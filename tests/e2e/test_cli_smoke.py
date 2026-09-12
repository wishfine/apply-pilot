import json
from pathlib import Path
from typer.testing import CliRunner

from applypilot.cli.main import app

runner = CliRunner()


def test_cli_help_smoke():
    res = runner.invoke(app, ["--help"])
    assert res.exit_code == 0
    assert "ApplyPilot" in res.stdout
    assert "profile" in res.stdout
    assert "apply" in res.stdout
    assert "track" in res.stdout


def test_cli_version():
    res = runner.invoke(app, ["--version"])
    assert res.exit_code == 0
    assert "ApplyPilot v0.1.0" in res.stdout


def test_profile_subcommands_help():
    res = runner.invoke(app, ["profile", "--help"])
    assert res.exit_code == 0
    assert "validate" in res.stdout
    assert "show" in res.stdout
    assert "import" in res.stdout


def test_apply_subcommands_help():
    res = runner.invoke(app, ["apply", "--help"])
    assert res.exit_code == 0
    assert "run" in res.stdout


def test_track_subcommands_help():
    res = runner.invoke(app, ["track", "--help"])
    assert res.exit_code == 0
    assert "status" in res.stdout


def test_profile_validate_command(tmp_path: Path):
    profile_data = {
        "profile_id": "cand_cli_01",
        "identity": {
            "name": "李四",
            "gender": "male",
            "birth_date": "2000-01-01",
        },
        "contact": {
            "mobile": "13900139000",
            "email": "lisi@example.com",
            "current_city": "上海",
        },
    }
    profile_file = tmp_path / "profile.json"
    profile_file.write_text(json.dumps(profile_data, ensure_ascii=False), encoding="utf-8")

    res = runner.invoke(app, ["profile", "validate", "-p", str(profile_file)])
    assert res.exit_code == 0
    assert "李四" in res.stdout


def test_profile_show_command(tmp_path: Path):
    profile_data = {
        "profile_id": "cand_cli_02",
        "identity": {
            "name": "王五",
            "gender": "female",
        },
        "contact": {
            "mobile": "13700137000",
            "email": "wangwu@example.com",
            "current_city": "深圳",
        },
    }
    profile_file = tmp_path / "profile.json"
    profile_file.write_text(json.dumps(profile_data, ensure_ascii=False), encoding="utf-8")

    res = runner.invoke(app, ["profile", "show", "--path", str(profile_file)])
    assert res.exit_code == 0
    assert "王五" in res.stdout


def test_apply_run_command_output():
    res = runner.invoke(
        app,
        ["apply", "run", "--job-url", "https://jobs.example.com/apply/123"],
    )
    assert res.exit_code == 0
    assert "https://jobs.example.com/apply/123" in res.stdout


def test_track_list_command():
    res = runner.invoke(app, ["track", "list"])
    assert res.exit_code == 0


def test_track_status_command():
    res = runner.invoke(app, ["track", "status", "app_12345"])
    assert res.exit_code == 0
    assert "app_12345" in res.stdout


def test_profile_validate_missing_file():
    res = runner.invoke(app, ["profile", "validate", "-p", "non_existent_path.yaml"])
    assert res.exit_code == 1
    assert "Validation failed" in res.stdout


def test_profile_validate_yaml(tmp_path: Path):
    yaml_content = """
profile_id: cand_yaml_01
identity:
  name: 张三
  gender: male
  birth_date: 2001-05-15
contact:
  email: zhangsan@example.com
  mobile: "13800138000"
  current_city: 北京
"""
    yaml_file = tmp_path / "profile.yaml"
    yaml_file.write_text(yaml_content.strip(), encoding="utf-8")

    res = runner.invoke(app, ["profile", "validate", "-p", str(yaml_file)])
    assert res.exit_code == 0
    assert "张三" in res.stdout
    assert "Profile validated successfully!" in res.stdout


def test_profile_show_missing_file():
    res = runner.invoke(app, ["profile", "show", "--path", "non_existent_profile.yaml"])
    assert res.exit_code == 1
    assert "No profile found" in res.stdout


def test_track_list_and_status_with_database(tmp_path: Path, monkeypatch):
    import asyncio
    from applypilot.storage.database import init_db
    from applypilot.storage.repositories import ApplicationRepository

    db_file = tmp_path / "applypilot.db"
    asyncio.run(init_db(db_file))

    app_repo = ApplicationRepository(db_file)
    asyncio.run(
        app_repo.create_application(
            app_id="app_db_01",
            application_key="cand_1:app_db_01:2027",
            candidate_id="cand_1",
            canonical_job_id="job_algo_01",
            company_name="字节跳动",
            job_title="大模型算法工程师",
            recruitment_cycle="2027-campus",
            status="applied",
            current_stage="resume_screen",
        )
    )

    monkeypatch.setenv("APPLYPILOT_HOME", str(tmp_path))

    # Test track list with -s filter
    res_list = runner.invoke(app, ["track", "list", "-s", "applied"])
    assert res_list.exit_code == 0
    assert "字节跳动" in res_list.stdout
    assert "app_db_01" in res_list.stdout
    assert "applied" in res_list.stdout

    # Test track status
    res_status = runner.invoke(app, ["track", "status", "app_db_01"])
    assert res_status.exit_code == 0
    assert "字节跳动" in res_status.stdout
    assert "大模型算法工程师" in res_status.stdout
    assert "applied" in res_status.stdout
