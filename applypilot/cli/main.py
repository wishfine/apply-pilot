"""ApplyPilot command-line interface entry point.

Provides CLI command groups:
- profile: Manage candidate fact base and resume variants.
- apply: Automate job application form filling and human review.
- track: Track application lifecycle and view audit logs.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Optional

from rich.console import Console
from rich.table import Table
import typer
import yaml

from applypilot.core.config import get_app_home_dir, get_db_path
from applypilot.domain.profile import CandidateProfile
from applypilot.modules.profile.ingestion import (
    ResumeIngestionError,
    ResumeIngestionService,
)
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


@apply_app.command("run")
def apply_run(
    job_url: str = typer.Option(..., "--job-url", "-u", help="Job recruitment URL"),
    profile_path: Optional[Path] = typer.Option(
        None, "--profile", "-p", help="Path to candidate profile yaml/json"
    ),
    headless: bool = typer.Option(
        False, "--headless", help="Run browser in headless mode"
    ),
) -> None:
    """Automate job application form filling and human review."""
    console.print(f"[bold blue]Starting ApplyPilot session for: {job_url}[/bold blue]")
    console.print(f"Headless mode: {headless}")
    if profile_path:
        console.print(f"Using profile from: {profile_path}")


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
