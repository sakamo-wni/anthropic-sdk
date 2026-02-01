"""AWS CloudTrail events tool."""

import json
from datetime import datetime
from typing import Any

import boto3
from botocore.exceptions import ClientError

from ..config import get_settings
from .base import ReadOnlyTool


class CloudTrailTool(ReadOnlyTool):
    """Tool for fetching AWS CloudTrail change events."""

    def __init__(self, region: str | None = None) -> None:
        """Initialize CloudTrail client."""
        settings = get_settings()
        self._region = region or settings.aws_region
        session_kwargs: dict[str, Any] = {"region_name": self._region}
        if settings.aws_profile:
            session_kwargs["profile_name"] = settings.aws_profile
        session = boto3.Session(**session_kwargs)
        self._client = session.client("cloudtrail")

    @property
    def name(self) -> str:
        return "get_cloudtrail_events"

    @property
    def description(self) -> str:
        return """Get AWS CloudTrail events for configuration/infrastructure changes.

Use this tool to find recent AWS API calls that may have caused issues,
such as Lambda function updates, IAM policy changes, or resource modifications.

You can filter by event name patterns (e.g., 'Update*', 'Put*', 'Delete*')
to focus on modification events."""

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "start_time": {
                    "type": "string",
                    "description": "Start time in ISO 8601 format",
                },
                "end_time": {
                    "type": "string",
                    "description": "End time in ISO 8601 format",
                },
                "event_name_prefix": {
                    "type": "string",
                    "description": "Filter by event name prefix (e.g., 'UpdateFunction', 'PutBucket')",
                },
                "resource_type": {
                    "type": "string",
                    "description": "Filter by resource type (e.g., 'AWS::Lambda::Function')",
                },
                "username": {
                    "type": "string",
                    "description": "Filter by username/role that performed the action",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of events to return (default: 50)",
                    "default": 50,
                },
            },
            "required": ["start_time", "end_time"],
        }

    async def execute(
        self,
        start_time: str,
        end_time: str,
        event_name_prefix: str | None = None,
        resource_type: str | None = None,
        username: str | None = None,
        limit: int = 50,
        **kwargs: Any,
    ) -> str:
        """Fetch CloudTrail events within the specified time range."""
        try:
            # Parse timestamps
            start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))

            # Build lookup attributes for filtering
            lookup_attributes = []
            if event_name_prefix:
                lookup_attributes.append(
                    {"AttributeKey": "EventName", "AttributeValue": event_name_prefix}
                )
            if resource_type:
                lookup_attributes.append(
                    {"AttributeKey": "ResourceType", "AttributeValue": resource_type}
                )
            if username:
                lookup_attributes.append(
                    {"AttributeKey": "Username", "AttributeValue": username}
                )

            # Query CloudTrail
            query_params: dict[str, Any] = {
                "StartTime": start_dt,
                "EndTime": end_dt,
                "MaxResults": min(limit, 50),  # API max is 50
            }
            if lookup_attributes:
                query_params["LookupAttributes"] = lookup_attributes[:1]  # API only accepts 1

            events = []
            paginator = self._client.get_paginator("lookup_events")

            for page in paginator.paginate(**query_params):
                for event in page.get("Events", []):
                    # Parse the CloudTrail event JSON
                    event_data = json.loads(event.get("CloudTrailEvent", "{}"))

                    # Apply additional filters that API doesn't support directly
                    if event_name_prefix and not event_data.get("eventName", "").startswith(
                        event_name_prefix
                    ):
                        continue
                    if username and event_data.get("userIdentity", {}).get(
                        "userName", ""
                    ) != username:
                        continue

                    events.append(
                        {
                            "event_id": event.get("EventId"),
                            "event_name": event_data.get("eventName"),
                            "event_source": event_data.get("eventSource"),
                            "event_time": event_data.get("eventTime"),
                            "aws_region": event_data.get("awsRegion"),
                            "source_ip": event_data.get("sourceIPAddress"),
                            "user_identity": {
                                "type": event_data.get("userIdentity", {}).get("type"),
                                "arn": event_data.get("userIdentity", {}).get("arn"),
                                "username": event_data.get("userIdentity", {}).get(
                                    "userName", ""
                                ),
                            },
                            "resources": [
                                {
                                    "type": r.get("ResourceType"),
                                    "name": r.get("ResourceName"),
                                }
                                for r in event.get("Resources", [])
                            ],
                            "error_code": event_data.get("errorCode"),
                            "error_message": event_data.get("errorMessage"),
                            "request_parameters": self._summarize_params(
                                event_data.get("requestParameters", {})
                            ),
                        }
                    )

                    if len(events) >= limit:
                        break
                if len(events) >= limit:
                    break

            # Sort by event time descending
            events.sort(key=lambda x: x.get("event_time", ""), reverse=True)

            return json.dumps(
                {
                    "success": True,
                    "region": self._region,
                    "start_time": start_time,
                    "end_time": end_time,
                    "event_count": len(events),
                    "events": events,
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

    def _summarize_params(
        self, params: dict[str, Any] | None, max_length: int = 500
    ) -> dict[str, Any]:
        """Summarize request parameters to avoid huge outputs."""
        if not params:
            return {}

        result = {}
        for key, value in params.items():
            if isinstance(value, str) and len(value) > max_length:
                result[key] = value[:max_length] + "...(truncated)"
            elif isinstance(value, (dict, list)):
                json_str = json.dumps(value)
                if len(json_str) > max_length:
                    result[key] = f"({type(value).__name__}, truncated)"
                else:
                    result[key] = value
            else:
                result[key] = value
        return result
