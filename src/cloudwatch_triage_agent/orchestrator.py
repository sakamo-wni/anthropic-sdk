"""Main orchestrator for the CloudWatch Triage Agent."""

import asyncio
import json
from typing import Any, Callable

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from .controllers.investigator import InvestigatorController
from .controllers.triage import TriageController
from .models.schemas import InvestigationReport, TriageContext


class TriageOrchestrator:
    """Orchestrates the triage and investigation workflow."""

    def __init__(self, console: Console | None = None) -> None:
        """Initialize the orchestrator."""
        self._console = console or Console()
        self._triage_controller = TriageController()
        self._investigator_controller = InvestigatorController()

    async def run(
        self,
        symptoms: str,
        skip_confirmation: bool = False,
        auto_approve_slack: bool = False,
    ) -> InvestigationReport:
        """Run the full triage and investigation workflow.

        Args:
            symptoms: User-reported symptoms
            skip_confirmation: Skip triage confirmation step
            auto_approve_slack: Auto-approve Slack posting

        Returns:
            Investigation report
        """
        self._console.print(
            Panel(
                "[bold blue]CloudWatch Triage Agent[/bold blue]\n"
                "AI-powered incident investigation",
                expand=False,
            )
        )

        # Step 1: Triage
        self._console.print("\n[bold]Step 1: Analyzing symptoms...[/bold]")
        context = await self._triage_controller.analyze_symptoms(symptoms)

        # Display triage results
        self._display_triage_context(context)

        # Confirm with user
        if not skip_confirmation:
            if not Confirm.ask("Proceed with investigation?", default=True):
                self._console.print("[yellow]Investigation cancelled.[/yellow]")
                raise SystemExit(0)

            # Allow user to modify parameters
            context = await self._prompt_for_modifications(context)

        # Step 2: Investigation
        self._console.print("\n[bold]Step 2: Investigating...[/bold]")

        async def approval_callback(tool_name: str, tool_input: dict[str, Any]) -> bool:
            if auto_approve_slack:
                return True
            return self._prompt_for_approval(tool_name, tool_input)

        report = await self._investigator_controller.investigate(
            context, approval_callback=approval_callback
        )

        # Display results
        self._display_investigation_report(report)

        # Step 3: Slack notification
        if Confirm.ask("\nPost results to Slack?", default=True):
            channel = Prompt.ask(
                "Slack channel", default="#incidents", show_default=True
            )

            # Show preview
            text, blocks = await self._investigator_controller.generate_slack_message(
                report
            )
            self._console.print("\n[bold]Slack message preview:[/bold]")
            self._console.print(Panel(text, title="Message", expand=False))

            if Confirm.ask("Confirm posting?", default=True):
                result = await self._investigator_controller.post_to_slack(
                    report,
                    channel=channel,
                    approval_callback=lambda *_: asyncio.coroutine(lambda: True)(),
                )
                result_data = json.loads(result)
                if result_data.get("success"):
                    self._console.print(
                        f"[green]Posted to Slack![/green] {result_data.get('permalink', '')}"
                    )
                else:
                    self._console.print(
                        f"[red]Failed to post:[/red] {result_data.get('error')}"
                    )

        return report

    def _display_triage_context(self, context: TriageContext) -> None:
        """Display triage context in a formatted table."""
        table = Table(title="Triage Results", expand=False)
        table.add_column("Parameter", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Service", context.service)
        table.add_row("Environment", context.environment.value)
        table.add_row("Log Group", context.log_group)
        table.add_row("Start Time", context.start_time.isoformat())
        table.add_row("End Time", context.end_time.isoformat())
        table.add_row("Strategy", context.initial_strategy)

        self._console.print(table)

    def _display_investigation_report(self, report: InvestigationReport) -> None:
        """Display investigation report."""
        self._console.print("\n[bold green]Investigation Complete![/bold green]\n")

        # Root causes table
        table = Table(title="Root Cause Candidates", expand=False)
        table.add_column("#", style="bold")
        table.add_column("Summary", style="cyan")
        table.add_column("Confidence", style="yellow")
        table.add_column("Evidence", style="dim")

        for rc in report.root_causes:
            evidence_str = "\n".join(f"- {e[:50]}..." if len(e) > 50 else f"- {e}" for e in rc.evidence[:2])
            table.add_row(
                str(rc.rank),
                rc.summary,
                rc.confidence,
                evidence_str or "N/A",
            )

        self._console.print(table)

        # Timeline
        if report.timeline:
            self._console.print("\n[bold]Timeline:[/bold]")
            for event in report.timeline[:5]:
                self._console.print(f"  - {event}")

        # Recommendations
        if report.recommendations:
            self._console.print("\n[bold]Recommendations:[/bold]")
            for rec in report.recommendations[:5]:
                self._console.print(f"  - {rec}")

    async def _prompt_for_modifications(
        self, context: TriageContext
    ) -> TriageContext:
        """Allow user to modify triage parameters."""
        if not Confirm.ask("Modify parameters?", default=False):
            return context

        # Allow modifications via prompts
        from datetime import datetime

        service = Prompt.ask("Service", default=context.service)
        env = Prompt.ask("Environment (dev/prod)", default=context.environment.value)

        start_str = Prompt.ask(
            "Start time (ISO 8601)", default=context.start_time.isoformat()
        )
        end_str = Prompt.ask(
            "End time (ISO 8601)", default=context.end_time.isoformat()
        )

        from .config import get_settings
        from .models.schemas import Environment

        settings = get_settings()

        return TriageContext(
            service=service,
            environment=Environment(env),
            start_time=datetime.fromisoformat(start_str.replace("Z", "+00:00")),
            end_time=datetime.fromisoformat(end_str.replace("Z", "+00:00")),
            symptoms=context.symptoms,
            log_group=settings.get_log_group(service, env),
            initial_strategy=context.initial_strategy,
        )

    def _prompt_for_approval(
        self, tool_name: str, tool_input: dict[str, Any]
    ) -> bool:
        """Prompt user for tool execution approval."""
        self._console.print(
            f"\n[yellow]Tool requires approval:[/yellow] {tool_name}"
        )
        self._console.print(f"Input: {json.dumps(tool_input, indent=2)[:500]}")
        return Confirm.ask("Approve?", default=False)
