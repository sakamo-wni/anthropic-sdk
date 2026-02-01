"""GitHub Deployments API tool."""

import json
from datetime import datetime
from typing import Any

from github import Auth, Github
from github.GithubException import GithubException

from ..config import get_settings
from .base import ReadOnlyTool


class GitHubDeploymentsTool(ReadOnlyTool):
    """Tool for fetching GitHub deployments information."""

    def __init__(self) -> None:
        """Initialize GitHub client."""
        settings = get_settings()
        auth = Auth.Token(settings.github_token)
        self._github = Github(auth=auth)
        self._owner = settings.github_owner
        self._repo = settings.github_repo

    @property
    def name(self) -> str:
        return "get_github_deployments"

    @property
    def description(self) -> str:
        return """Get recent GitHub deployments for a specific environment.

Use this tool to find recent deployments that may have caused issues.
Returns deployment details including commit SHA, timestamp, status, and creator.

Environments: 'dev' or 'prod'"""

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "environment": {
                    "type": "string",
                    "enum": ["dev", "prod"],
                    "description": "Deployment environment to query",
                },
                "since": {
                    "type": "string",
                    "description": "Only return deployments after this time (ISO 8601 format)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of deployments to return (default: 10)",
                    "default": 10,
                },
            },
            "required": ["environment"],
        }

    async def execute(
        self,
        environment: str,
        since: str | None = None,
        limit: int = 10,
        **kwargs: Any,
    ) -> str:
        """Fetch GitHub deployments for the specified environment."""
        try:
            repo = self._github.get_repo(f"{self._owner}/{self._repo}")
            deployments = repo.get_deployments(environment=environment)

            since_dt = None
            if since:
                since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))

            results = []
            count = 0
            for deployment in deployments:
                if count >= limit:
                    break

                created_at = deployment.created_at
                if since_dt and created_at < since_dt:
                    continue

                # Get deployment status
                statuses = list(deployment.get_statuses())
                latest_status = statuses[0] if statuses else None

                results.append(
                    {
                        "deployment_id": deployment.id,
                        "environment": deployment.environment,
                        "ref": deployment.ref,
                        "sha": deployment.sha,
                        "created_at": created_at.isoformat(),
                        "description": deployment.description or "",
                        "creator": deployment.creator.login if deployment.creator else "unknown",
                        "status": latest_status.state if latest_status else "unknown",
                        "status_description": (
                            latest_status.description if latest_status else ""
                        ),
                    }
                )
                count += 1

            return json.dumps(
                {
                    "success": True,
                    "repository": f"{self._owner}/{self._repo}",
                    "environment": environment,
                    "deployment_count": len(results),
                    "deployments": results,
                },
                indent=2,
            )

        except GithubException as e:
            return json.dumps(
                {
                    "success": False,
                    "error": f"GitHub API error: {e.data.get('message', str(e))}",
                    "status": e.status,
                }
            )
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def close(self) -> None:
        """Close the GitHub client connection."""
        self._github.close()
