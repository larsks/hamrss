"""Publisher configuration using pydantic-settings."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PublisherSettings(BaseSettings):
    """Publisher configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="HAMRSS_PUBLISHER_",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Server configuration
    host: str = Field(
        default="127.0.0.1",
        description="Host to bind the server to",
    )

    port: int = Field(
        default=8080,
        description="Port to bind the server to",
        ge=1,
        le=65535,
    )

    # Database configuration
    database_url: str = Field(
        default="postgresql://hamrss:hamrss@localhost/hamrss",
        description="PostgreSQL database URL",
    )

    # RSS feed configuration
    feed_title: str = Field(
        default="Ham RSS",
        description="Title for RSS feeds",
    )

    feed_description: str = Field(
        default="Latest ham radio equipment from various dealers",
        description="Description for RSS feeds",
    )

    feed_link: str = Field(
        default="http://localhost:8080",
        description="Base URL for the feed service",
    )

    max_items_per_feed: int = Field(
        default=500,
        description="Maximum number of items to include in each feed",
        ge=1,
        le=1000,
    )

    # Database connection pool settings
    db_pool_size: int = Field(
        default=5,
        description="Database connection pool size",
        ge=1,
        le=20,
    )

    db_pool_overflow: int = Field(
        default=10,
        description="Database connection pool overflow",
        ge=0,
        le=50,
    )


def get_settings() -> PublisherSettings:
    """Get the publisher settings instance."""
    return PublisherSettings()
