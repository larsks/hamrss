"""Shared configuration patterns for drivers."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseDriverSettings(BaseSettings):
    """Base settings class for all drivers."""

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    max_items: int = Field(default=1000, description="Maximum items to fetch per category")
    timeout: int = Field(default=30, description="Request timeout in seconds")


class AuthenticatedDriverSettings(BaseDriverSettings):
    """Settings for drivers requiring authentication."""

    username: str = Field(default="", description="Username for authentication")
    password: str = Field(default="", description="Password for authentication")