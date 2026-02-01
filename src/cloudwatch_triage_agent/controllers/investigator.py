"""Investigator Controller - Performs log analysis and root cause identification."""

import json
from datetime import datetime, timezone
from typing import Any

import anthropic

from ..config import get_settings
from ..models.schemas import (
    InvestigationReport,
    RootCauseCandidate,
    TriageContext,
)
from ..tools.base import BaseTool
from ..tools.cloudtrail import CloudTrailTool
from ..tools.cloudwatch import CloudWatchLogsTool
from ..tools.github_deployments import GitHubDeploymentsTool
from ..tools.slack import SlackTool


INVESTIGATOR_SYSTEM_PROMPT = """You are an expert SRE investigating a production incident. Your goal is to identify the root cause by analyzing logs and correlating with recent changes.

**Investigation Context:**
- Service: {service}
- Environment: {environment}
- Time Range: {start_time} to {end_time}
- Symptoms: {symptoms}
- Log Group: {log_group}
- Initial Strategy: {initial_strategy}

**Investigation Process:**
1. Start by searching CloudWatch Logs for errors and exceptions
2. Look for patterns in error messages and stack traces
3. Check GitHub deployments for recent code changes
4. Check CloudTrail for infrastructure/config changes
5. Correlate timing of errors with deployments and changes
6. Identify TOP 3 most likely root causes with supporting evidence

**Output Requirements:**
When you have completed your investigation, respond with a JSON object:
{{
    "investigation_complete": true,
    "root_causes": [
        {{
            "rank": 1,
            "summary": "Brief description",
            "evidence": ["Evidence 1", "Evidence 2"],
            "confidence": "high|medium|low",
            "related_logs": ["Relevant log excerpts"],
            "related_changes": ["Related deployments or changes"]
        }}
    ],
    "timeline": ["Event 1 at time", "Event 2 at time"],
    "investigation_steps": ["Step 1", "Step 2"],
    "recommendations": ["Next action 1", "Next action 2"],
    "slack_summary": "Concise summary for Slack notification"
}}

Use the available tools to gather evidence. Be thorough but efficient."""


