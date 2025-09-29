"""Database operations for storing scraped data."""

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select, update, and_
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from ..database.models import Product, ScrapeRun, ScrapeError, DriverStats
from ..model import Product as ProductModel

logger = logging.getLogger(__name__)


class StorageManager:
    """Manages storage operations for scraped data."""

    def __init__(self, session: Session):
        self.session = session

    def create_scrape_run(self, enabled_drivers: List[str]) -> int:
        """Create a new scrape run and return its ID."""
        scrape_run = ScrapeRun(
            total_drivers=len(enabled_drivers),
            enabled_drivers=json.dumps(enabled_drivers),
        )
        self.session.add(scrape_run)
        self.session.flush()
        self.session.refresh(scrape_run)

        logger.info(
            f"Created scrape run {scrape_run.id} with {len(enabled_drivers)} drivers"
        )
        return scrape_run.id

    def complete_scrape_run(
        self,
        scrape_run_id: int,
        status: str = "completed",
        error_message: Optional[str] = None,
    ) -> None:
        """Mark a scrape run as completed."""
        # Get final statistics
        driver_stats = (
            self.session.execute(
                select(DriverStats).where(DriverStats.scrape_run_id == scrape_run_id)
            )
            .scalars()
            .all()
        )

        completed_drivers = sum(
            1 for stat in driver_stats if stat.status == "completed"
        )
        failed_drivers = sum(1 for stat in driver_stats if stat.status == "failed")
        total_products = sum(stat.products_found for stat in driver_stats)

        # Update scrape run
        self.session.execute(
            update(ScrapeRun)
            .where(ScrapeRun.id == scrape_run_id)
            .values(
                completed_at=datetime.now(timezone.utc),
                status=status,
                completed_drivers=completed_drivers,
                failed_drivers=failed_drivers,
                total_products=total_products,
                error_message=error_message,
            )
        )

        logger.info(
            f"Completed scrape run {scrape_run_id}: {status}, "
            f"{completed_drivers} completed, {failed_drivers} failed, "
            f"{total_products} total products"
        )

    def create_driver_stats(
        self, scrape_run_id: int, driver_name: str, category: str
    ) -> int:
        """Create driver statistics entry and return its ID."""
        driver_stats = DriverStats(
            scrape_run_id=scrape_run_id,
            driver_name=driver_name,
            category=category,
        )
        self.session.add(driver_stats)
        self.session.commit()
        self.session.refresh(driver_stats)

        return driver_stats.id

    def complete_driver_stats(
        self,
        stats_id: int,
        products_found: int,
        products_new: int,
        products_updated: int,
        status: str = "completed",
        error_message: Optional[str] = None,
    ) -> None:
        """Update driver statistics with final results."""
        started_at = self.session.execute(
            select(DriverStats.started_at).where(DriverStats.id == stats_id)
        ).scalar_one()

        duration_seconds = int(
            (datetime.now(timezone.utc) - started_at).total_seconds()
        )

        self.session.execute(
            update(DriverStats)
            .where(DriverStats.id == stats_id)
            .values(
                completed_at=datetime.now(timezone.utc),
                duration_seconds=duration_seconds,
                products_found=products_found,
                products_new=products_new,
                products_updated=products_updated,
                status=status,
                error_message=error_message,
            )
        )

        logger.debug(
            f"Driver stats {stats_id}: {products_found} found, "
            f"{products_new} new, {products_updated} updated"
        )

    def store_products(
        self,
        products: List[ProductModel],
        driver_name: str,
        category: str,
        scrape_run_id: int,
    ) -> tuple[int, int]:
        """
        Store products and return (new_count, updated_count).

        Uses PostgreSQL's ON CONFLICT to handle deduplication based on URL and driver.
        """
        if not products:
            return 0, 0

        # Check existing products before inserting
        existing_urls = set()
        if products:
            existing_result = self.session.execute(
                select(Product.url).where(
                    and_(
                        Product.driver_name == driver_name,
                        Product.url.in_([p.url for p in products]),
                    )
                )
            )
            existing_urls = set(existing_result.scalars().all())

        new_count = 0
        updated_count = 0
        current_time = datetime.now(timezone.utc)

        for product in products:
            is_new = product.url not in existing_urls

            # Convert ProductModel to database Product
            product_data = {
                "url": product.url,
                "title": product.title,
                "description": product.description,
                "manufacturer": product.manufacturer,
                "model": product.model,
                "product_id": product.product_id,
                "location": product.location,
                "date_added": product.date_added,
                "price": product.price,
                "image_url": product.image_url,
                "author": product.author,
                "driver_name": driver_name,
                "category": category,
                "scraped_at": current_time,
                "scrape_run_id": scrape_run_id,
                "first_seen": current_time,
                "last_seen": current_time,
                "is_active": True,
            }

            # Always use PostgreSQL's INSERT ... ON CONFLICT for upsert
            stmt = insert(Product).values(product_data)
            stmt = stmt.on_conflict_do_update(
                index_elements=["url", "driver_name"],
                set_={
                    "title": stmt.excluded.title,
                    "description": stmt.excluded.description,
                    "manufacturer": stmt.excluded.manufacturer,
                    "model": stmt.excluded.model,
                    "product_id": stmt.excluded.product_id,
                    "location": stmt.excluded.location,
                    "date_added": stmt.excluded.date_added,
                    "price": stmt.excluded.price,
                    "image_url": stmt.excluded.image_url,
                    "author": stmt.excluded.author,
                    "category": stmt.excluded.category,
                    "scraped_at": stmt.excluded.scraped_at,
                    "scrape_run_id": stmt.excluded.scrape_run_id,
                    "last_seen": stmt.excluded.last_seen,
                    "is_active": True,
                    # Preserve first_seen for existing records
                    "first_seen": Product.first_seen,
                },
            )

            # Count as new or updated
            if is_new:
                new_count += 1
            else:
                updated_count += 1

            # Execute the upsert
            self.session.execute(stmt)

        self.session.commit()

        logger.info(
            f"Stored {len(products)} products for {driver_name}/{category}: "
            f"{new_count} new, {updated_count} updated"
        )

        return new_count, updated_count

    def mark_inactive_products(self, scrape_run_id: int) -> int:
        """
        Mark products as inactive if they weren't seen in the current scrape run.
        Returns the number of products marked as inactive.
        """
        # Mark products as inactive if they weren't updated in this scrape run
        result = self.session.execute(
            update(Product)
            .where(
                and_(
                    Product.scrape_run_id != scrape_run_id,
                    Product.is_active,
                )
            )
            .values(is_active=False)
        )

        self.session.commit()
        inactive_count = result.rowcount

        if inactive_count > 0:
            logger.info(f"Marked {inactive_count} products as inactive")

        return inactive_count

    def log_error(
        self,
        scrape_run_id: int,
        driver_name: str,
        error_type: str,
        error_message: str,
        category: Optional[str] = None,
        error_traceback: Optional[str] = None,
    ) -> None:
        """Log a scraping error."""
        error = ScrapeError(
            scrape_run_id=scrape_run_id,
            driver_name=driver_name,
            category=category,
            error_type=error_type,
            error_message=error_message,
            error_traceback=error_traceback,
        )
        self.session.add(error)
        self.session.commit()

        logger.error(f"Logged error for {driver_name}: {error_type} - {error_message}")

    def get_recent_scrape_runs(self, limit: int = 10) -> List[ScrapeRun]:
        """Get recent scrape runs for monitoring."""
        result = self.session.execute(
            select(ScrapeRun).order_by(ScrapeRun.started_at.desc()).limit(limit)
        )
        return result.scalars().all()

    def get_product_counts_by_driver(self) -> dict[str, int]:
        """Get active product counts by driver."""
        result = self.session.execute(
            select(Product.driver_name, Product.category).where(Product.is_active)
        )

        counts = {}
        for driver_name, category in result:
            key = f"{driver_name}/{category}"
            counts[key] = counts.get(key, 0) + 1

        return counts
