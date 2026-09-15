import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest

from applypilot.domain.profile import CandidateProfile
from applypilot.modules.profile.ingestion.service import (
    ResumeIngestionError,
    ResumeIngestionService,
)


def _mock_llm_response(data: dict, status_code: int = 200) -> httpx.Response:
    content = json.dumps(
        {
            "id": "chatcmpl-test",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(data, ensure_ascii=False),
                    },
                    "finish_reason": "stop",
                }
            ],
        }
    )
    return httpx.Response(
        status_code=status_code,
        content=content.encode("utf-8"),
        request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
    )


@pytest.fixture
def sample_profile_dict() -> dict:
    return {
        "schema_version": "1.1.0",
        "profile_id": "cand_zhangsan",
        "identity": {
            "name": "张三",
            "gender": "male",
            "birth_date": "2001-05-15",
        },
        "contact": {
            "mobile": "13800138000",
            "email": "zhangsan@example.com",
            "current_city": "北京",
        },
        "education": [
            {
                "id": "edu_bachelor",
                "school_name": "清华大学",
                "education_level": "bachelor",
                "major": "计算机科学与技术",
                "start_date": "2019-09",
                "end_date": "2023-06",
            }
        ],
        "experiences": [
            {
                "id": "exp_1",
                "org_name": "阿里巴巴",
                "title": "算法工程师实习生",
                "experience_type": "internship",
                "start_date": "2024-06",
                "end_date": "2024-12",
                "description_bullets": ["负责大模型 RAG 系统开发与优化"],
            }
        ],
        "projects": [
            {
                "id": "proj_1",
                "project_name": "智能问答系统",
                "role": "核心开发者",
                "summary": "基于 LangChain 的招聘问答系统",
                "start_date": "2023-10",
                "end_date": "2024-05",
            }
        ],
        "skills": [
            {
                "skill_id": "skill_1",
                "name": "Python",
                "category": "programming",
            }
        ],
    }


def test_service_repr_masks_api_key():
    svc_with_key = ResumeIngestionService(api_key="sk-secret-123456789")
    r1 = repr(svc_with_key)
    assert "sk-secret-123456789" not in r1
    assert "api_key='***'" in r1

    svc_no_key = ResumeIngestionService(api_key="")
    r2 = repr(svc_no_key)
    assert "api_key='None'" in r2


def test_missing_profile_id_is_derived_from_profile_content():
    first = ResumeIngestionService._normalize_profile_dict({"identity": {"name": "甲"}})
    second = ResumeIngestionService._normalize_profile_dict({"identity": {"name": "乙"}})
    assert first["profile_id"] != second["profile_id"]
    assert first["profile_id"].startswith("cand_")

    empty_first = ResumeIngestionService._normalize_profile_dict({})
    empty_second = ResumeIngestionService._normalize_profile_dict({})
    assert empty_first["profile_id"] != empty_second["profile_id"]


def test_model_supplied_profile_ids_are_replaced_with_content_derived_ids():
    first = ResumeIngestionService._normalize_profile_dict(
        {"profile_id": "cand_001", "identity": {"name": "甲"}}
    )
    second = ResumeIngestionService._normalize_profile_dict(
        {"profile_id": "cand_001", "identity": {"name": "乙"}}
    )
    assert first["profile_id"] != second["profile_id"]
    assert first["profile_id"].startswith("cand_")


def test_profile_id_derivation_normalizes_aliases_before_hashing():
    canonical = ResumeIngestionService._normalize_profile_dict(
        {"identity": {"name": "甲"}, "experiences": [{"org_name": "公司", "title": "工程师"}]}
    )
    aliases = ResumeIngestionService._normalize_profile_dict(
        {"identity": {"name": "甲"}, "experiences": [{"company_name": "公司", "job_title": "工程师"}]}
    )
    assert canonical["profile_id"] == aliases["profile_id"]


def test_profile_id_stays_stable_when_non_identity_facts_change():
    first = ResumeIngestionService._normalize_profile_dict(
        {"identity": {"name": "甲"}, "skills": [{"name": "Python", "category": "programming"}]}
    )
    updated = ResumeIngestionService._normalize_profile_dict(
        {"identity": {"name": "甲"}, "skills": [{"name": "Rust", "category": "programming"}]}
    )
    assert first["profile_id"] == updated["profile_id"]


