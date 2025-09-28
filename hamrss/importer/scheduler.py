"""Task scheduling for the scraper server."""

import logging
import signal
import threading
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .config import ServerSettings
from ..database.connection import DatabaseManager
from .scraper import ScrapeOrchestrator

logger = logging.getLogger(__name__)


class ScraperScheduler:
    """Manages scheduled scraping tasks."""

    def __init__(
        self,
        settings: ServerSettings,
        db_manager: DatabaseManager,
    ):
        self.settings = settings
        self.db_manager = db_manager
        self.scheduler: Optional[BlockingScheduler] = None
        self.orchestrator: Optional[ScrapeOrchestrator] = None
        self.shutdown_event = threading.Event()

    def start(self) -> None:
        """Start the scheduler and begin scraping."""
        logger.info("Starting scraper scheduler")

        # Create orchestrator
        self.orchestrator = ScrapeOrchestrator(self.settings, self.db_manager)

        # Create and configure scheduler
        self.scheduler = BlockingScheduler(timezone="UTC")

        # Add the scraping job
        self.scheduler.add_job(
            func=self._run_scrape_job,
            trigger=IntervalTrigger(hours=self.settings.scrape_interval_hours),
            id="scrape_job",
            name="Ham Radio Catalog Scraper",
            max_instances=1,  # Prevent overlapping runs
            coalesce=True,  # Combine missed runs
            misfire_grace_time=300,  # 5 minutes grace for missed jobs
        )

        # Setup signal handlers for graceful shutdown
        self._setup_signal_handlers()

        # Run initial scrape immediately (optional - can be configured)
        if True:  # You can make this configurable
            logger.info("Running initial scrape")
            self._run_scrape_job()

        logger.info(
            f"Scheduler started with {self.settings.scrape_interval_hours}h interval"
        )

        # Start the scheduler - this will block until shutdown
        try:
            self.scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler interrupted")
        finally:
            self._internal_stop()

    def stop(self) -> None:
        """Stop the scheduler gracefully (external call)."""
        self.shutdown_event.set()
        self._internal_stop()

    def _internal_stop(self) -> None:
        """Internal stop method to avoid double shutdown."""
        logger.info("Stopping scraper scheduler")

        if self.scheduler and self.scheduler.running:
            try:
                self.scheduler.shutdown(wait=False)  # Don't wait to avoid blocking
                logger.info("Scheduler stopped")
            except Exception:
                # APScheduler may throw errors during shutdown - ignore them
                logger.info("Scheduler stopped")

    def _run_scrape_job(self) -> None:
        """Execute a scraping job."""
        job_start = datetime.now(timezone.utc)
        logger.info(f"Starting scheduled scrape job at {job_start}")

        try:
            if not self.orchestrator:
                logger.error("Orchestrator not initialized")
                return

            success = self.orchestrator.run_scrape_cycle()

            duration = datetime.now(timezone.utc) - job_start
            status = "successful" if success else "failed"

            logger.info(
                f"Scrape job completed: {status}, duration: {duration.total_seconds():.1f}s"
            )

        except Exception as e:
            duration = datetime.now(timezone.utc) - job_start
            logger.error(
                f"Scrape job failed after {duration.total_seconds():.1f}s: {e}",
                exc_info=True,
            )

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""

        def signal_handler(signum, frame):
            logger.info("Received signal, initiating graceful shutdown")
            self.shutdown_event.set()
            if self.scheduler and self.scheduler.running:
                self.scheduler.shutdown(wait=False)

        # Use standard signal handling for sync operations
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

    def get_status(self) -> dict:
        """Get current scheduler status."""
        if not self.scheduler:
            return {"status": "not_started"}

        jobs = self.scheduler.get_jobs()
        jobs[0] if jobs else None

        status = {
            "status": "running" if self.scheduler.running else "stopped",
            "next_run": None,  # BlockingScheduler doesn't expose next_run_time easily
            "interval_hours": self.settings.scrape_interval_hours,
        }

        # Add orchestrator health check if available
        if self.orchestrator:
            try:
                health = self.orchestrator.health_check()
                status["health"] = health
            except Exception as e:
                logger.error(f"Health check failed: {e}")
                status["health"] = {"error": str(e)}

        return status

    def trigger_immediate_scrape(self) -> bool:
        """Trigger an immediate scrape run (for manual triggering)."""
        logger.info("Triggering immediate scrape")

        try:
            if not self.orchestrator:
                logger.error("Orchestrator not initialized")
                return False

            success = self.orchestrator.run_scrape_cycle()
            logger.info(
                f"Manual scrape completed: {'success' if success else 'failed'}"
            )
            return success

        except Exception as e:
            logger.error(f"Manual scrape failed: {e}", exc_info=True)
            return False
