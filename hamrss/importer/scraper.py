"""Scraping orchestration and driver management."""

import importlib
import logging
import traceback
from typing import Optional

from .config import ServerSettings
from ..database.connection import DatabaseManager
from ..playwright_server import PlaywrightServer
from ..protocol import Catalog
from .storage import StorageManager

logger = logging.getLogger(__name__)


class DriverScraper:
    """Handles scraping for a single driver."""

    def __init__(
        self,
        settings: ServerSettings,
        playwright_server: PlaywrightServer,
    ):
        self.settings = settings
        self.playwright_server = playwright_server

    def scrape_driver(
        self,
        driver_name: str,
        scrape_run_id: int,
        db_manager: DatabaseManager,
    ) -> bool:
        """
        Scrape all categories for a single driver.
        Returns True if successful, False if failed.
        """
        logger.info(f"Starting scrape for driver: {driver_name}")

        # Create a separate session for this driver
        with db_manager.get_session() as session:
            storage = StorageManager(session)

            try:
                # Load the driver
                catalog = self._load_driver(driver_name)
                if not catalog:
                    return False

                # Get available categories
                categories = catalog.get_categories()
                logger.info(f"Driver {driver_name} has categories: {categories}")

                total_products = 0
                total_new = 0
                total_updated = 0

                # Scrape each category
                for category in categories:
                    stats_id = None
                    try:
                        # Create driver stats entry
                        stats_id = storage.create_driver_stats(
                            scrape_run_id, driver_name, category
                        )

                        logger.info(f"Scraping {driver_name}/{category}")

                        # Get products from the driver
                        products = catalog.get_items(category)
                        logger.info(
                            f"Found {len(products)} products in {driver_name}/{category}"
                        )

                        # Store products in database
                        new_count, updated_count = storage.store_products(
                            products, driver_name, category, scrape_run_id
                        )

                        # Update statistics
                        storage.complete_driver_stats(
                            stats_id,
                            products_found=len(products),
                            products_new=new_count,
                            products_updated=updated_count,
                            status="completed",
                        )

                        total_products += len(products)
                        total_new += new_count
                        total_updated += updated_count

                    except Exception as e:
                        error_msg = f"Failed to scrape {driver_name}/{category}: {e}"
                        logger.error(error_msg)

                        # Log error to database
                        storage.log_error(
                            scrape_run_id=scrape_run_id,
                            driver_name=driver_name,
                            category=category,
                            error_type=type(e).__name__,
                            error_message=str(e),
                            error_traceback=traceback.format_exc(),
                        )

                        # Update stats as failed if we created them
                        if stats_id:
                            storage.complete_driver_stats(
                                stats_id,
                                products_found=0,
                                products_new=0,
                                products_updated=0,
                                status="failed",
                                error_message=str(e),
                            )

                logger.info(
                    f"Completed scrape for {driver_name}: {total_products} products, "
                    f"{total_new} new, {total_updated} updated"
                )
                return True

            except Exception as e:
                error_msg = f"Fatal error scraping driver {driver_name}: {e}"
                logger.error(error_msg)

                # Log the driver-level error
                storage.log_error(
                    scrape_run_id=scrape_run_id,
                    driver_name=driver_name,
                    error_type=type(e).__name__,
                    error_message=str(e),
                    error_traceback=traceback.format_exc(),
                )

                return False

    def _load_driver(self, driver_name: str) -> Optional[Catalog]:
        """Load a driver module and return its Catalog instance."""
        try:
            module = importlib.import_module(driver_name)
            catalog_class = module.Catalog

            # Create catalog instance with playwright server
            catalog = catalog_class(self.playwright_server)

            return catalog

        except Exception as e:
            logger.error(f"Failed to load driver {driver_name}: {e}")
            return None


class ScrapeOrchestrator:
    """Orchestrates the entire scraping process."""

    def __init__(
        self,
        settings: ServerSettings,
        db_manager: DatabaseManager,
    ):
        self.settings = settings
        self.db_manager = db_manager
        self.playwright_server = PlaywrightServer(settings.playwright_server_url)

    def run_scrape_cycle(self) -> bool:
        """
        Run a complete scraping cycle for all enabled drivers.
        Returns True if successful, False if failed.
        """
        logger.info("Starting scrape cycle")

        with self.db_manager.get_session() as session:
            storage = StorageManager(session)

            try:
                # Create scrape run
                scrape_run_id = storage.create_scrape_run(
                    self.settings.get_enabled_drivers()
                )

                # Create driver scraper
                driver_scraper = DriverScraper(self.settings, self.playwright_server)

                # Track results
                successful_drivers = 0
                failed_drivers = 0

                # Run drivers sequentially (simpler than async concurrency)
                for driver_name in self.settings.get_enabled_drivers():
                    try:
                        success = driver_scraper.scrape_driver(
                            driver_name, scrape_run_id, self.db_manager
                        )
                        if success:
                            successful_drivers += 1
                        else:
                            failed_drivers += 1
                    except Exception as e:
                        logger.error(f"Driver {driver_name} failed with exception: {e}")
                        failed_drivers += 1

                        # Log timeout or other errors
                        storage.log_error(
                            scrape_run_id=scrape_run_id,
                            driver_name=driver_name,
                            error_type=type(e).__name__,
                            error_message=str(e),
                            error_traceback=traceback.format_exc(),
                        )

                # Mark inactive products
                storage.mark_inactive_products(scrape_run_id)

                # Complete the scrape run
                status = "completed" if failed_drivers == 0 else "partial"
                storage.complete_scrape_run(scrape_run_id, status)

                logger.info(
                    f"Scrape cycle completed: {successful_drivers} successful, "
                    f"{failed_drivers} failed drivers"
                )

                return failed_drivers == 0

            except Exception as e:
                error_msg = f"Scrape cycle failed: {e}"
                logger.error(error_msg)

                # Mark scrape run as failed
                storage.complete_scrape_run(
                    scrape_run_id, status="failed", error_message=str(e)
                )

                return False

    def health_check(self) -> dict:
        """Perform health checks and return status."""
        health = {
            "database": False,
            "recent_scrapes": [],
            "product_counts": {},
        }

        try:
            # Check database health
            health["database"] = self.db_manager.health_check()

            if health["database"]:
                with self.db_manager.get_session() as session:
                    storage = StorageManager(session)

                    # Get recent scrape runs
                    recent_runs = storage.get_recent_scrape_runs(limit=5)
                    health["recent_scrapes"] = [
                        {
                            "id": run.id,
                            "started_at": run.started_at.isoformat(),
                            "status": run.status,
                            "total_products": run.total_products,
                        }
                        for run in recent_runs
                    ]

                    # Get product counts
                    health["product_counts"] = storage.get_product_counts_by_driver()

        except Exception as e:
            logger.error(f"Health check failed: {e}")

        return health
