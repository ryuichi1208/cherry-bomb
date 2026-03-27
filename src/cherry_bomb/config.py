"""Application configuration using pydantic-settings."""

from enum import StrEnum

from pydantic import SecretStr
from pydantic_settings import BaseSettings


class LogFormat(StrEnum):
    """Log format choices."""

    json = "json"
    console = "console"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = {"env_prefix": "", "case_sensitive": True}

    # Anthropic
    ANTHROPIC_API_KEY: SecretStr
    CLAUDE_MODEL: str = "claude-sonnet-4-20250514"

    # Slack
    SLACK_BOT_TOKEN: SecretStr
    SLACK_SIGNING_SECRET: SecretStr
    SLACK_APP_TOKEN: SecretStr | None = None

    # AWS
    AWS_REGION: str = "ap-northeast-1"
    DYNAMODB_TABLE_NAME: str = "cherry-bomb-approvals"
    SQS_QUEUE_URL: str | None = None

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: LogFormat = LogFormat.json
