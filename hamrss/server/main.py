"""Main server entry point for the ham radio scraper."""

import logging
import sys
from typing import Optional

from ..config import get_settings, ServerSettings
from ..database.connection import init_database, close_database
from .scheduler import ScraperScheduler


def setup_logging(settings: ServerSettings) -> None:
    """Configure logging for the server."""
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper()),
        format=settings.log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Set specific logger levels
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.INFO)

    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured at {settings.log_level} level")


def main() -> None:
    """Main server function."""
    # Load configuration
    settings = get_settings()

    # Setup logging
    setup_logging(settings)

    logger = logging.getLogger(__name__)
    logger.info("Starting Ham Radio Scraper Server")
    logger.info(f"Configuration: {settings.scrape_interval_hours}h interval, "
                f"{len(settings.get_enabled_drivers())} drivers enabled")

    db_manager: Optional[object] = None
    scheduler: Optional[ScraperScheduler] = None

    try:
        # Initialize database
        logger.info("Initializing database connection")
        db_manager = init_database(settings)
        logger.info("Database initialized successfully")

        # Create and start scheduler
        scheduler = ScraperScheduler(settings, db_manager)
        logger.info("Starting scheduler")

        # This will run until shutdown signal is received
        scheduler.start()

    except Exception as e:
        logger.error(f"Server startup failed: {e}", exc_info=True)
        sys.exit(1)

    finally:
        # Cleanup
        logger.info("Shutting down server")

        if scheduler:
            scheduler.stop()

        if db_manager:
            close_database()

        logger.info("Server shutdown complete")


def run_server() -> None:
    """Entry point for the console script."""
    try:
        main()
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
        sys.exit(0)
    except Exception as e:
        print(f"Server failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_server()