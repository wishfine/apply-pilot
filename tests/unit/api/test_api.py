from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from applypilot.api.app import app


def profile_payload() -> dict:
    return {
        "profile_id": "cand_api",
        "identity": {"name": "张三", "id_number": "110101200001010011"},
        "contact": {"email": "z@example.com"},
        "education": [
            {
                "id": "edu_master",
                "school_name": "北京大学",
                "education_level": "master",
                "major": "计算机",
                "department": "计算机学院",
                "start_date": "2023-09",
                "end_date": "2026-06",
            }
        ],
        "experiences": [
            {
                "id": "exp_new",
                "experience_type": "internship",
                "org_name": "新东方",
                "title": "算法实习生",
                "start_date": "2026-01",
                "end_date": "2026-06",
                "description_bullets": ["算法建模"],
            },
            {
                "id": "exp_old",
                "experience_type": "internship",
                "org_name": "高德地图",
                "title": "应用算法实习生",
                "start_date": "2025-01",
                "end_date": "2025-06",
                "description_bullets": ["流量预测"],
            },
        ],
        "projects": [],
    }


def page_payload() -> dict:
    return {
        "url_origin": "https://example.com",
        "active_section": "个人信息",
        "fields": [
            {"field_ref": "f-name", "label": "姓名", "kind": "text", "required": True},
            {"field_ref": "f-org-1", "label": "单位名称", "section": "实习经历", "record_group": "row-1", "kind": "text", "required": True},
            {"field_ref": "f-org-2", "label": "单位名称", "section": "实习经历", "record_group": "row-2", "kind": "text", "required": True},
            {"field_ref": "f-note", "label": "备注", "kind": "text", "required": False},
        ],
    }


def test_healthz_and_form_plan_contract():
    client = TestClient(app)
    assert client.get("/healthz").json()["status"] == "ok"
    response = client.post("/v1/forms/plan", json={"profile": profile_payload(), "page": page_payload()})
    assert response.status_code == 200
    body = response.json()
    assert body["mapping_version"].startswith("rules-")
    assert [item["value"] for item in body["plan"][:3]] == ["张三", "新东方", "高德地图"]
    assert body["summary"] == {"fields": 4, "fill": 3, "review": 0, "optional_skipped": 1, "existing_skipped": 0}
    assert body["plan"][1]["record_id"] == "exp_new"
    assert body["plan"][2]["profile_path"] == "/experiences/1/org_name"


def test_form_plan_groups_repeated_experience_rows_without_explicit_group_ids():
    client = TestClient(app)
    page = page_payload()
    for field in page["fields"]:
        field.pop("record_group", None)
    response = client.post("/v1/forms/plan", json={"profile": profile_payload(), "page": page})
    assert response.status_code == 200
    plan = response.json()["plan"]
    assert [item["value"] for item in plan[:3]] == ["张三", "新东方", "高德地图"]


def test_reconcile_keeps_existing_facts_and_reports_conflict():
    client = TestClient(app)
    incoming = profile_payload()
    incoming["identity"]["name"] = "另一个名字"
    response = client.post("/v1/profiles/reconcile", json={"base_profile": profile_payload(), "incoming_profile": incoming})
    assert response.status_code == 200
    body = response.json()
    assert body["profile"]["identity"]["name"] == "张三"
    assert any(item["path"] == "/identity/name" for item in body["conflicts"])


def test_parse_text_returns_profile_and_evidence():
    client = TestClient(app)
    with patch("applypilot.api.app.ResumeIngestionService.parse_text", new_callable=AsyncMock) as parse_text:
        from applypilot.domain.profile import CandidateProfile

        parse_text.return_value = CandidateProfile.model_validate(profile_payload())
        response = client.post("/v1/profiles/parse", json={"text": "张三 北京大学 新东方", "source_name": "resume.txt"})
    assert response.status_code == 200
    body = response.json()
    assert body["profile_draft"]["profile_id"].startswith("cand_")
    name_fact = next(item for item in body["facts"] if item["path"] == "/identity/name")
    assert name_fact["source"]["quote"] == "张三"
    assert name_fact["confidence"] == 1


def test_parse_multipart_resume_file_uses_ingestion_service():
    client = TestClient(app)
    from applypilot.domain.profile import CandidateProfile

    with patch("applypilot.api.app.ResumeIngestionService.parse_file", new_callable=AsyncMock) as parse_file:
        parse_file.return_value = CandidateProfile.model_validate(profile_payload())
        response = client.post("/v1/profiles/parse", files={"file": ("resume.pdf", b"%PDF-1.4", "application/pdf")})
    assert response.status_code == 200
    assert parse_file.await_count == 1
    assert response.json()["facts"][0]["source"]["document"] == "resume.pdf"


def test_form_plan_redacts_sensitive_value_without_explicit_authorization():
    client = TestClient(app)
    page = page_payload()
    page["fields"].insert(1, {"field_ref": "f-id", "label": "身份证号", "kind": "text", "required": True})
    response = client.post("/v1/forms/plan", json={"profile": profile_payload(), "page": page, "policy": {"fill_required_only": True, "allow_sensitive_paths": []}})
    assert response.status_code == 200
    item = next(item for item in response.json()["plan"] if item["field_ref"] == "f-id")
    assert item["decision"] == "review"
    assert item["value"] is None
    assert item["reason"] == "敏感字段未获得本次授权"


def test_feedback_accepts_only_redacted_mapping_metadata():
    client = TestClient(app)
    response = client.post("/v1/forms/feedback", json={"field_signature": "sha256:field", "section_signature": "sha256:section", "control_kind": "text", "options_signature": None, "corrected_profile_path": "/experiences/0/org_name", "mapping_version": "rules-test"})
    assert response.status_code == 200
    assert response.json()["accepted"] is True
    rejected = client.post("/v1/forms/feedback", json={"field_signature": "field", "control_kind": "text", "corrected_profile_path": "identity.name", "mapping_version": "rules-test"})
    assert rejected.status_code == 422
