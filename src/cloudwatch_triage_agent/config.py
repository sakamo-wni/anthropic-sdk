"""Configuration management for CloudWatch Triage Agent."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Anthropic
    anthropic_api_key: str = Field(..., description="Anthropic API key")
    anthropic_model: str = Field(
        default="claude-sonnet-4-20250514", description="Claude model to use"
    )

    # AWS
    aws_region: str = Field(default="ap-northeast-1", description="AWS region")
    aws_profile: str | None = Field(default=None, description="AWS profile name")

    # GitHub
    github_token: str = Field(..., description="GitHub personal access token or App token")
    github_owner: str = Field(..., description="GitHub repository owner")
    github_repo: str = Field(..., description="GitHub repository name")

    # Slack
    slack_bot_token: str = Field(..., description="Slack bot OAuth token")
    slack_default_channel: str = Field(
        default="#incidents", description="Default Slack channel for notifications"
    )

    # Service configuration
    service_log_groups: dict[str, dict[str, str]] = Field(
        default_factory=lambda: {
            "example-service": {
                "dev": "/aws/lambda/example-service-dev",
                "prod": "/aws/lambda/example-service-prod",
            }
        },
        description="Mapping of service names to log groups per environment",
    )

    # Investigation defaults
    default_lookback_minutes: int = Field(
        default=60, description="Default time range for log search (minutes)"
    )
    max_log_results: int = Field(
        default=100, description="Maximum log results to return"
    )

    def get_log_group(self, service: str, environment: str) -> str:
        """Get log group name for a service and environment."""
        if service not in self.service_log_groups:
            raise ValueError(f"Unknown service: {service}")
        env_groups = self.service_log_groups[service]
        if environment not in env_groups:
            raise ValueError(f"Unknown environment '{environment}' for service '{service}'")
        return env_groups[environment]


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
