from pathlib import Path
from unittest.mock import AsyncMock, patch
from typer.testing import CliRunner
import yaml

from applypilot.cli.main import app
from applypilot.domain.base import PartialDate
from applypilot.domain.profile import (
    CandidateProfile,
    ContactInfo,
    EducationLevel,
    EducationRecord,
    ExperienceRecord,
    ExperienceType,
    IdentityInfo,
    ProjectRecord,
    SkillRecord,
)
from applypilot.modules.profile.ingestion.service import ResumeIngestionError

runner = CliRunner()


def _create_mock_profile() -> CandidateProfile:
    return CandidateProfile(
        schema_version="1.1.0",
        profile_id="cand_test_01",
        identity=IdentityInfo(name="赵六", gender="male", birth_date=PartialDate(year=2001, month=3)),
        contact=ContactInfo(mobile="13600136000", email="zhaoliu@example.com", current_city="杭州"),
        education=[
            EducationRecord(
                id="edu_bachelor",
                school_name="浙江大学",
                education_level=EducationLevel.BACHELOR,
                major="软件工程",
                start_date=PartialDate(year=2019, month=9),
                end_date=PartialDate(year=2023, month=6),
            )
        ],
        experiences=[
            ExperienceRecord(
                id="exp_1",
                org_name="网易",
                title="Python 后端开发",
                experience_type=ExperienceType.INTERNSHIP,
                start_date=PartialDate(year=2022, month=7),
                end_date=PartialDate(year=2023, month=1),
                description_bullets=["参与微服务重构与性能压测"],
            )
        ],
        projects=[
            ProjectRecord(
                id="proj_1",
                project_name="智能分发平台",
                role="架构师",
                summary="高可用任务调度系统",
                start_date=PartialDate(year=2022, month=10),
                end_date=PartialDate(year=2023, month=4),
            )
        ],
        skills=[
            SkillRecord(
                skill_id="skill_python",
                name="Python",
                category="programming",
            )
        ],
    )


def test_profile_import_help():
    res = runner.invoke(app, ["profile", "import", "--help"])
    assert res.exit_code == 0
    assert "--file" in res.stdout
    assert "--output" in res.stdout
    assert "--model" in res.stdout
    assert "--base-url" in res.stdout
    assert "--api-key" in res.stdout


def test_profile_import_success(tmp_path: Path):
    resume_file = tmp_path / "resume.tex"
    resume_file.write_text(r"\textbf{赵六} 浙江大学", encoding="utf-8")
    output_file = tmp_path / "imported_profile.yaml"

    mock_profile = _create_mock_profile()

    with patch(
        "applypilot.modules.profile.ingestion.service.ResumeIngestionService.parse_file",
        new_callable=AsyncMock,
    ) as mock_parse:
        mock_parse.return_value = mock_profile

        res = runner.invoke(
            app,
            [
                "profile",
                "import",
                "-f",
                str(resume_file),
                "-o",
                str(output_file),
                "--model",
                "deepseek-chat",
                "--api-key",
                "sk-test",
            ],
        )

        assert res.exit_code == 0
        assert "Profile successfully imported to" in res.stdout
        assert "赵六" in res.stdout
        assert "zhaoliu@example.com" in res.stdout
        assert "13600136000" in res.stdout
        assert output_file.exists()

        content = yaml.safe_load(output_file.read_text(encoding="utf-8"))
        validated = CandidateProfile.model_validate(content)
        assert validated.identity.name == "赵六"
        assert len(validated.education) == 1
        assert len(validated.experiences) == 1
        assert len(validated.projects) == 1
        assert len(validated.skills) == 1


def test_profile_import_default_output_path(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APPLYPILOT_HOME", str(tmp_path))

    resume_file = tmp_path / "resume.pdf"
    resume_file.write_bytes(b"%PDF-1.4 dummy")

    mock_profile = _create_mock_profile()

    with patch(
        "applypilot.modules.profile.ingestion.service.ResumeIngestionService.parse_file",
        new_callable=AsyncMock,
    ) as mock_parse:
        mock_parse.return_value = mock_profile

        res = runner.invoke(app, ["profile", "import", "-f", str(resume_file)])

        assert res.exit_code == 0
        default_output = tmp_path / "profile.yaml"
        assert default_output.exists()


def test_profile_import_non_existent_file(tmp_path: Path):
    missing_file = tmp_path / "non_existent.pdf"
    res = runner.invoke(app, ["profile", "import", "-f", str(missing_file)])
    assert res.exit_code == 1
    assert "File not found" in res.stdout or "not found" in res.stdout.lower()


def test_profile_import_ingestion_error(tmp_path: Path):
    resume_file = tmp_path / "corrupt.pdf"
    resume_file.write_bytes(b"corrupt")

    with patch(
        "applypilot.modules.profile.ingestion.service.ResumeIngestionService.parse_file",
        new_callable=AsyncMock,
    ) as mock_parse:
        mock_parse.side_effect = ResumeIngestionError("Failed to parse LLM response as JSON")

        res = runner.invoke(app, ["profile", "import", "-f", str(resume_file)])
        assert res.exit_code == 1
        assert "Import failed" in res.stdout or "Failed to parse LLM response" in res.stdout
