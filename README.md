# CloudWatch Log Triage Agent

AI-powered incident investigation tool using Anthropic Claude.

## Overview

This agent accelerates initial incident response by:
- Extracting root cause candidates from CloudWatch Logs
- Correlating with GitHub Actions deployments and CloudTrail changes
- Generating investigation reports with approval-gated Slack notifications

## Architecture

```
User → Triage Controller → Investigator Controller → Summary → (Approval) → Slack
```

### Controllers

- **Triage Controller**: Determines service, environment, time range, and initial investigation strategy
- **Investigator Controller**: Performs iterative log analysis using Claude with tool use

### Tools

| Tool | Type | Description |
|------|------|-------------|
| `search_cloudwatch_logs` | Read | CloudWatch Logs Insights query |
| `get_github_deployments` | Read | GitHub Deployments API |
| `get_cloudtrail_events` | Read | AWS CloudTrail events |
| `post_slack_message` | Action | Slack notification (requires approval) |

## Installation

```bash
# Clone the repository
git clone https://github.com/your-org/cloudwatch-triage-agent.git
cd cloudwatch-triage-agent

# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Sync dependencies
uv sync
```

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Required environment variables:

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `AWS_REGION` | AWS region (default: ap-northeast-1) |
| `AWS_PROFILE` | AWS profile name (optional) |
| `GITHUB_TOKEN` | GitHub personal access token |
| `GITHUB_OWNER` | GitHub repository owner |
| `GITHUB_REPO` | GitHub repository name |
| `SLACK_BOT_TOKEN` | Slack bot OAuth token |

### Service Configuration

Configure service log groups in `src/cloudwatch_triage_agent/config.py`:

```python
service_log_groups = {
    "api-service": {
        "dev": "/aws/lambda/api-service-dev",
        "prod": "/aws/lambda/api-service-prod",
    },
    "worker-service": {
        "dev": "/aws/ecs/worker-dev",
        "prod": "/aws/ecs/worker-prod",
    },
}
```

## Usage

### CLI Commands

```bash
# Investigate an incident
uv run triage investigate "500 errors in checkout API since 10am"

# Investigate with service/environment hints
uv run triage investigate -s payment-service -e prod "Payment failures"

# Skip confirmation prompts
uv run triage investigate -y "Database timeout errors"

# List configured services
uv run triage list-services

# Check configuration
uv run triage check-config
```

### Programmatic Usage

```python
import asyncio
from cloudwatch_triage_agent.orchestrator import TriageOrchestrator

async def main():
    orchestrator = TriageOrchestrator()
    report = await orchestrator.run(
        symptoms="500 errors in checkout API since 10am",
        skip_confirmation=True,
    )
    print(f"Root cause: {report.root_causes[0].summary}")

asyncio.run(main())
```

## MVP Flow

1. User describes incident symptoms
2. Triage Controller analyzes and determines investigation parameters
3. User confirms/modifies parameters
4. Investigator Controller:
   - Searches CloudWatch Logs for errors
   - Checks GitHub deployments
   - Checks CloudTrail for infrastructure changes
   - Correlates timing and generates root cause candidates
5. Agent generates TOP 3 root cause candidates with evidence
6. User reviews Slack message draft
7. After approval, posts to Slack

## Out of Scope

- Automatic remediation
- Write operations to AWS
- Metrics analysis
- Automatic postmortem generation

## Development

```bash
# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=cloudwatch_triage_agent

# Type checking
uv run mypy src/

# Linting
uv run ruff check src/
```

## License

MIT