def test_normalize_structured_resume_records_adds_ids_and_publication_aliases():
    normalized = ResumeIngestionService._normalize_profile_dict(
        {
            "identity": {"name": "甲"},
            "awards": [{"award_name": "一等奖学金", "date": "2025"}],
            "publications": [{"name": "NAS 2026", "venue": "CCF-C"}],
            "certificates": [{"name": "英语六级"}],
            "campus_practices": [{"name": "志愿服务"}],
        }
    )
    assert normalized["awards"][0]["id"] == "award_1"
    assert normalized["awards"][0]["name"] == "一等奖学金"
    assert normalized["publications"][0] == {"venue": "CCF-C", "id": "pub_1", "title": "NAS 2026"}
    assert normalized["certificates"][0]["id"] == "cert_1"
    assert normalized["campus_practices"][0]["id"] == "practice_1"


@pytest.mark.asyncio
async def test_parse_text_empty_or_whitespace_raises_error():
    service = ResumeIngestionService(api_key="test_api_key")

    with pytest.raises(ResumeIngestionError, match="Extracted resume text is empty"):
        await service.parse_text("")

    with pytest.raises(ResumeIngestionError, match="Extracted resume text is empty"):
        await service.parse_text("   \n\t  \n ")


@pytest.mark.asyncio
async def test_parse_text_success(sample_profile_dict):
    service = ResumeIngestionService(api_key="test_api_key")

    mock_resp = _mock_llm_response(sample_profile_dict)
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        profile = await service.parse_text("张三的简历文本内容")

        assert isinstance(profile, CandidateProfile)
        assert profile.profile_id.startswith("cand_")
        assert profile.profile_id != "cand_zhangsan"
        assert profile.identity.name == "张三"
        assert profile.contact.email == "zhangsan@example.com"
        assert len(profile.education) == 1
        assert profile.education[0].school_name == "清华大学"
        assert len(profile.experiences) == 1
        assert profile.experiences[0].org_name == "阿里巴巴"
        assert len(profile.projects) == 1
        assert profile.projects[0].project_name == "智能问答系统"
        assert len(profile.skills) == 1
        assert profile.skills[0].name == "Python"


