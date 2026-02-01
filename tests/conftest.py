"""Pytest fixtures for CloudWatch Triage Agent tests."""

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from cloudwatch_triage_agent.models.schemas import Environment, TriageContext


@pytest.fixture(autouse=True)
def mock_env_vars() -> None:
    """Set required environment variables for tests."""
    env_vars = {
        "ANTHROPIC_API_KEY": "sk-ant-test-key",
        "GITHUB_TOKEN": "ghp_test_token",
        "GITHUB_OWNER": "test-owner",
        "GITHUB_REPO": "test-repo",
        "SLACK_BOT_TOKEN": "xoxb-test-token",
        "AWS_REGION": "us-east-1",
    }
    with patch.dict(os.environ, env_vars):
        yield


@pytest.fixture
def sample_triage_context() -> TriageContext:
    """Create a sample triage context for testing."""
    now = datetime.now(timezone.utc)
    return TriageContext(
        service="test-service",
        environment=Environment.PROD,
        start_time=now,
        end_time=now,
        symptoms="500 errors in API",
        log_group="/aws/lambda/test-service-prod",
        initial_strategy="Search for ERROR patterns",
    )


@pytest.fixture
def mock_anthropic_client() -> MagicMock:
    """Create a mock Anthropic client."""
    mock = MagicMock()
    mock.messages.create.return_value = MagicMock(
        content=[MagicMock(type="text", text='{"service": "test", "environment": "prod"}')],
        stop_reason="end_turn",
    )
    return mock


@pytest.fixture
def mock_boto3_client() -> MagicMock:
    """Create a mock boto3 client."""
    mock = MagicMock()
    return mock
