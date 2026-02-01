"""CLI for CloudWatch Triage Agent."""

import asyncio
from typing import Optional

import typer
from rich.console import Console
from rich.prompt import Prompt

from . import __version__

app = typer.Typer(
    name="triage",
    help="CloudWatch Log Triage Agent - AI-powered incident investigation",
    no_args_is_help=True,
)
console = Console()


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"CloudWatch Triage Agent v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit",
    ),
) -> None:
    """CloudWatch Log Triage Agent."""
    pass


@app.command()
def investigate(
    symptoms: Optional[str] = typer.Argument(
        None,
        help="Symptom description (will prompt if not provided)",
    ),
    service: Optional[str] = typer.Option(
        None,
        "--service",
        "-s",
        help="Service name to investigate",
    ),
    environment: Optional[str] = typer.Option(
        None,
        "--env",
        "-e",
        help="Environment (dev/prod)",
    ),
    skip_confirmation: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompts",
    ),
    auto_approve_slack: bool = typer.Option(
        False,
        "--auto-slack",
        help="Auto-approve Slack posting",
    ),
) -> None:
    """Investigate an incident using AI-powered log analysis.

    Example:
        triage investigate "500 errors in checkout API since 10am"
        triage investigate -s payment-service -e prod "Payment failures"
    """
    from .orchestrator import TriageOrchestrator

    # Get symptoms if not provided
    if not symptoms:
        symptoms = Prompt.ask(
            "[bold]Describe the incident symptoms[/bold]",
            console=console,
        )

    # Build symptom string with optional service/env hints
    full_symptoms = symptoms
    if service:
        full_symptoms = f"[Service: {service}] {full_symptoms}"
    if environment:
        full_symptoms = f"[Environment: {environment}] {full_symptoms}"

    # Run investigation
    orchestrator = TriageOrchestrator(console=console)
    try:
        asyncio.run(
            orchestrator.run(
                symptoms=full_symptoms,
                skip_confirmation=skip_confirmation,
                auto_approve_slack=auto_approve_slack,
            )
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Investigation cancelled.[/yellow]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"\n[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def list_services() -> None:
    """List configured services and their log groups."""
    from .config import get_settings

    try:
        settings = get_settings()
    except Exception as e:
        console.print(f"[red]Configuration error:[/red] {e}")
        console.print("\nMake sure you have a .env file with required settings.")
        raise typer.Exit(1)

    from rich.table import Table

    table = Table(title="Configured Services")
    table.add_column("Service", style="cyan")
    table.add_column("Environment", style="green")
    table.add_column("Log Group", style="dim")

    for service, envs in settings.service_log_groups.items():
        for env, log_group in envs.items():
            table.add_row(service, env, log_group)

    console.print(table)


@app.command()
def check_config() -> None:
    """Verify configuration and connectivity."""
    from .config import get_settings

    console.print("[bold]Checking configuration...[/bold]\n")

    # Check settings
    try:
        settings = get_settings()
        console.print("[green]✓[/green] Configuration loaded")
    except Exception as e:
        console.print(f"[red]✗[/red] Configuration error: {e}")
        raise typer.Exit(1)

    # Check Anthropic
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        # Just verify key format (don't make actual API call)
        if settings.anthropic_api_key.startswith("sk-"):
            console.print("[green]✓[/green] Anthropic API key configured")
        else:
            console.print("[yellow]?[/yellow] Anthropic API key format unclear")
    except Exception as e:
        console.print(f"[red]✗[/red] Anthropic error: {e}")

    # Check AWS
    try:
        import boto3

        session = boto3.Session(
            region_name=settings.aws_region,
            profile_name=settings.aws_profile,
        )
        sts = session.client("sts")
        identity = sts.get_caller_identity()
        console.print(
            f"[green]✓[/green] AWS configured (Account: {identity['Account']})"
        )
    except Exception as e:
        console.print(f"[red]✗[/red] AWS error: {e}")

    # Check GitHub
    try:
        from github import Auth, Github

        auth = Auth.Token(settings.github_token)
        g = Github(auth=auth)
        user = g.get_user()
        console.print(f"[green]✓[/green] GitHub configured (User: {user.login})")
        g.close()
    except Exception as e:
        console.print(f"[red]✗[/red] GitHub error: {e}")

    # Check Slack
    try:
        from slack_sdk import WebClient

        client = WebClient(token=settings.slack_bot_token)
        auth = client.auth_test()
        console.print(f"[green]✓[/green] Slack configured (Bot: {auth['user']})")
    except Exception as e:
        console.print(f"[red]✗[/red] Slack error: {e}")

    console.print("\n[bold]Configuration check complete.[/bold]")


if __name__ == "__main__":
    app()
