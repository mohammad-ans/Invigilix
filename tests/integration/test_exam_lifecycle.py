"""Cross-feature acceptance against PostgreSQL. Each run owns a new empty schema."""
import hashlib
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from sqlalchemy.engine import make_url

from backend.app.main import create_app
from backend.app.platform.bootstrap import first_admin
from backend.app.platform.database import database_engine, transactions
from backend.app.platform.identity import COOKIE, NewAccount
from backend.app.platform.migrate import upgrade

ORIGIN = "https://office.example.test"
PASSWORD = "test-only-phrase-4286"


@pytest.fixture
def office(monkeypatch):
    dsn = os.getenv("FOLIO_TEST_DSN")
    if not dsn:
        pytest.skip("Set FOLIO_TEST_DSN to a disposable PostgreSQL database")
    schema = "integration_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as setup:
        setup.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    url = make_url(dsn).update_query_dict({"options": "-csearch_path=" + schema})
    monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
    monkeypatch.setenv("PUBLIC_ORIGIN", ORIGIN)
    engine = database_engine()
    try:
        upgrade(engine)
        upgrade(engine)
        connect = transactions(engine)
        first_admin(connect, NewAccount(email="admin@example.test", display_name="Registrar",
                                        roles={"admin"}, password=PASSWORD))
        app = create_app()
        with TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN}) as client:
            yield client, connect
    finally:
        engine.dispose()
        with psycopg.connect(dsn, autocommit=True) as setup:
            setup.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_publish_sit_grade_release(office):
    client, connect = office

    def call(method, path, expected=200, body=None, **kwargs):
        response = client.request(method, "/api" + path, json=body, **kwargs)
        assert response.status_code == expected, (path, response.text[:500])
        return response

    def login(name):
        return call("POST", "/sessions", body={"email": name + "@example.test", "password": PASSWORD})

    def logout():
        call("DELETE", "/session", 204)
        call("GET", "/session", 401)

    call("GET", "/exams", 401)
    call("POST", "/sessions", 403, headers={"Origin": "https://unrelated.example.test"})
    call("POST", "/sessions", 401, {"email": "admin@example.test", "password": "invalid"})
    cookie = login("admin").headers["set-cookie"].lower()
    assert all(flag in cookie for flag in ["httponly", "secure", "samesite=lax"])
    admin_token = client.cookies[COOKIE]
    ids = {}
    for name, role in [("lecturer", "examiner"), ("student", "candidate"), ("other", "candidate")]:
        ids[name] = call("POST", "/admin/accounts", 201, {"email": name + "@example.test", "display_name": name,
                         "roles": [role], "password": PASSWORD}).json()["id"]
    call("GET", "/questions", 403)
    logout()
    login("lecturer")
    common = {"topic": "Field studies", "difficulty": "easy"}
    objective = call("POST", "/questions", 201, {**common, "prompt": "Which reading is cooler?", "kind": "single",
        "marking_rule": "exact", "options": [{"id": 1, "label": "10 °C"}, {"id": 2, "label": "20 °C"}], "correct_option_ids": [1]}).json()
    written = call("POST", "/questions", 201, {**common, "prompt": "Explain your sampling method.",
        "kind": "written", "marking_rule": "manual", "rubric": "Mention repetition."}).json()
    now = datetime.now(timezone.utc)
    exam = call("POST", "/exams", 201, {"title": "Field journal", "opens_at": (now - timedelta(minutes=5)).isoformat(),
        "closes_at": (now + timedelta(hours=1)).isoformat(), "duration_minutes": 10, "total_marks": "5"}).json()["id"]
    base = "/exams/" + exam
    call("PUT", base + "/items", body={"items": [{"question_id": objective["id"], "max_marks": "2"},
        {"question_id": written["id"], "max_marks": "3"}]})
    call("POST", base + "/publish")
    call("POST", base + "/enrollments", body={"candidate_emails": ["student@example.test"]})
    logout()
    login("student")
    call("GET", "/admin/accounts", 403)
    assert call("GET", "/me/exams").json()[0]["id"] == exam
    paper = call("POST", base + "/attempts").json()
    assert all(k not in str(paper) for k in ["correct_option_ids", "is_correct", "rubric"])
    aid = paper["attempt_id"]
    attempt = "/attempts/" + aid
    for slot, answer in [(1, {"selected_option_ids": [1]}), (2, {"written_answer": "Repeat the readings."})]:
        call("PUT", attempt + f"/items/{slot}", body={**answer, "flagged": False, "base_revision": 0})
    assert call("POST", attempt + "/submit").json()["close_reason"] == "submitted"
    result = "/me" + attempt + "/result"
    assert call("GET", "/me/results").json() == []
    call("GET", result, 404)
    logout()
    login("lecturer")
    assert call("GET", base + "/marking").json()["pending_written_count"] == 1
    call("PUT", attempt + "/items/2/grade", body={"awarded_marks": "2"})
    call("POST", base + "/results/publish", 409)
    # Advance only the schedule of this isolated test exam past its release gate.
    with connect() as db:
        db.execute("UPDATE exam SET closes_at=clock_timestamp() WHERE id=%s", (exam,))
    call("POST", base + "/results/publish")
    logout()
    login("other")
    call("GET", result, 404)
    call("GET", attempt, 404)
    logout()
    login("student")
    assert call("GET", "/me/results").json()[0]["attempt_id"] == aid
    score = call("GET", result).json()
    assert (score["total_score"], score["max_marks"]) == ("4.00", "5.00")
    pdf = call("GET", "/me" + attempt + "/report").content
    assert pdf.startswith(b"%PDF")
    assert call("POST", "/reports/verify", body={"verification_code": score["verification_code"],
                "sha256_hex": hashlib.sha256(pdf).hexdigest()}).json()["valid"]
    student_token = client.cookies[COOKIE]
    # Use an independent browser session for the administrator.
    client.cookies.clear()
    login("admin")
    call("GET", "/session", headers={"Cookie": f"{COOKIE}={student_token}"})
    call("PATCH", "/admin/accounts/" + ids["student"], body={"display_name": "Student", "roles": ["candidate"], "enabled": False})
    call("GET", "/session", 401, headers={"Cookie": f"{COOKIE}={student_token}"})
    call("GET", "/session", 401, headers={"Cookie": f"{COOKIE}={admin_token}"})
    call("POST", "/sessions", 401, {"email": "student@example.test", "password": PASSWORD})

    call("PATCH", "/admin/accounts/" + ids["student"], body={"display_name": "Student", "roles": ["candidate"], "enabled": True})
    call("GET", "/session", 401, headers={"Cookie": f"{COOKIE}={student_token}"})
    admin_session = client.cookies[COOKIE]
    client.cookies.clear()
    login("other")
    old_roles_token = client.cookies[COOKIE]
    call("PATCH", "/admin/accounts/" + ids["other"], body={"display_name": "Staff", "roles": ["examiner"], "enabled": True},
         headers={"Cookie": f"{COOKIE}={admin_session}"})
    call("GET", "/session", 401, headers={"Cookie": f"{COOKIE}={old_roles_token}"})
    assert login("other").json()["roles"] == ["examiner"]
    call("GET", "/me/exams", 403)
    with connect() as db:
        db.execute("UPDATE login_session SET expires_at=now() WHERE account_id=%s", (ids["other"],))
    call("GET", "/questions", 401)
