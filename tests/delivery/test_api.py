"""Run against a disposable PostgreSQL DB using DELIVERY_TEST_DSN."""
import os
import socket
import subprocess
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from unittest.mock import patch
from uuid import uuid4

import psycopg
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from psycopg.rows import dict_row
from psycopg import sql

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
        self.identity = identity
        self.app = FastAPI()
        self.app.include_router(create_router(self.connect, identity, self.scorer))
        self.client = TestClient(self.app)
        self.enter_path = f"/exams/{self.exam}/attempts"

    @staticmethod
    def scorer(kind, selected, correct, rule, cap):
        return cap if selected == correct else 0

    def connect(self):
        db = psycopg.connect(self.dsn, row_factory=dict_row, application_name=self.schema)
        try:
            db.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(self.schema)))
            return db
        except Exception:
            db.close()
            raise

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
        self.assertEqual(self.client.get("/me/exams").json()[0]["deadline_at"], papers[0]["deadline_at"])
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

    def test_save_and_submit_blocked_until_cutoff(self):
        attempt_id = self.enter()["attempt_id"]
        path = "/attempts/" + attempt_id
        edit = dict(base_revision=0, selected_option_ids=[1], flagged=False)
        self.now.return_value = self.cutoff - timedelta(microseconds=1)
        with ThreadPoolExecutor(2) as pool:
            with self.connect() as blocker, psycopg.connect(self.dsn, autocommit=True) as monitor:
                blocker.execute("SELECT id FROM attempt WHERE id=%s FOR UPDATE", (attempt_id,))
                save = pool.submit(self.client.put, path + "/items/1", json=edit)
                submit = pool.submit(self.client.post, path + "/submit")
                timeout = time.monotonic() + 5
                while True:
                    blocked, = monitor.execute("""
                        SELECT COUNT(*) FROM pg_stat_activity WHERE application_name=%s
                        AND cardinality(pg_blocking_pids(pid)) > 0
                    """, (self.schema,)).fetchone()
                    if blocked == 2:
                        break
                    self.assertLess(time.monotonic(), timeout, "Both requests must reach the row lock")
                    time.sleep(0.01)
                self.now.return_value = self.cutoff
            late = save.result(timeout=5)
            terminal = submit.result(timeout=5)
        self.assertEqual(late.status_code, 409)
        self.assertEqual(terminal.status_code, 200)
        self.assertEqual(late.json()["receipt"], terminal.json())
        self.assertEqual(terminal.json()["close_reason"], "expired")
        with self.connect() as db:
            item = db.execute("SELECT answer_revision, awarded_marks FROM attempt_item WHERE slot=1").fetchone()
            self.assertEqual(item, {"answer_revision": 0, "awarded_marks": 0})
            events = db.execute("SELECT kind FROM attempt_event ORDER BY recorded_at").fetchall()
            self.assertEqual([row["kind"] for row in events], ["started", "expired"])

    @unittest.skipUnless(os.getenv("DELIVERY_LIVE_BROWSER") == "1", "set DELIVERY_LIVE_BROWSER=1 for Chromium")
    def test_browser_with_postgres(self):
        import uvicorn

        self.clock.stop()
        with self.connect() as db:
            db.execute("""UPDATE exam SET published_at=now()-interval '2 days',
                          opens_at=now()-interval '1 hour', closes_at=now()+interval '1 hour'""")
        sessions = {uuid4().hex: self.candidate, uuid4().hex: self.other}
        owner_cookie, peer_cookie = sessions

        def browser_identity(request: Request):
            actor = sessions.get(request.cookies.get("delivery_test_session"))
            if actor is None:
                raise HTTPException(401)
            return actor

        self.app.dependency_overrides[self.identity] = browser_identity
        with TemporaryDirectory() as public, socket.socket() as listener:
            @self.app.middleware("http")
            async def candidate_shell(request: Request, call_next):
                path = request.url.path
                candidate_page = path == "/me/exams" or (
                    path.startswith("/attempts/") and path.count("/") == 2
                )
                if candidate_page and request.method == "GET" and "text/html" in request.headers.get("accept", ""):
                    return FileResponse(Path(public) / "index.html")
                return await call_next(request)

            self.app.mount("/", StaticFiles(directory=public))
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
            server = uvicorn.Server(uvicorn.Config(self.app, log_level="warning", ws="none"))
            thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
            thread.start()
            script = Path(__file__).with_name("live-browser.mjs")
            try:
                subprocess.run(["node", str(script), public, origin, str(self.candidate), str(self.other)],
                               env={**os.environ, "DELIVERY_OWNER_COOKIE": owner_cookie,
                                    "DELIVERY_PEER_COOKIE": peer_cookie}, check=True, timeout=90)
            finally:
                server.should_exit = True
                thread.join(timeout=10)
                self.assertFalse(thread.is_alive(), "Live test HTTP server did not shut down")
        with self.connect() as db:
            rows = db.execute("SELECT slot, answer_revision, written_answer, awarded_marks FROM attempt_item ORDER BY slot").fetchall()
            self.assertEqual([row["answer_revision"] for row in rows], [1, 0, 2])
            self.assertEqual([row["awarded_marks"] for row in rows], [1, 0, None])
            self.assertEqual(rows[2]["written_answer"], "Saved after reconnecting.")
            events = db.execute("SELECT kind FROM attempt_event ORDER BY recorded_at").fetchall()
            self.assertEqual([row["kind"] for row in events], ["started", "submitted"])

    def test_preferences_and_role(self):
        prefs = dict(font_percent=200, workspace_layout="focus")
        self.assertEqual(self.client.patch("/me/preferences", json=prefs).json(), prefs)
        self.assertEqual(self.enter()["preferences"], prefs)
        self.assertEqual(self.client.patch("/me/preferences", json={**prefs, "font_percent": 201}).status_code, 422)
        with self.connect() as db:
            db.execute("DELETE FROM account_role WHERE account_id=%s", (self.actor,))
        self.assertEqual(self.client.get("/me/exams").status_code, 403)
