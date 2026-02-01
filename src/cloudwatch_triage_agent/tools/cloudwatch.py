"""CloudWatch Logs search tool."""

import json
import time
from datetime import datetime
from typing import Any

import boto3
from botocore.exceptions import ClientError

from ..config import get_settings
from .base import ReadOnlyTool


class CloudWatchLogsTool(ReadOnlyTool):
    """Tool for searching CloudWatch Logs using Logs Insights."""

    def __init__(self, region: str | None = None) -> None:
        """Initialize CloudWatch Logs client."""
        settings = get_settings()
        self._region = region or settings.aws_region
        session_kwargs: dict[str, Any] = {"region_name": self._region}
        if settings.aws_profile:
            session_kwargs["profile_name"] = settings.aws_profile
        session = boto3.Session(**session_kwargs)
        self._client = session.client("logs")
        self._max_results = settings.max_log_results

    @property
    def name(self) -> str:
        return "search_cloudwatch_logs"

    @property
    def description(self) -> str:
        return """Search CloudWatch Logs using Logs Insights query.

Use this tool to search for error messages, exceptions, and relevant log entries
within a specified time range. The query uses CloudWatch Logs Insights syntax.

Common query patterns:
- Filter by level: `fields @timestamp, @message | filter @message like /ERROR/`
- Filter by field: `fields @timestamp, @message | filter statusCode >= 500`
- Aggregate errors: `stats count(*) by errorType | sort count desc`
- Parse JSON logs: `parse @message '{"level":"*","msg":"*"}' as level, msg`

Returns matching log entries with timestamps and messages."""

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "log_group": {
                    "type": "string",
                    "description": "CloudWatch log group name to search",
                },
                "query": {
                    "type": "string",
                    "description": "Logs Insights query (e.g., 'fields @timestamp, @message | filter @message like /ERROR/ | sort @timestamp desc | limit 50')",
                },
                "start_time": {
                    "type": "string",
                    "description": "Start time in ISO 8601 format (e.g., '2024-01-15T10:00:00Z')",
                },
                "end_time": {
                    "type": "string",
                    "description": "End time in ISO 8601 format (e.g., '2024-01-15T11:00:00Z')",
                },
            },
            "required": ["log_group", "query", "start_time", "end_time"],
        }

    async def execute(
        self,
        log_group: str,
        query: str,
        start_time: str,
        end_time: str,
        **kwargs: Any,
    ) -> str:
        """Execute CloudWatch Logs Insights query."""
        try:
            # Parse timestamps
            start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))

            # Start query
            response = self._client.start_query(
                logGroupName=log_group,
                startTime=int(start_dt.timestamp()),
                endTime=int(end_dt.timestamp()),
                queryString=query,
                limit=self._max_results,
            )
            query_id = response["queryId"]

            # Poll for results
            results = await self._wait_for_query(query_id)

            return json.dumps(
                {
                    "success": True,
                    "log_group": log_group,
                    "query": query,
                    "start_time": start_time,
                    "end_time": end_time,
                    "result_count": len(results.get("results", [])),
                    "results": results.get("results", []),
                    "statistics": results.get("statistics", {}),
                },
                indent=2,
                default=str,
            )

        except ClientError as e:
            return json.dumps(
                {
                    "success": False,
                    "error": f"AWS error: {e.response['Error']['Message']}",
                    "error_code": e.response["Error"]["Code"],
                }
            )
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    async def _wait_for_query(
        self, query_id: str, max_wait_seconds: int = 60
    ) -> dict[str, Any]:
        """Wait for query to complete and return results."""
        start_time = time.time()
        while time.time() - start_time < max_wait_seconds:
            response = self._client.get_query_results(queryId=query_id)
            status = response["status"]

            if status == "Complete":
                # Convert results to more readable format
                formatted_results = []
                for result in response.get("results", []):
                    entry = {field["field"]: field["value"] for field in result}
                    formatted_results.append(entry)
                return {
                    "results": formatted_results,
                    "statistics": response.get("statistics", {}),
                }
            elif status in ("Failed", "Cancelled"):
                raise RuntimeError(f"Query {status.lower()}")

            time.sleep(0.5)

        raise TimeoutError("Query timed out")
