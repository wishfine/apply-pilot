"""ApplyPilot command-line interface entry point.

Provides CLI command groups:
- profile: Manage candidate fact base and resume variants.
- apply: Automate job application form filling and human review.
- track: Track application lifecycle and view audit logs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from rich.console import Console
import typer
import yaml

from applypilot.core.config import get_app_home_dir
from applypilot.domain.profile import CandidateProfile

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
    try:
        data = yaml.safe_load(content)
    except Exception:
        data = json.loads(content)
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
        console.print(f"[yellow]No profile found at: {profile_path}[/yellow]")
        return

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


@apply_app.command("run")
def apply_run(
    job_url: str = typer.Option(..., "--job-url", "-u", help="Job recruitment URL"),
    profile_path: Optional[Path] = typer.Option(
        None, "--profile", help="Path to candidate profile yaml/json"
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


@track_app.command("list")
def list_applications(
    status: Optional[str] = typer.Option(None, "--status", help="Filter by status"),
) -> None:
    """List job applications and their current status."""
    console.print(f"[bold cyan]Tracking Applications[/bold cyan]")
    if status:
        console.print(f"Filtered by status: {status}")
    console.print("No active applications found.")


@track_app.command("list-applications", hidden=True)
def list_applications_alias(
    status: Optional[str] = typer.Option(None, "--status", help="Filter by status"),
) -> None:
    """Alias for list."""
    list_applications(status=status)


@track_app.command("status")
def application_status(
    app_id: str = typer.Argument(..., help="Application ID"),
) -> None:
    """Show detailed status and audit history for an application."""
    console.print(f"[bold cyan]Application Status: {app_id}[/bold cyan]")


if __name__ == "__main__":
    app()
