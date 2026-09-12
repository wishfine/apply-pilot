"""ApplyPilot command-line interface entry point.

Provides CLI command groups:
- profile: Manage candidate fact base and resume variants.
- apply: Automate job application form filling and human review.
- track: Track application lifecycle and view audit logs.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse
import uuid

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
import typer
import yaml

from applypilot.browser import PlaywrightBackend
from applypilot.core.config import get_app_home_dir, get_browser_dir, get_db_path
from applypilot.domain.job import ApplicationStatus, ApplicationTarget, Job
from applypilot.domain.profile import CandidateProfile
from applypilot.domain.variant import ResumeVariant
from applypilot.modules.apply.engine import ApplyEngine
from applypilot.modules.apply.readiness import (
    ProfileWritebackSynchronizer,
    ReadinessReport,
)
from applypilot.modules.profile.ingestion import (
    ResumeIngestionError,
    ResumeIngestionService,
)
from applypilot.storage.database import init_db
from applypilot.storage.repositories import ApplicationRepository, EventRepository

app = typer.Typer(
    name="applypilot",
    help="ApplyPilot: A local-first AI job application agent for Chinese recruitment platforms.",
    no_args_is_help=True,
)
console = Console()

profile_app = typer.Typer(
    name="profile",
    help="Manage candidate fact base and resume variants.",
    no_args_is_help=True,
)
app.add_typer(profile_app, name="profile")

apply_app = typer.Typer(
    name="apply",
    help="Automate job application form filling and human review.",
    no_args_is_help=True,
)
app.add_typer(apply_app, name="apply")

track_app = typer.Typer(
    name="track",
    help="Track application lifecycle and view audit logs.",
    no_args_is_help=True,
)
app.add_typer(track_app, name="track")


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print("ApplyPilot v0.1.0")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        help="Show version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """ApplyPilot: One profile. Every application."""


def _load_profile(path: Path) -> CandidateProfile:
    """Load and parse candidate profile from YAML or JSON."""
    if not path.exists():
        raise FileNotFoundError(f"Profile file not found at: {path}")
    content = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(content)
    else:
        data = yaml.safe_load(content)
    return CandidateProfile.model_validate(data)


@profile_app.command("validate")
def profile_validate(
    path: Path = typer.Option(..., "--path", "-p", help="Path to profile.yaml/json"),
) -> None:
    """Validate candidate profile fact base."""
    try:
        profile = _load_profile(path)
        console.print(f"[bold green]Profile validated successfully![/bold green]")
        console.print(
            f"Candidate: [bold]{profile.identity.name}[/bold] ({profile.profile_id})"
        )
        console.print(f"Education records: {len(profile.education)}")
        console.print(f"Experience records: {len(profile.experiences)}")
        console.print(f"Project records: {len(profile.projects)}")
    except Exception as e:
        console.print(f"[bold red]Validation failed: {e}[/bold red]")
        raise typer.Exit(code=1)


@profile_app.command("show")
def profile_show(
    path: Optional[Path] = typer.Option(
        None, "--path", "-p", help="Path to profile.yaml/json"
    ),
) -> None:
    """Show candidate profile summary."""
    profile_path = path or (get_app_home_dir() / "profile.yaml")
    if not profile_path.exists():
        console.print(f"[bold red]No profile found at: {profile_path}[/bold red]")
        raise typer.Exit(code=1)

    try:
        profile = _load_profile(profile_path)
        console.print(f"[bold cyan]Candidate Profile Summary[/bold cyan]")
        console.print(f"Name: [bold]{profile.identity.name}[/bold]")
        console.print(f"Email: {profile.contact.email}")
        console.print(f"Mobile: {profile.contact.mobile}")
        console.print(f"City: {profile.contact.current_city or 'N/A'}")
    except Exception as e:
        console.print(f"[bold red]Failed to load profile: {e}[/bold red]")
        raise typer.Exit(code=1)


@profile_app.command("import")
def profile_import(
    file: Path = typer.Option(..., "--file", "-f", help="Path to resume file (.pdf or .tex)"),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Path to output profile.yaml (defaults to ~/.applypilot/profile.yaml)"
    ),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="LLM model name"),
    base_url: Optional[str] = typer.Option(None, "--base-url", "-b", help="LLM API base URL"),
    api_key: Optional[str] = typer.Option(None, "--api-key", "-k", help="LLM API key"),
) -> None:
    """Import and structure a resume file into CandidateProfile YAML."""
    if not file.exists() or not file.is_file():
        console.print(f"[bold red]File not found: {file}[/bold red]")
        raise typer.Exit(code=1)

    output_path = output or (get_app_home_dir() / "profile.yaml")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    console.print(f"[bold blue]Importing resume from: {file}[/bold blue]")
    service = ResumeIngestionService(api_key=api_key, base_url=base_url, model=model)

    try:
        profile = asyncio.run(service.parse_file(file))
        yaml_str = yaml.safe_dump(
            profile.model_dump(mode="json", exclude_none=True),
            allow_unicode=True,
            sort_keys=False,
        )
        output_path.write_text(yaml_str, encoding="utf-8")

        console.print(f"[bold green]Profile successfully imported to: {output_path}[/bold green]")
        console.print(
            f"Candidate: [bold]{profile.identity.name or 'N/A'}[/bold] ({profile.profile_id})"
        )
        if profile.contact.email:
            console.print(f"Email: {profile.contact.email}")
        if profile.contact.mobile:
            console.print(f"Mobile: {profile.contact.mobile}")
        console.print(f"Education records: {len(profile.education)}")
        console.print(f"Experience records: {len(profile.experiences)}")
        console.print(f"Project records: {len(profile.projects)}")
        console.print(f"Skill records: {len(profile.skills)}")
    except Exception as e:
        console.print(f"[bold red]Import failed: {e}[/bold red]")
        raise typer.Exit(code=1)


def _update_in_memory_profile(prof: Any, path: str, val: Any) -> None:
    """Navigate dot-separated profile path and update attribute in-memory."""
    if not path or "[" in path or "]" in path:
        return
    parts = path.strip().split(".")
    target = prof
    for part in parts[:-1]:
        if hasattr(target, part):
            target = getattr(target, part)
        elif isinstance(target, dict) and part in target:
            target = target[part]
        else:
            return
    last_key = parts[-1]
    if hasattr(target, last_key):
        setattr(target, last_key, val)
    elif isinstance(target, dict):
        target[last_key] = val


@apply_app.command("run")
def apply_run(
    job_url: str = typer.Option(..., "--job-url", "-u", help="Job recruitment URL"),
    profile_path: Optional[Path] = typer.Option(
        None, "--profile", "-p", help="Path to candidate profile yaml/json"
    ),
    headless: bool = typer.Option(
        False, "--headless", help="Run browser in headless mode"
    ),
    interactive_readiness: bool = typer.Option(
        True,
        "--interactive-readiness/--no-interactive-readiness",
        help="Enable interactive resolution for missing required fields",
    ),
) -> None:
    """Automate job application form filling and human review."""
    console.print(f"[bold blue]Starting ApplyPilot session for: {job_url}[/bold blue]")
    console.print(f"Headless mode: {headless}")
    console.print(f"Interactive readiness: {interactive_readiness}")
    if profile_path:
        console.print(f"Using profile from: {profile_path}")

    try:
        # 1. Locate candidate profile
        prof_path = profile_path or (get_app_home_dir() / "profile.yaml")
        if not prof_path.exists():
            console.print(
                f"[bold red]Profile file not found at: {prof_path}. Please create one or import using 'applypilot profile import -f <resume>'.[/bold red]"
            )
            raise typer.Exit(code=1)

        # 2. Load and validate profile
        profile = _load_profile(prof_path)

        # 3. Local database path
        db_path = get_db_path()

        # 4. Build Job and ApplicationTarget
        domain = urlparse(job_url).netloc or "target_company"
        job = Job(
            job_id=f"job_{uuid.uuid4().hex[:8]}",
            title=f"Application at {domain}",
            company_name=domain,
            description_raw="Automated job application via ApplyPilot CLI",
            source_channel="url",
            source_url=job_url,
            apply_url=job_url,
        )
        target = ApplicationTarget(target_id=f"tgt_{uuid.uuid4().hex[:8]}", job=job)

        # 5. Single async event loop runner driving the entire execution session
        async def _run_session() -> None:
            await init_db(db_path)
            browser = PlaywrightBackend(
                headless=headless,
                user_data_dir=get_browser_dir(),
                user_prompt_handler=lambda reason: typer.prompt(
                    f"\n[ApplyPilot] {reason}\n[按回车键继续]",
                    default="",
                    show_default=False,
                ),
            )

            async def terminal_readiness_resolver(
                page: Any,
                report: ReadinessReport,
                prof: CandidateProfile,
                var: Optional[ResumeVariant],
            ) -> Any:
                table = Table(title="⚠️  阶段就绪度诊断：发现必填项缺失", border_style="yellow")
                table.add_column("字段标识", style="cyan")
                table.add_column("表单标签", style="bold")
                table.add_column("所属板块", style="magenta")
                table.add_column("建议修复", style="green")
                for item in report.missing_required:
                    table.add_row(
                        item.field_sig,
                        item.label,
                        item.section_title or "-",
                        item.suggested_fix or "-",
                    )
                console.print(table)
                console.print("\n请选择处理方式：")
                console.print("[bold cyan][1][/bold cyan] 切换至浏览器手动补填")
                console.print("[bold cyan][2][/bold cyan] 终端逐项即时补全并回写档案")
                console.print("[bold cyan][3][/bold cyan] 暂停并退出本次网申 (PAUSED)")
                choice = typer.prompt("请输入选项 [1/2/3]", default="1")
                if choice == "3":
                    return ApplicationStatus.PAUSED
                elif choice == "2":
                    for item in report.missing_required:
                        val = typer.prompt(f"请输入 [{item.label}]")
                        if val:
                            if item.profile_path:
                                try:
                                    ProfileWritebackSynchronizer.sync_field(
                                        prof_path, item.profile_path, val
                                    )
                                    console.print(
                                        f"[green]已同步回写 {item.profile_path} = {val}[/green]"
                                    )
                                except Exception as e:
                                    console.print(f"[yellow]回写失败: {e}[/yellow]")

                                try:
                                    _update_in_memory_profile(prof, item.profile_path, val)
                                except Exception:
                                    pass

                            # Fill into DOM page element if element is accessible
                            if page is not None and hasattr(page, "find"):
                                element = None
                                for sel in (
                                    f"#{item.field_sig}",
                                    f"[name='{item.field_sig}']",
                                    item.field_sig,
                                    f"[id*='{item.field_sig}']",
                                    f"[name*='{item.field_sig}']",
                                ):
                                    try:
                                        res = page.find(sel)
                                        if inspect.isawaitable(res):
                                            res = await res
                                        if res:
                                            element = res
                                            break
                                    except Exception:
                                        continue

                                if element is not None:
                                    try:
                                        if hasattr(element, "clear_text"):
                                            c_res = element.clear_text()
                                            if inspect.isawaitable(c_res):
                                                await c_res
                                        if hasattr(element, "type_text"):
                                            t_res = element.type_text(str(val))
                                            if inspect.isawaitable(t_res):
                                                await t_res
                                    except Exception as e:
                                        console.print(f"[yellow]页面控件填充提示: {e}[/yellow]")

                    return True
                else:
                    if hasattr(browser, "wait_for_user"):
                        wait_res = browser.wait_for_user(
                            "请在已打开的浏览器中完成上述必填项填写，完成后按回车继续..."
                        )
                        if inspect.isawaitable(wait_res):
                            await wait_res
                    return True

            engine = ApplyEngine(
                db_path=db_path,
                browser_backend=browser,
                interactive_readiness=interactive_readiness,
                readiness_resolver=terminal_readiness_resolver if interactive_readiness else None,
            )
            try:
                status = await engine.run_application_target(target, profile)
                if status == ApplicationStatus.READY_REVIEW:
                    console.print(
                        Panel(
                            "[bold green]🎉 表单已自动化填写完毕！已进入终审阶段 (READY_REVIEW)。[/bold green]\n"
                            "请在已打开的浏览器中核对各项表单，核对无误后请亲自点击提交。",
                            title="终审确认",
                            border_style="green",
                        )
                    )
                    if not headless and hasattr(browser, "wait_for_user"):
                        wait_res = browser.wait_for_user(
                            "请在浏览器中核对并点击提交。提交完毕后，按回车退出浏览器..."
                        )
                        if inspect.isawaitable(wait_res):
                            await wait_res
                elif status == ApplicationStatus.PAUSED:
                    console.print(
                        Panel(
                            "[bold yellow]⏸️  网申已暂停 (PAUSED)，已保存阶段断点 Checkpoint。[/bold yellow]\n"
                            "后续可通过 track 查看或恢复。",
                            title="网申暂停",
                            border_style="yellow",
                        )
                    )
            finally:
                if hasattr(browser, "close"):
                    close_res = browser.close()
                    if inspect.isawaitable(close_res):
                        await close_res

        asyncio.run(_run_session())

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[bold red]Execution error: {e}[/bold red]")
        raise typer.Exit(code=1)


async def _query_applications(
    db_path: Path, status: Optional[str] = None
) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    try:
        repo = ApplicationRepository(db_path)
        return await repo.list_applications(status=status)
    except Exception:
        return []


async def _query_application_detail(
    db_path: Path, app_id: str
) -> tuple[Optional[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if not db_path.exists():
        return None, [], []
    try:
        app_repo = ApplicationRepository(db_path)
        event_repo = EventRepository(db_path)
        app = await app_repo.get_application(app_id)
        if not app:
            return None, [], []
        runs = await app_repo.list_runs_by_application(app_id)
        events: list[dict[str, Any]] = []
        for r in runs:
            run_events = await event_repo.list_events_by_run(r["id"])
            events.extend(run_events)
        return app, runs, events
    except Exception:
        return None, [], []


@track_app.command("list")
def list_applications(
    status: Optional[str] = typer.Option(
        None, "--status", "-s", help="Filter by status"
    ),
) -> None:
    """List job applications and their current status."""
    console.print(f"[bold cyan]Tracking Applications[/bold cyan]")
    if status:
        console.print(f"Filtered by status: {status}")

    db_path = get_db_path()
    apps = asyncio.run(_query_applications(db_path, status=status))
    if not apps:
        console.print("No active applications found.")
        return

    table = Table(title="Applications")
    table.add_column("ID", style="cyan")
    table.add_column("Company", style="bold")
    table.add_column("Job Title")
    table.add_column("Status", style="green")
    table.add_column("Stage", style="magenta")
    table.add_column("Updated At", style="dim")

    for a in apps:
        table.add_row(
            str(a.get("id")),
            str(a.get("company_name")),
            str(a.get("job_title")),
            str(a.get("status")),
            str(a.get("current_stage") or "-"),
            str(a.get("updated_at") or "-"),
        )
    console.print(table)


@track_app.command("list-applications", hidden=True)
def list_applications_alias(
    status: Optional[str] = typer.Option(
        None, "--status", "-s", help="Filter by status"
    ),
) -> None:
    """Alias for list."""
    list_applications(status=status)


@track_app.command("status")
def application_status(
    app_id: str = typer.Argument(..., help="Application ID"),
) -> None:
    """Show detailed status and audit history for an application."""
    console.print(f"[bold cyan]Application Status: {app_id}[/bold cyan]")
    db_path = get_db_path()
    app, runs, events = asyncio.run(_query_application_detail(db_path, app_id))
    if not app:
        console.print(f"[yellow]Application not found: {app_id}[/yellow]")
        return

    console.print(f"Target Company: [bold]{app.get('company_name')}[/bold]")
    console.print(f"Job Title: [bold]{app.get('job_title')}[/bold]")
    console.print(f"Status: [green]{app.get('status')}[/green]")
    console.print(f"Current Stage: {app.get('current_stage') or 'N/A'}")
    console.print(f"Recruitment Cycle: {app.get('recruitment_cycle') or 'N/A'}")
    console.print(f"Created At: {app.get('created_at')}")
    console.print(f"Updated At: {app.get('updated_at')}")
    console.print(f"Execution Runs: {len(runs)}")
    console.print(f"Audit Events: {len(events)}")


if __name__ == "__main__":
    app()
