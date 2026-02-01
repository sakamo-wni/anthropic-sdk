"""Triage Controller - Determines investigation parameters."""

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import anthropic

from ..config import get_settings
from ..models.schemas import Environment, TriageContext


TRIAGE_SYSTEM_PROMPT = """You are an expert incident triage specialist. Your role is to analyze user-reported symptoms and determine the optimal investigation parameters.

Given a symptom description, you must determine:
1. **Service**: Which service is affected (choose from available services)
2. **Environment**: dev or prod
3. **Time Range**: When the issue likely started and current time
4. **Initial Strategy**: What to look for in logs first

Available services: {available_services}

Respond with a JSON object containing:
{{
    "service": "service-name",
    "environment": "dev" or "prod",
    "start_time": "ISO 8601 timestamp",
    "end_time": "ISO 8601 timestamp",
    "initial_strategy": "Description of what to search for first"
}}

Consider these factors:
- Error messages often mention the affected service
- Production issues are more critical
- Start with a 1-hour lookback unless symptoms suggest otherwise
- For intermittent issues, consider a longer time range
- Initial strategy should focus on ERROR/EXCEPTION logs first"""


class TriageController:
    """Controller for triaging incidents and determining investigation parameters."""

    def __init__(self) -> None:
        """Initialize the triage controller."""
        settings = get_settings()
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.anthropic_model
        self._settings = settings

    async def analyze_symptoms(self, symptoms: str) -> TriageContext:
        """Analyze symptoms and determine investigation context.

        Args:
            symptoms: User-reported symptom description

        Returns:
            TriageContext with determined parameters
        """
        available_services = list(self._settings.service_log_groups.keys())

        system_prompt = TRIAGE_SYSTEM_PROMPT.format(
            available_services=", ".join(available_services)
        )

        message = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": f"Analyze this incident report and determine investigation parameters:\n\n{symptoms}",
                }
            ],
        )

        # Extract JSON from response
        response_text = message.content[0].text
        triage_data = self._parse_triage_response(response_text)

        # Validate and create context
        service = triage_data.get("service", available_services[0])
        if service not in available_services:
            service = available_services[0]

        environment = triage_data.get("environment", "prod")
        if environment not in ["dev", "prod"]:
            environment = "prod"

        # Parse time range
        now = datetime.now(timezone.utc)
        default_lookback = timedelta(minutes=self._settings.default_lookback_minutes)

        try:
            start_time = datetime.fromisoformat(
                triage_data["start_time"].replace("Z", "+00:00")
            )
        except (KeyError, ValueError):
            start_time = now - default_lookback

        try:
            end_time = datetime.fromisoformat(
                triage_data["end_time"].replace("Z", "+00:00")
            )
        except (KeyError, ValueError):
            end_time = now

        # Get log group for service/environment
        log_group = self._settings.get_log_group(service, environment)

        return TriageContext(
            service=service,
            environment=Environment(environment),
            start_time=start_time,
            end_time=end_time,
            symptoms=symptoms,
            log_group=log_group,
            initial_strategy=triage_data.get(
                "initial_strategy", "Search for ERROR and EXCEPTION patterns"
            ),
        )

    def _parse_triage_response(self, response: str) -> dict[str, Any]:
        """Parse JSON from Claude's response."""
        # Try to find JSON in the response
        try:
            # First try direct JSON parse
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # Try to extract JSON from markdown code block
        if "```json" in response:
            start = response.find("```json") + 7
            end = response.find("```", start)
            if end > start:
                try:
                    return json.loads(response[start:end].strip())
                except json.JSONDecodeError:
                    pass

        # Try to find any JSON object
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(response[start:end])
            except json.JSONDecodeError:
                pass

        return {}

    async def confirm_with_user(
        self, context: TriageContext
    ) -> tuple[bool, TriageContext]:
        """Present triage results to user for confirmation.

        In a real implementation, this would interact with the user.
        For now, it returns the context as-is.

        Returns:
            Tuple of (confirmed, possibly_modified_context)
        """
        # This would typically prompt the user for confirmation
        # For MVP, we auto-confirm
        return True, context
