"""Configuration management using pydantic-settings."""

import logging
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ..driver.discovery import get_available_driver_modules

logger = logging.getLogger(__name__)


class ServerSettings(BaseSettings):
    """Server configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="HAMRSS_IMPORTER_",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database configuration
    database_url: str = Field(
        default="postgresql://hamrss:hamrss@localhost/hamrss",
        description="PostgreSQL database URL",
    )

    # Scraping configuration
    scrape_interval_hours: int = Field(
        default=6,
        description="Interval between scraping runs in hours",
        ge=1,
        le=168,  # Max 1 week
    )

    enabled_drivers: str = Field(
        default="",
        description="Comma-separated list of driver module names to use for scraping. If empty, uses automatic discovery via entry points.",
    )

    def get_enabled_drivers(self) -> list[str]:
        """Parse enabled drivers into a list, using automatic discovery if empty."""
        if self.enabled_drivers.strip():
            # Use explicitly configured drivers
            return [s.strip() for s in self.enabled_drivers.split(",") if s.strip()]
        else:
            # Use automatic discovery
            discovered = get_available_driver_modules()
            if discovered:
                logger.info(f"Auto-discovered drivers: {discovered}")
                return discovered
            else:
                # Fallback to hardcoded list if discovery fails
                logger.warning("Driver discovery failed, using fallback drivers")
                return [
                    "hamrss.driver.mtc",
                    "hamrss.driver.randl",
                    "hamrss.driver.hro",
                    "hamrss.driver.qrz"
                ]

    # Playwright configuration
    playwright_server_url: str = Field(
        default="ws://127.0.0.1:3000/",
        description="WebSocket URL for the Playwright server",
    )

    # Logging configuration
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )

    log_format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Log message format string",
    )

    # Server configuration
    max_concurrent_drivers: int = Field(
        default=1,
        description="Maximum number of drivers to run concurrently",
        ge=1,
        le=10,
    )

    scrape_timeout_minutes: int = Field(
        default=30,
        description="Timeout for individual driver scraping in minutes",
        ge=5,
        le=120,
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


def get_settings() -> ServerSettings:
    """Get the application settings instance."""
    return ServerSettings()