@pytest.mark.asyncio
async def test_parse_text_markdown_json_cleaning(sample_profile_dict):
    service = ResumeIngestionService(api_key="test_api_key")

    wrapped_content = f"```json\n{json.dumps(sample_profile_dict, ensure_ascii=False)}\n```"
    raw_api_response = {
        "id": "chatcmpl-test",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": wrapped_content,
                }
            }
        ],
    }
    mock_resp = httpx.Response(
        status_code=200,
        content=json.dumps(raw_api_response).encode("utf-8"),
        request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        profile = await service.parse_text("简历文本")
        assert profile.identity.name == "张三"


@pytest.mark.asyncio
async def test_parse_text_preamble_postamble_wrapped_json(sample_profile_dict):
    service = ResumeIngestionService(api_key="test_api_key")

    conversational_content = (
        "Here is the parsed JSON profile for the candidate:\n"
        f"{json.dumps(sample_profile_dict, ensure_ascii=False)}\n"
        "Please let me know if you need further adjustments!"
    )
    raw_api_response = {
        "id": "chatcmpl-test",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": conversational_content,
                }
            }
        ],
    }
    mock_resp = httpx.Response(
        status_code=200,
        content=json.dumps(raw_api_response).encode("utf-8"),
        request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        profile = await service.parse_text("简历文本")
        assert profile.identity.name == "张三"
        assert profile.experiences[0].org_name == "阿里巴巴"


@pytest.mark.asyncio
async def test_parse_text_defensive_normalization():
    service = ResumeIngestionService(api_key="test_api_key")

    # LLM output with common discrepancies:
    # - company_name instead of org_name
    # - job_title instead of title
    # - missing id in experiences and projects
    # - missing summary in projects
    # - id instead of skill_id in skills
    raw_discrepant_data = {
        "identity": {"name": "李四"},
        "experiences": [
            {
                "company_name": "腾讯",
                "job_title": "后端开发工程师",
                "experience_type": "full_time",
                "start_date": "2023-07",
            }
        ],
        "projects": [
            {
                "project_name": "分布式存储系统",
                "role": "主程",
                "start_date": "2022-09",
            }
        ],
        "skills": [
            {
                "id": "skill_go",
                "name": "Golang",
                "category": "programming",
            }
        ],
    }

    mock_resp = _mock_llm_response(raw_discrepant_data)
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        profile = await service.parse_text("李四的简历")

        assert profile.profile_id.startswith("cand_")
        assert profile.identity.name == "李四"
        assert len(profile.experiences) == 1
        assert profile.experiences[0].id == "exp_1"
        assert profile.experiences[0].org_name == "腾讯"
        assert profile.experiences[0].title == "后端开发工程师"
        assert len(profile.projects) == 1
        assert profile.projects[0].id == "proj_1"
        assert profile.projects[0].summary == "分布式存储系统"
        assert len(profile.skills) == 1
        assert profile.skills[0].skill_id == "skill_go"
        assert profile.skills[0].name == "Golang"


@pytest.mark.asyncio
async def test_parse_text_missing_profile_id_defaults(sample_profile_dict):
    service = ResumeIngestionService(api_key="test_api_key")
    del sample_profile_dict["profile_id"]

    mock_resp = _mock_llm_response(sample_profile_dict)
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        profile = await service.parse_text("简历文本")
        assert profile.profile_id.startswith("cand_")


@pytest.mark.asyncio
async def test_parse_text_missing_api_key_raises_error(monkeypatch):
    monkeypatch.delenv("APPLYPILOT_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    service = ResumeIngestionService()
    with pytest.raises(ResumeIngestionError, match="No API key provided"):
        await service.parse_text("简历内容")


@pytest.mark.asyncio
async def test_parse_file_tex(tmp_path: Path, sample_profile_dict):
    service = ResumeIngestionService(api_key="test_api_key")

    tex_file = tmp_path / "resume.tex"
    tex_file.write_text(r"\textbf{张三} 清华大学", encoding="utf-8")

    mock_resp = _mock_llm_response(sample_profile_dict)
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        profile = await service.parse_file(tex_file)
        assert profile.identity.name == "张三"


@pytest.mark.asyncio
async def test_parse_file_pdf(tmp_path: Path, sample_profile_dict):
    service = ResumeIngestionService(api_key="test_api_key")

    pdf_file = tmp_path / "resume.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy")

    mock_resp = _mock_llm_response(sample_profile_dict)
    with patch(
        "applypilot.modules.profile.ingestion.extractors.PdfExtractor.extract_text",
        return_value="张三 清华大学",
    ), patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        profile = await service.parse_file(pdf_file)
        assert profile.identity.name == "张三"


@pytest.mark.asyncio
async def test_parse_file_non_existent(tmp_path: Path):
    service = ResumeIngestionService(api_key="test_api_key")
    with pytest.raises(FileNotFoundError, match="Resume file not found"):
        await service.parse_file(tmp_path / "not_found.pdf")


@pytest.mark.asyncio
async def test_parse_file_unsupported_format(tmp_path: Path):
    service = ResumeIngestionService(api_key="test_api_key")
    docx_file = tmp_path / "resume.docx"
    docx_file.write_text("dummy", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported resume file format: .docx"):
        await service.parse_file(docx_file)


@pytest.mark.asyncio
async def test_parse_text_http_error_wrapped():
    service = ResumeIngestionService(api_key="test_api_key")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.ConnectTimeout("Connection timed out")
        with pytest.raises(ResumeIngestionError, match="LLM API request failed"):
            await service.parse_text("简历文本")


@pytest.mark.asyncio
async def test_parse_text_malformed_json_wrapped():
    service = ResumeIngestionService(api_key="test_api_key")

    mock_resp = httpx.Response(
        status_code=200,
        content=json.dumps(
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "This is definitely not valid JSON",
                        }
                    }
                ]
            }
        ).encode("utf-8"),
        request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with pytest.raises(ResumeIngestionError, match="Failed to parse LLM response as JSON"):
            await service.parse_text("简历文本")


@pytest.mark.asyncio
async def test_parse_text_validation_error_wrapped():
    service = ResumeIngestionService(api_key="test_api_key")

    # Invalid payload (education is a string, schema requires list)
    invalid_data = {
        "profile_id": "cand_invalid",
        "education": "Not a list",
    }
    mock_resp = _mock_llm_response(invalid_data)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with pytest.raises(ResumeIngestionError, match="Profile validation failed"):
            await service.parse_text("简历文本")
