"""Exercise the command Railway runs against an isolated PostgreSQL schema."""
import secrets
import subprocess
import sys

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.platform.database import transactions

ROLES = ("admin", "examiner", "candidate")
ORIGIN = "https://demo.example.test"


def release(*, check=True):
    return subprocess.run([sys.executable, "-m", "backend.migrations.predeploy"],
                          capture_output=True, text=True, check=check, timeout=30)


def test_health_and_seeded_release(isolated_database, monkeypatch):
    monkeypatch.setenv("PUBLIC_ORIGIN", ORIGIN)
    credentials = {role: secrets.token_urlsafe(24) for role in ROLES}
    for role in ROLES:
        monkeypatch.delenv(f"FOLIO_SEED_{role.upper()}_PASSWORD", raising=False)
    connect = transactions(isolated_database)

    with TestClient(create_app(), base_url=ORIGIN) as client:
        before_migration = client.get("/api/health")
        assert before_migration.status_code == 503
        assert before_migration.json() == {"status": "unavailable"}

        release()
        ready = client.get("/api/health")
        assert ready.status_code == 200
        assert ready.json() == {"status": "ok"}
        with connect() as db:
            assert db.execute("SELECT id FROM account").fetchall() == []

        monkeypatch.setenv("FOLIO_SEED_ADMIN_PASSWORD", credentials["admin"])
        incomplete = release(check=False)
        assert incomplete.returncode != 0
        assert credentials["admin"] not in incomplete.stderr + incomplete.stdout
        with connect() as db:
            assert db.execute("SELECT id FROM account").fetchall() == []

        for role, password in credentials.items():
            monkeypatch.setenv(f"FOLIO_SEED_{role.upper()}_PASSWORD", password)
        release()
        for role, password in credentials.items():
            response = client.post("/api/sessions", json={"email": f"demo-{role}@example.test", "password": password},
                                   headers={"Origin": ORIGIN})
            assert response.status_code == 200
            assert response.json()["roles"] == [role]

        with connect() as db:
            rows = db.execute("SELECT id, password_hash FROM account ORDER BY id").fetchall()
            assert len(rows) == 3
            assert all(row["password_hash"].startswith("$argon2id$") for row in rows)
            db.execute("UPDATE account SET enabled=false WHERE email='demo-examiner@example.test'")
        monkeypatch.setenv("FOLIO_SEED_ADMIN_PASSWORD", secrets.token_urlsafe(24))
        release()
        with connect() as db:
            assert db.execute("SELECT id, password_hash FROM account ORDER BY id").fetchall() == rows
            assert not db.execute("SELECT enabled FROM account WHERE email='demo-examiner@example.test'").fetchone()["enabled"]
