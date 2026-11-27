"""Run against a disposable PostgreSQL DB using DELIVERY_TEST_DSN."""
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from backend.app.features.delivery.router import create_router
from backend.app.features.delivery.service import expire_due


@unittest.skipUnless(os.getenv("DELIVERY_TEST_DSN"), "set DELIVERY_TEST_DSN to a test database")
class DeliveryAPI(unittest.TestCase):
    def setUp(self):
        self.dsn = os.environ["DELIVERY_TEST_DSN"]
        self.schema = "delivery_test_" + uuid4().hex
        with psycopg.connect(self.dsn) as db:
            db.execute("CREATE SCHEMA " + self.schema)
        self.addCleanup(self.drop_schema)
        self.actor = self.candidate = uuid4()
        self.other, self.exam = uuid4(), uuid4()
        self.start = datetime(2026, 11, 27, 10, 42, tzinfo=timezone.utc)
        self.cutoff = self.start.replace(hour=11, minute=0)
        with self.connect() as db:
            sql = Path(__file__).resolve().parents[2] / "contracts" / "exam_schema.sql"
            db.execute(sql.read_text())
            for actor in [self.actor, self.other]:
                db.execute("INSERT INTO account(id,email,display_name,password_hash) VALUES (%s,%s,'Test','fake')",
                           (actor, str(actor)))
                db.execute("INSERT INTO account_role VALUES (%s,'candidate')", (actor,))
            db.execute("""
                INSERT INTO exam VALUES (%s,%s,'Biology','Read carefully',%s,%s,1800,3,true,true,%s,NULL)
            """, (self.exam, self.other, self.start.replace(minute=30), self.cutoff, self.start.replace(hour=9)))
            db.execute("INSERT INTO enrollment VALUES (%s,%s,%s,true)", (self.exam,self.actor,self.other))
            for slot, kind in enumerate(["single", "multiple", "written"], 1):
                question, version = uuid4(), uuid4()
                db.execute("INSERT INTO question VALUES (%s,%s)", (question,self.other))
                db.execute("INSERT INTO question_version VALUES (%s,%s,1,'Topic','easy',%s,%s,%s,'Private')",
                           (version, question, "Question " + str(slot), kind, "manual" if slot == 3 else "exact"))
                if slot != 3:
                    for n in [1, 2]:
                        db.execute("INSERT INTO question_option VALUES (%s,%s,%s,%s)", (version,n,str(n),n==1))
                db.execute("INSERT INTO exam_item VALUES (%s,%s,%s,1)", (self.exam,slot,version))
        self.clock = patch("backend.app.features.delivery.service.now", return_value=self.start)
        self.now = self.clock.start()
        self.addCleanup(self.clock.stop)
        def identity():
            if self.actor is None:
                raise HTTPException(401)
            return self.actor
        app = FastAPI()
        app.include_router(create_router(self.connect, identity, self.scorer))
        self.client = TestClient(app)
        self.enter_path = f"/exams/{self.exam}/attempts"

    @staticmethod
    def scorer(kind, selected, correct, rule, cap):
        return cap if selected == correct else 0

    def connect(self):
        return psycopg.connect(self.dsn, options="-c search_path=" + self.schema, row_factory=dict_row)

    def drop_schema(self):
        with psycopg.connect(self.dsn) as db:
            db.execute("DROP SCHEMA " + self.schema + " CASCADE")

    def enter(self):
        result = self.client.post(self.enter_path)
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def test_entry_and_resume(self):
        self.now.return_value = self.start.replace(minute=15)
        self.assertEqual(self.client.get("/me/exams").json()[0]["status"], "upcoming")
        self.assertEqual(self.client.post(self.enter_path).status_code, 409)
        self.now.return_value = self.start
        self.actor = self.other
        self.assertEqual(self.client.post(self.enter_path).status_code, 404)
        self.actor = self.candidate
        with ThreadPoolExecutor(2) as pool:
            papers = list(pool.map(lambda _: self.enter(), range(2)))
        self.assertEqual(papers[0], papers[1])
        self.assertEqual(datetime.fromisoformat(papers[0]["deadline_at"]), self.cutoff)
        self.assertEqual([q["display_no"] for q in papers[0]["items"]], [1, 2, 3])
        self.assertNotIn("rubric", str(papers))
        self.assertNotIn("is_correct", str(papers))
        self.actor = self.other
        self.assertEqual(self.client.get("/attempts/" + papers[0]["attempt_id"]).status_code, 404)
        self.actor = None
        self.assertEqual(self.client.get("/me/exams").status_code, 401)

    def test_replay_conflict_and_invalid_edits(self):
        attempt = "/attempts/" + self.enter()["attempt_id"]
        path = attempt + "/items/1"
        body = dict(base_revision=0, selected_option_ids=[1], flagged=True)
        first = self.client.put(path, json=body)
        self.assertEqual(first.json()["revision"], 1)
        self.assertEqual(self.client.put(path, json=body).json(), first.json())
        conflict = self.client.put(path, json={**body, "selected_option_ids": []})
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["item"]["selected_option_ids"], [1])
        for ids in [[3], [1, 2], [1, 1], ["1"]]:
            self.assertEqual(self.client.put(path, json={**body, "selected_option_ids": ids}).status_code, 422)
        self.assertEqual(self.client.put(attempt + "/items/3", json=body).status_code, 422)
        self.assertEqual(self.client.put(path, json={**body, "base_revision": 1, "selected_option_ids": []}).json()["revision"], 2)

    def test_cutoff_and_duplicate_submit(self):
        attempt = "/attempts/" + self.enter()["attempt_id"]
        self.now.return_value = self.cutoff
        late = self.client.put(attempt + "/items/1", json=dict(base_revision=0, flagged=False, selected_option_ids=[1]))
        self.assertEqual(late.status_code, 409)
        receipt = late.json()["receipt"]
        self.assertEqual(receipt["close_reason"], "expired")
        self.assertEqual(receipt, self.client.post(attempt + "/submit").json())
        self.assertEqual(receipt, self.client.post(attempt + "/submit").json())
        self.assertEqual(self.client.get("/me/exams").json()[0]["status"], "completed")
        with self.connect() as db:
            self.assertEqual(db.execute("SELECT total_score FROM attempt_score").fetchone()["total_score"], 0)

    def test_simultaneous_submit(self):
        attempt = "/attempts/" + self.enter()["attempt_id"]
        self.now.return_value = self.cutoff - timedelta(microseconds=1)
        with ThreadPoolExecutor(2) as pool:
            one, two = pool.map(lambda _: self.client.post(attempt + "/submit").json(), range(2))
        self.assertEqual(one, two)
        self.assertEqual(one["close_reason"], "submitted")
        with self.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) AS n FROM attempt_event WHERE kind='submitted'").fetchone()["n"], 1)

    def test_worker_restart(self):
        self.enter()
        with self.connect() as db:
            db.execute("""UPDATE attempt SET started_at=clock_timestamp()-interval '2 hours',
                          deadline_at=clock_timestamp()-interval '1 hour'""")
        self.clock.stop()
        self.assertEqual(expire_due(self.connect, self.scorer), 1)
        self.assertEqual(expire_due(self.connect, self.scorer), 0)

    def test_preferences_and_role(self):
        prefs = dict(font_percent=200, workspace_layout="focus")
        self.assertEqual(self.client.patch("/me/preferences", json=prefs).json(), prefs)
        self.assertEqual(self.enter()["preferences"], prefs)
        self.assertEqual(self.client.patch("/me/preferences", json={**prefs, "font_percent": 201}).status_code, 422)
        with self.connect() as db:
            db.execute("DELETE FROM account_role WHERE account_id=%s", (self.actor,))
        self.assertEqual(self.client.get("/me/exams").status_code, 403)