class InvestigatorController:
    """Controller for investigating incidents using Claude and tools."""

    MAX_TURNS = 10

    def __init__(self) -> None:
        """Initialize the investigator controller."""
        settings = get_settings()
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.anthropic_model

        # Initialize tools
        self._tools: dict[str, BaseTool] = {
            "search_cloudwatch_logs": CloudWatchLogsTool(),
            "get_github_deployments": GitHubDeploymentsTool(),
            "get_cloudtrail_events": CloudTrailTool(),
            "post_slack_message": SlackTool(),
        }

    async def investigate(
        self,
        context: TriageContext,
        approval_callback: Any = None,
    ) -> InvestigationReport:
        """Perform investigation using Claude with tool use.

        Args:
            context: Triage context with investigation parameters
            approval_callback: Optional callback for tool approval (async callable)

        Returns:
            InvestigationReport with findings
        """
        system_prompt = INVESTIGATOR_SYSTEM_PROMPT.format(
            service=context.service,
            environment=context.environment.value,
            start_time=context.start_time.isoformat(),
            end_time=context.end_time.isoformat(),
            symptoms=context.symptoms,
            log_group=context.log_group,
            initial_strategy=context.initial_strategy,
        )

        # Build tool definitions (exclude Slack for investigation phase)
        investigation_tools = [
            tool.to_anthropic_tool()
            for name, tool in self._tools.items()
            if name != "post_slack_message"
        ]

        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": "Begin your investigation. Use the available tools to analyze logs and identify root causes.",
            }
        ]

        investigation_steps: list[str] = []
        turn = 0

        while turn < self.MAX_TURNS:
            turn += 1

            response = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=system_prompt,
                tools=investigation_tools,
                messages=messages,
            )

            # Check if investigation is complete
            if response.stop_reason == "end_turn":
                # Try to parse final response
                for block in response.content:
                    if block.type == "text":
                        report = self._parse_investigation_result(block.text, context)
                        if report:
                            report.investigation_steps = investigation_steps
                            return report

            # Process tool use
            if response.stop_reason == "tool_use":
                tool_results = []

                for block in response.content:
                    if block.type == "tool_use":
                        tool_name = block.name
                        tool_input = block.input
                        tool_id = block.id

                        investigation_steps.append(
                            f"Called {tool_name} with {json.dumps(tool_input)[:100]}..."
                        )

                        # Execute tool
                        tool = self._tools.get(tool_name)
                        if tool:
                            # Check approval for action tools
                            if hasattr(tool, "requires_approval") and tool.requires_approval:
                                if approval_callback:
                                    approved = await approval_callback(
                                        tool_name, tool_input
                                    )
                                    if not approved:
                                        tool_results.append(
                                            {
                                                "type": "tool_result",
                                                "tool_use_id": tool_id,
                                                "content": "Tool execution denied by user",
                                                "is_error": True,
                                            }
                                        )
                                        continue

                            result = await tool.execute(**tool_input)
                            tool_results.append(
                                {
                                    "type": "tool_result",
                                    "tool_use_id": tool_id,
                                    "content": result,
                                }
                            )
                        else:
                            tool_results.append(
                                {
                                    "type": "tool_result",
                                    "tool_use_id": tool_id,
                                    "content": f"Unknown tool: {tool_name}",
                                    "is_error": True,
                                }
                            )

                # Add assistant response and tool results to messages
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})

        # If we hit max turns, create a partial report
        return InvestigationReport(
            context=context,
            root_causes=[
                RootCauseCandidate(
                    rank=1,
                    summary="Investigation incomplete - max turns reached",
                    evidence=["Investigation was cut short"],
                    confidence="low",
                )
            ],
            investigation_steps=investigation_steps,
            recommendations=["Manual investigation required"],
        )

    def _parse_investigation_result(
        self, text: str, context: TriageContext
    ) -> InvestigationReport | None:
        """Parse investigation result from Claude's response."""
        try:
            # Try to find JSON in the response
            data = self._extract_json(text)
            if not data or not data.get("investigation_complete"):
                return None

            root_causes = [
                RootCauseCandidate(
                    rank=rc.get("rank", i + 1),
                    summary=rc.get("summary", "Unknown"),
                    evidence=rc.get("evidence", []),
                    confidence=rc.get("confidence", "low"),
                    related_logs=rc.get("related_logs", []),
                    related_changes=rc.get("related_changes", []),
                )
                for i, rc in enumerate(data.get("root_causes", [])[:3])
            ]

            if not root_causes:
                root_causes = [
                    RootCauseCandidate(
                        rank=1,
                        summary="No clear root cause identified",
                        evidence=["Insufficient evidence"],
                        confidence="low",
                    )
                ]

            return InvestigationReport(
                context=context,
                root_causes=root_causes,
                timeline=data.get("timeline", []),
                investigation_steps=data.get("investigation_steps", []),
                recommendations=data.get("recommendations", []),
                created_at=datetime.now(timezone.utc),
            )

        except Exception:
            return None

    def _extract_json(self, text: str) -> dict[str, Any] | None:
        """Extract JSON from text response."""
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try markdown code block
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end > start:
                try:
                    return json.loads(text[start:end].strip())
                except json.JSONDecodeError:
                    pass

        # Try to find JSON object
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

        return None

    async def generate_slack_message(
        self, report: InvestigationReport
    ) -> tuple[str, list[dict[str, Any]]]:
        """Generate Slack message from investigation report.

        Returns:
            Tuple of (text, blocks) for Slack message
        """
        slack_tool = self._tools.get("post_slack_message")
        if isinstance(slack_tool, SlackTool):
            root_causes_data = [
                {
                    "summary": rc.summary,
                    "evidence": rc.evidence,
                    "confidence": rc.confidence,
                }
                for rc in report.root_causes
            ]

            return slack_tool.format_investigation_report(
                service=report.context.service,
                environment=report.context.environment.value,
                summary=report.root_causes[0].summary if report.root_causes else "Unknown",
                root_causes=root_causes_data,
                recommendations=report.recommendations,
            )

        # Fallback simple message
        return (
            f"Investigation Report for {report.context.service} ({report.context.environment.value})",
            [],
        )

    async def post_to_slack(
        self,
        report: InvestigationReport,
        channel: str | None = None,
        approval_callback: Any = None,
    ) -> str:
        """Post investigation report to Slack.

        Args:
            report: Investigation report to post
            channel: Optional channel override
            approval_callback: Callback for approval (required)

        Returns:
            Result message
        """
        text, blocks = await self.generate_slack_message(report)

        slack_tool = self._tools.get("post_slack_message")
        if not isinstance(slack_tool, SlackTool):
            return "Slack tool not available"

        # Require approval
        if approval_callback:
            tool_input = {"text": text, "blocks": blocks}
            if channel:
                tool_input["channel"] = channel

            approved = await approval_callback("post_slack_message", tool_input)
            if not approved:
                return "Slack posting denied by user"

        return await slack_tool.execute(text=text, blocks=blocks, channel=channel)
