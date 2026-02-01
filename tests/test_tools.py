"""Tests for tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cloudwatch_triage_agent.tools.base import ActionTool, ReadOnlyTool


class TestBaseTool:
    """Tests for base tool classes."""

    def test_readonly_tool_no_approval(self) -> None:
        """ReadOnlyTool should not require approval."""
        assert ReadOnlyTool.requires_approval is False

    def test_action_tool_requires_approval(self) -> None:
        """ActionTool should require approval."""
        assert ActionTool.requires_approval is True


class TestCloudWatchLogsTool:
    """Tests for CloudWatch Logs tool."""

    @patch("cloudwatch_triage_agent.tools.cloudwatch.boto3.Session")
    @patch("cloudwatch_triage_agent.tools.cloudwatch.get_settings")
    def test_tool_definition(
        self, mock_settings: MagicMock, mock_session: MagicMock
    ) -> None:
        """Test tool Anthropic definition."""
        mock_settings.return_value = MagicMock(
            aws_region="us-east-1",
            aws_profile=None,
            max_log_results=100,
        )

        from cloudwatch_triage_agent.tools.cloudwatch import CloudWatchLogsTool

        tool = CloudWatchLogsTool()
        definition = tool.to_anthropic_tool()

        assert definition["name"] == "search_cloudwatch_logs"
        assert "description" in definition
        assert "input_schema" in definition
        assert "log_group" in definition["input_schema"]["properties"]

    @patch("cloudwatch_triage_agent.tools.cloudwatch.boto3.Session")
    @patch("cloudwatch_triage_agent.tools.cloudwatch.get_settings")
    @pytest.mark.asyncio
    async def test_execute_query(
        self, mock_settings: MagicMock, mock_session: MagicMock
    ) -> None:
        """Test query execution."""
        mock_settings.return_value = MagicMock(
            aws_region="us-east-1",
            aws_profile=None,
            max_log_results=100,
        )

        mock_client = MagicMock()
        mock_client.start_query.return_value = {"queryId": "test-query-id"}
        mock_client.get_query_results.return_value = {
            "status": "Complete",
            "results": [
                [{"field": "@message", "value": "Error occurred"}]
            ],
            "statistics": {"recordsMatched": 1},
        }
        mock_session.return_value.client.return_value = mock_client

        from cloudwatch_triage_agent.tools.cloudwatch import CloudWatchLogsTool

        tool = CloudWatchLogsTool()
        result = await tool.execute(
            log_group="/aws/lambda/test",
            query="fields @message | filter @message like /ERROR/",
            start_time="2024-01-01T00:00:00Z",
            end_time="2024-01-01T01:00:00Z",
        )

        assert "success" in result
        mock_client.start_query.assert_called_once()


class TestSlackTool:
    """Tests for Slack tool."""

    @patch("cloudwatch_triage_agent.tools.slack.WebClient")
    @patch("cloudwatch_triage_agent.tools.slack.get_settings")
    def test_requires_approval(
        self, mock_settings: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test that Slack tool requires approval."""
        mock_settings.return_value = MagicMock(
            slack_bot_token="xoxb-test",
            slack_default_channel="#test",
        )

        from cloudwatch_triage_agent.tools.slack import SlackTool

        tool = SlackTool()
        assert tool.requires_approval is True

    @patch("cloudwatch_triage_agent.tools.slack.WebClient")
    @patch("cloudwatch_triage_agent.tools.slack.get_settings")
    def test_format_investigation_report(
        self, mock_settings: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test Slack message formatting."""
        mock_settings.return_value = MagicMock(
            slack_bot_token="xoxb-test",
            slack_default_channel="#test",
        )

        from cloudwatch_triage_agent.tools.slack import SlackTool

        tool = SlackTool()
        text, blocks = tool.format_investigation_report(
            service="test-service",
            environment="prod",
            summary="Database connection timeout",
            root_causes=[
                {
                    "summary": "DB pool exhausted",
                    "evidence": ["Connection count: 100/100"],
                    "confidence": "high",
                }
            ],
            recommendations=["Increase pool size"],
        )

        assert "test-service" in text
        assert len(blocks) > 0
        assert blocks[0]["type"] == "header"
