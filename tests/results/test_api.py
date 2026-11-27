"""FastAPI router integration tests for all results, monitor, grading, and verify routes."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from backend.app.features.results import ADMIN, Actor, CANDIDATE, EXAMINER, build_router
from tests.results.conftest import DualBackendHarness


def _make_app(harness: DualBackendHarness, actors: dict[str, Actor]) -> FastAPI:
    app = FastAPI()

    def current_actor(x_test_actor: str | None = Header(default=None)) -> Actor:
        if not x_test_actor or x_test_actor not in actors:
            raise HTTPException(status_code=401, detail="Not authenticated")
        return actors[x_test_actor]

    app.include_router(build_router(harness.module, current_actor), prefix="/api")
    return app


def test_http_routes_status_codes_privacy_and_openapi():
    harness = DualBackendHarness("sql")
    owner = harness.add_account(email="remy@example.test", display_name="Remy Chen", roles={EXAMINER})
    other = harness.add_account(email="ola@example.test", display_name="Ola", roles={EXAMINER})
    cand = harness.add_account(email="sana@example.test", display_name="Sana Ali", roles={CANDIDATE})
    admin = harness.add_account(email="admin@example.test", display_name="Admin", roles={ADMIN})

    opens = datetime(2026, 11, 27, 10, 30, tzinfo=timezone.utc)
    closes = datetime(2026, 11, 27, 11, 0, tzinfo=timezone.utc)
    exam = harness.create_exam(
        owner_id=owner.id,
        title="Field ecology",
        opens_at=opens,
        closes_at=closes,
        total_marks="10.00",
        published_at=opens - timedelta(hours=1),
        items=[
            {
                "topic": "Ecology",
                "difficulty": "easy",
                "prompt": "Abiotic factor?",
                "kind": "single",
                "marking_rule": "exact",
                "max_marks": "2.00",
                "options": [(1, "Light", True), (2, "Count", False)],
            },
            {
                "topic": "Diversity",
                "difficulty": "medium",
                "prompt": "Species diversity metrics?",
                "kind": "multiple",
                "marking_rule": "partial_no_wrong",
                "max_marks": "4.00",
                "options": [(1, "Richness", True), (2, "Temp", False), (3, "Abundance", True)],
            },
            {
                "topic": "Sampling",
                "difficulty": "hard",
                "prompt": "Why repeat transect?",
                "kind": "written",
                "marking_rule": "manual",
                "max_marks": "4.00",
                "rubric": "Private rubric text",
            },
        ],
    )
    harness.enroll(exam_id=exam.id, candidate_id=cand.id, enrolled_by=owner.id)
    att = harness.create_attempt(
        exam=exam,
        candidate_id=cand.id,
        finalized_at=closes - timedelta(minutes=2),
        close_reason="submitted",
        responses={
            1: {"selected": [1]},
            2: {"selected": [1]},
            3: {"written": "Replication reduces chance variation."},
        },
        events=[("started", opens + timedelta(minutes=1), None), ("reconnected", opens + timedelta(minutes=6), "Dropped")],
    )

    app = _make_app(harness, {"owner": owner, "other": other, "cand": cand, "admin": admin})
    client = TestClient(app)

    # NFR05: OpenAPI schema compiles cleanly
    schema = app.openapi()
    assert "/api/reports/verify" in schema["paths"]

    # 401 on absent session
    assert client.get(f"/api/exams/{exam.id}/monitor").status_code == 401

    # 403 for wrong role, 404 for other examiner
    assert client.get(f"/api/exams/{exam.id}/monitor", headers={"X-Test-Actor": "cand"}).status_code == 403
    assert client.get(f"/api/exams/{exam.id}/monitor", headers={"X-Test-Actor": "admin"}).status_code == 403
    assert client.get(f"/api/exams/{exam.id}/monitor", headers={"X-Test-Actor": "other"}).status_code == 404

    # Monitor + announcement roundtrip
    mon = client.get(f"/api/exams/{exam.id}/monitor", headers={"X-Test-Actor": "owner"})
    assert mon.status_code == 200
    assert mon.headers["cache-control"] == "no-store"
    assert mon.json()["counts"]["submitted"] == 1

    post_ann = client.post(
        f"/api/exams/{exam.id}/announcements",
        headers={"X-Test-Actor": "owner"},
        json={"message": "Clarification on Q3."},
    )
    assert post_ann.status_code == 201
    cand_ann = client.get(f"/api/exams/{exam.id}/announcements", headers={"X-Test-Actor": "cand"})
    assert cand_ann.status_code == 200
    assert cand_ann.json()[0]["message"] == "Clarification on Q3."

    # 422 on invalid grade & 409 on early release
    bad_grade = client.put(
        f"/api/attempts/{att.id}/items/3/grade",
        headers={"X-Test-Actor": "owner"},
        json={"awarded_marks": "5.00"},
    )
    assert bad_grade.status_code == 422
    assert bad_grade.json()["error"]["code"] == "validation_failed"
    assert bad_grade.json()["error"]["issues"][0]["field"] == "awarded_marks"

    good_grade = client.put(
        f"/api/attempts/{att.id}/items/3/grade",
        headers={"X-Test-Actor": "owner"},
        json={"awarded_marks": "3.00"},
    )
    assert good_grade.status_code == 200
    assert good_grade.json()["attempt_total_score"] == "7.00"

    early_rel = client.post(f"/api/exams/{exam.id}/results/publish", headers={"X-Test-Actor": "owner"})
    assert early_rel.status_code == 409
    assert early_rel.json()["error"]["code"] == "exam_not_closed"

    # Unreleased candidate result returns 404
    assert client.get(f"/api/me/attempts/{att.id}/result", headers={"X-Test-Actor": "cand"}).status_code == 404

    # Advance past closes_at and publish
    harness.clock.set(closes + timedelta(minutes=1))
    rel = client.post(f"/api/exams/{exam.id}/results/publish", headers={"X-Test-Actor": "owner"})
    assert rel.status_code == 200
    assert rel.json()["summary"]["mean_score"] == "7.00"

    # Candidate reads result: fixed-point strings, zero keys/rubrics leaked
    res = client.get(f"/api/me/attempts/{att.id}/result", headers={"X-Test-Actor": "cand"})
    assert res.status_code == 200
    body = res.json()
    assert body["total_score"] == "7.00"
    assert body["max_marks"] == "10.00"
    assert "Private rubric text" not in res.text
    assert "is_correct" not in res.text

    # PDF downloads & public verification
    pdf_resp = client.get(f"/api/me/attempts/{att.id}/report", headers={"X-Test-Actor": "cand"})
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert pdf_resp.headers["cache-control"] == "no-store"
    assert hashlib.sha256(pdf_resp.content).hexdigest() == body["sha256_hex"]

    # Public verifier works without authentication and returns ONLY {"valid": bool}
    ver_ok = client.post(
        "/api/reports/verify",
        json={"verification_code": body["verification_code"], "sha256_hex": body["sha256_hex"]},
    )
    assert ver_ok.status_code == 200
    assert ver_ok.json() == {"valid": True}

    ver_bad = client.post(
        "/api/reports/verify",
        json={"verification_code": body["verification_code"], "sha256_hex": "0" * 64},
    )
    assert ver_bad.status_code == 200
    assert ver_bad.json() == {"valid": False}

    ver_422 = client.post(
        "/api/reports/verify",
        json={"verification_code": "", "sha256_hex": "not-hex"},
    )
    assert ver_422.status_code == 422

    # Class summary PDF export
    class_pdf = client.get(f"/api/exams/{exam.id}/report", headers={"X-Test-Actor": "owner"})
    assert class_pdf.status_code == 200
    assert class_pdf.headers["content-type"] == "application/pdf"
