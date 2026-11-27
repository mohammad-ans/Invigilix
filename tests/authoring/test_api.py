"""HTTP contract for authoring: status codes, error shape and key privacy."""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from app.features.authoring.api import build_router
from app.features.authoring.ports import Actor

from support import CLOSES, OPENS

DETAILS = {"title": "Field ecology", "instructions": "Answer every question.",
           "opens_at": OPENS.isoformat(), "closes_at": CLOSES.isoformat(),
           "duration_minutes": 30, "total_marks": "10", "shuffle_questions": True}
SINGLE = {"topic": "Ecology", "difficulty": "easy", "kind": "single",
          "prompt": "Which factor is abiotic?", "marking_rule": "exact",
          "options": [{"id": 1, "label": "Light"}, {"id": 2, "label": "Rabbit"}],
          "correct_option_ids": [1]}
WRITTEN = {"topic": "Sampling", "difficulty": "hard", "kind": "written",
           "prompt": "Describe one source of bias.", "marking_rule": "manual",
           "rubric": "PRIVATE-RUBRIC names a concrete bias."}


@pytest.fixture
def api(world):
    """A test app whose session stand-in reads an account name from a header."""

    def current_actor(x_test_account: str | None = Header(default=None)) -> Actor:
        if x_test_account not in world.accounts:
            raise HTTPException(401, "Sign in to continue.")
        return world.actor(x_test_account)

    app = FastAPI()
    app.include_router(build_router(world.module, current_actor))
    client = TestClient(app)
    client.world = world
    return client


def as_(name: str) -> dict:
    return {"X-Test-Account": name}


def make_paper(api, totals=("2", "8")) -> str:
    exam = api.post("/exams", json=DETAILS, headers=as_("examiner")).json()
    q1 = api.post("/questions", json=SINGLE, headers=as_("examiner")).json()
    q2 = api.post("/questions", json=WRITTEN, headers=as_("examiner")).json()
    items = [{"question_id": q1["id"], "max_marks": totals[0]},
             {"question_id": q2["id"], "max_marks": totals[1]}]
    response = api.put(f"/exams/{exam['id']}/items", json={"items": items},
                       headers=as_("examiner"))
    assert response.status_code == 200, response.text
    return exam["id"]


class TestExamEndpoints:
    def test_create_review_and_publish(self, api):
        exam_id = make_paper(api)
        body = api.get(f"/exams/{exam_id}", headers=as_("examiner")).json()
        assert body["state"] == "draft" and body["publication"]["ready"]
        assert body["total_marks"] == "10.00" and body["allocated_marks"] == "10.00"
        assert [i["slot"] for i in body["items"]] == [1, 2]
        published = api.post(f"/exams/{exam_id}/publish", headers=as_("examiner"))
        assert published.status_code == 200 and published.json()["state"] == "scheduled"
        assert published.headers["cache-control"] == "no-store"
        frozen = api.put(f"/exams/{exam_id}", json=DETAILS, headers=as_("examiner"))
        assert frozen.status_code == 409 and frozen.json()["error"]["code"] == "exam_published"

    def test_invalid_publish_identifies_item_and_field(self, api):
        exam_id = make_paper(api, totals=("2", "4"))
        response = api.post(f"/exams/{exam_id}/publish", headers=as_("examiner"))
        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "paper_invalid"
        assert [(i["code"], i["field"]) for i in error["issues"]] == [
            ("total_mismatch", "total_marks")]

    def test_invalid_particulars_are_422_with_fields(self, api):
        bad = {**DETAILS, "duration_minutes": 0, "total_marks": "-1",
               "closes_at": OPENS.isoformat()}
        response = api.post("/exams", json=bad, headers=as_("examiner"))
        assert response.status_code == 422
        assert {i["field"] for i in response.json()["error"]["issues"]} == {
            "duration_minutes", "total_marks", "closes_at"}

    def test_naive_timestamp_is_rejected_by_request_validation(self, api):
        bad = {**DETAILS, "opens_at": "2026-11-27T10:30:00"}
        response = api.post("/exams", json=bad, headers=as_("examiner"))
        assert response.status_code == 422
        assert response.json()["error"]["issues"][0]["field"] == "opens_at"

    def test_slot_request_validation_is_one_based(self, api):
        exam = api.post("/exams", json=DETAILS, headers=as_("examiner")).json()
        response = api.put(f"/exams/{exam['id']}/items",
                           json={"items": [{"question_id": "nope", "max_marks": "1"}]},
                           headers=as_("examiner"))
        assert response.status_code == 422
        assert response.json()["error"]["issues"][0]["item"] == 1


class TestAccessScope:
    def test_401_403_404(self, api):
        exam_id = make_paper(api)
        assert api.get("/exams").status_code == 401
        assert api.get("/exams", headers=as_("nora")).status_code == 403
        assert api.get(f"/exams/{exam_id}", headers=as_("other")).status_code == 404
        assert api.get(f"/exams/{uuid4()}", headers=as_("examiner")).status_code == 404
        response = api.post(f"/exams/{exam_id}/preview", headers=as_("other"))
        assert response.status_code == 404 and "Field ecology" not in response.text

    def test_extra_fields_are_refused(self, api):
        response = api.post("/exams", json={**DETAILS, "owner_id": str(uuid4())},
                            headers=as_("examiner"))
        assert response.status_code == 422


