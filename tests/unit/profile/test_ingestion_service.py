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
        "experiences": [],
        "projects": [],
        "skills": [],
    }


@pytest.mark.asyncio
async def test_parse_text_success(sample_profile_dict):
    service = ResumeIngestionService(api_key="test_api_key")

    mock_resp = _mock_llm_response(sample_profile_dict)
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        profile = await service.parse_text("张三的简历文本内容")

        assert isinstance(profile, CandidateProfile)
        assert profile.profile_id == "cand_zhangsan"
        assert profile.identity.name == "张三"
        assert profile.contact.email == "zhangsan@example.com"
        assert len(profile.education) == 1
        assert profile.education[0].school_name == "清华大学"


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
async def test_parse_text_missing_profile_id_defaults(sample_profile_dict):
    service = ResumeIngestionService(api_key="test_api_key")
    del sample_profile_dict["profile_id"]

    mock_resp = _mock_llm_response(sample_profile_dict)
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        profile = await service.parse_text("简历文本")
        assert profile.profile_id == "cand_profile"


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
