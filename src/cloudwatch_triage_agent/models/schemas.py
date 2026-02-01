"""Pydantic schemas for CloudWatch Triage Agent."""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Environment(StrEnum):
    """Target environment."""

    DEV = "dev"
    PROD = "prod"


class TriageContext(BaseModel):
    """Context for triage investigation."""

    service: str = Field(..., description="Service name to investigate")
    environment: Environment = Field(..., description="Target environment (dev/prod)")
    start_time: datetime = Field(..., description="Start of investigation time range")
    end_time: datetime = Field(..., description="End of investigation time range")
    symptoms: str = Field(..., description="User-reported symptoms")
    log_group: str = Field(..., description="CloudWatch log group name")
    initial_strategy: str = Field(
        default="", description="Initial investigation strategy determined by triage"
    )


class LogSearchResult(BaseModel):
    """Result from CloudWatch Logs search."""

    query: str = Field(..., description="Logs Insights query executed")
    log_group: str = Field(..., description="Log group searched")
    start_time: datetime = Field(..., description="Search start time")
    end_time: datetime = Field(..., description="Search end time")
    results: list[dict[str, Any]] = Field(
        default_factory=list, description="Log entries found"
    )
    statistics: dict[str, Any] = Field(
        default_factory=dict, description="Query statistics"
    )


class DeploymentInfo(BaseModel):
    """GitHub deployment information."""

    deployment_id: int = Field(..., description="GitHub deployment ID")
    environment: str = Field(..., description="Deployment environment")
    ref: str = Field(..., description="Git ref (branch/tag/sha)")
    sha: str = Field(..., description="Commit SHA")
    created_at: datetime = Field(..., description="Deployment creation time")
    updated_at: datetime = Field(..., description="Last update time")
    status: str = Field(..., description="Deployment status")
    description: str = Field(default="", description="Deployment description")
    creator: str = Field(default="", description="User who created the deployment")


class CloudTrailEvent(BaseModel):
    """AWS CloudTrail event."""

    event_id: str = Field(..., description="CloudTrail event ID")
    event_name: str = Field(..., description="AWS API action name")
    event_source: str = Field(..., description="AWS service source")
    event_time: datetime = Field(..., description="Event timestamp")
    username: str = Field(default="", description="User/role that performed the action")
    source_ip: str = Field(default="", description="Source IP address")
    aws_region: str = Field(..., description="AWS region")
    resources: list[dict[str, str]] = Field(
        default_factory=list, description="Affected resources"
    )
    error_code: str | None = Field(default=None, description="Error code if failed")
    error_message: str | None = Field(
        default=None, description="Error message if failed"
    )


class RootCauseCandidate(BaseModel):
    """Potential root cause candidate."""

    rank: int = Field(..., ge=1, le=3, description="Ranking (1-3)")
    summary: str = Field(..., description="Brief summary of the cause")
    evidence: list[str] = Field(..., description="Supporting evidence")
    confidence: str = Field(..., description="Confidence level (high/medium/low)")
    related_logs: list[str] = Field(
        default_factory=list, description="Related log entries"
    )
    related_changes: list[str] = Field(
        default_factory=list, description="Related deployment/config changes"
    )


class InvestigationReport(BaseModel):
    """Complete investigation report."""

    context: TriageContext = Field(..., description="Triage context")
    root_causes: list[RootCauseCandidate] = Field(
        ..., description="Top 3 root cause candidates"
    )
    timeline: list[str] = Field(
        default_factory=list, description="Timeline of relevant events"
    )
    investigation_steps: list[str] = Field(
        default_factory=list, description="Steps taken during investigation"
    )
    recommendations: list[str] = Field(
        default_factory=list, description="Recommended next actions"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Report creation time",
    )


class SlackMessage(BaseModel):
    """Slack message for posting."""

    channel: str = Field(..., description="Slack channel ID or name")
    text: str = Field(..., description="Message text (markdown supported)")
    blocks: list[dict[str, Any]] = Field(
        default_factory=list, description="Slack Block Kit blocks"
    )
    thread_ts: str | None = Field(
        default=None, description="Thread timestamp for replies"
    )


class ToolCall(BaseModel):
    """Represents a tool call from Claude."""

    id: str = Field(..., description="Tool call ID")
    name: str = Field(..., description="Tool name")
    input: dict[str, Any] = Field(..., description="Tool input parameters")


class ToolResult(BaseModel):
    """Result from a tool execution."""

    tool_use_id: str = Field(..., description="Corresponding tool call ID")
    content: str = Field(..., description="Tool result content")
    is_error: bool = Field(default=False, description="Whether the result is an error")