class TestSandboxEndpoint:
    def test_preview_has_attempt_shape_and_no_private_data(self, api):
        exam_id = make_paper(api)
        before = api.world.snapshot()
        response = api.post(f"/exams/{exam_id}/preview", headers=as_("examiner"))
        assert response.status_code == 200
        body = response.json()
        assert body["mode"] == "sandbox"
        assert set(body["items"][0]) == {"slot", "display_no", "kind", "prompt", "max_marks",
                                         "options", "selected_option_ids", "written_answer",
                                         "flagged", "revision"}
        for forbidden in ("correct", "PRIVATE-RUBRIC", "marking_rule", "rubric"):
            assert forbidden not in response.text
        assert api.world.snapshot() == before


class TestBankEndpoints:
    def test_create_search_revise_and_history(self, api):
        created = api.post("/questions", json=SINGLE, headers=as_("examiner"))
        assert created.status_code == 201
        qid = created.json()["id"]
        found = api.get("/questions", params={"difficulty": "easy", "q": "abiotic"},
                        headers=as_("examiner")).json()
        assert [q["id"] for q in found] == [qid]
        same = api.post(f"/questions/{qid}/versions", json=SINGLE, headers=as_("examiner"))
        assert same.status_code == 200 and same.json()["created"] is False
        revised = api.post(f"/questions/{qid}/versions",
                           json={**SINGLE, "prompt": "Which factor is non-living?"},
                           headers=as_("examiner"))
        assert revised.status_code == 201 and revised.json()["question"]["version_count"] == 2
        history = api.get(f"/questions/{qid}", headers=as_("examiner")).json()
        assert [v["number"] for v in history["versions"]] == [2, 1]

    def test_key_outside_options_and_two_single_keys(self, api):
        response = api.post("/questions", json={**SINGLE, "correct_option_ids": [7]},
                            headers=as_("examiner"))
        assert response.json()["error"]["issues"][0]["code"] == "unknown_key"
        response = api.post("/questions", json={**SINGLE, "correct_option_ids": [1, 2]},
                            headers=as_("examiner"))
        assert response.status_code == 422
        assert response.json()["error"]["issues"][0]["code"] == "single_key_count"


class TestRosterAndImports:
    def test_enroll_and_withdraw(self, api):
        exam_id = make_paper(api)
        roster = api.post(f"/exams/{exam_id}/enrollments",
                          json={"candidate_emails": ["nora@example.test"]},
                          headers=as_("examiner")).json()
        entry = roster["entries"][0]
        assert (entry["display_name"], entry["access"]) == ("Nora Khan", "awaiting_publication")
        withdrawn = api.patch(f"/exams/{exam_id}/enrollments/{entry['candidate_id']}",
                              json={"active": False}, headers=as_("examiner")).json()
        assert withdrawn["entries"][0]["access"] == "enrollment_inactive"

    def test_csv_import_dry_run_then_commit(self, api):
        exam_id = make_paper(api)
        csv = b"candidate_email\nnora@example.test\nghost@example.test\n"
        url = f"/exams/{exam_id}/enrollments/import"
        checked = api.post(url, params={"dry_run": True}, content=csv, headers=as_("examiner"))
        assert checked.status_code == 200
        assert [(i["row"], i["field"]) for i in checked.json()["issues"]] == [
            (3, "candidate_email")]
        refused = api.post(url, content=csv, headers=as_("examiner"))
        assert refused.status_code == 422 and refused.json()["error"]["code"] == "import_invalid"
        accepted = api.post(url, content=csv.replace(b"ghost", b"eli"), headers=as_("examiner"))
        assert accepted.json()["created"] == 2 and accepted.json()["committed"] is True

    def test_candidate_import_requires_admin(self, api):
        data = b"email,display_name\nsana@example.test,Sana Ali\n"
        assert api.post("/admin/accounts/import", content=data,
                        headers=as_("examiner")).status_code == 403
        response = api.post("/admin/accounts/import", content=data, headers=as_("admin"))
        assert response.status_code == 200
        assert response.json()["credentials"][0]["email"] == "sana@example.test"
        assert response.headers["cache-control"] == "no-store"

    def test_oversized_upload(self, api):
        response = api.post("/questions/import", content=b"x" * (2 * 1024 * 1024 + 1),
                            headers=as_("examiner"))
        assert response.status_code == 422
        assert response.json()["error"]["issues"][0]["code"] == "file_too_large"


def test_openapi_contract_generates(api):
    """NFR05: the router contributes a valid OpenAPI document."""
    paths = api.get("/openapi.json").json()["paths"]
    assert {"/exams", "/exams/{exam_id}/publish", "/exams/{exam_id}/preview",
            "/exams/{exam_id}/enrollments/import", "/questions/{question_id}/versions",
            "/admin/accounts/import"} <= set(paths)
