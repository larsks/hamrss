"""Database queries for RSS feed generation."""

import logging
from typing import List

from sqlalchemy import select, and_, desc
from sqlalchemy.orm import Session

from ..database.models import Product

logger = logging.getLogger(__name__)


class FeedQueries:
    """Database queries for RSS feeds."""

    def __init__(self, session: Session):
        self.session = session

    def _get_driver_mappings(self) -> dict[str, str]:
        """Build mapping from short driver names to full driver names from database."""
        query = select(Product.driver_name).where(Product.is_active).distinct()
        full_names = self.session.execute(query).scalars().all()

        mappings = {}
        for full_name in full_names:
            # Extract short name as last dot-delimited component
            short_name = full_name.split(".")[-1]
            mappings[short_name] = full_name

        return mappings

    def get_all_items(self, limit: int = 100) -> List[Product]:
        """Get all active items from all drivers."""
        query = (
            select(Product)
            .where(Product.is_active)
            .order_by(desc(Product.last_seen))
            .limit(limit)
        )
        return list(self.session.execute(query).scalars().all())

    def get_driver_items(
        self, driver_short_name: str, limit: int = 100
    ) -> List[Product]:
        """Get all active items from a specific driver."""
        driver_mappings = self._get_driver_mappings()
        driver_name = driver_mappings.get(driver_short_name)
        if not driver_name:
            logger.warning(f"Unknown driver short name: {driver_short_name}")
            return []

        query = (
            select(Product)
            .where(and_(Product.is_active, Product.driver_name == driver_name))
            .order_by(desc(Product.last_seen))
            .limit(limit)
        )
        return list(self.session.execute(query).scalars().all())

    def get_category_items(
        self, driver_short_name: str, category: str, limit: int = 100
    ) -> List[Product]:
        """Get all active items from a specific driver and category."""
        driver_mappings = self._get_driver_mappings()
        driver_name = driver_mappings.get(driver_short_name)
        if not driver_name:
            logger.warning(f"Unknown driver short name: {driver_short_name}")
            return []

        query = (
            select(Product)
            .where(
                and_(
                    Product.is_active,
                    Product.driver_name == driver_name,
                    Product.category == category,
                )
            )
            .order_by(desc(Product.last_seen))
            .limit(limit)
        )
        return list(self.session.execute(query).scalars().all())

    def get_available_drivers(self) -> List[str]:
        """Get list of available driver short names that have active products."""
        driver_mappings = self._get_driver_mappings()
        return sorted(driver_mappings.keys())

    def get_available_categories(self, driver_short_name: str) -> List[str]:
        """Get list of available categories for a specific driver."""
        driver_mappings = self._get_driver_mappings()
        driver_name = driver_mappings.get(driver_short_name)
        if not driver_name:
            return []

        query = (
            select(Product.category)
            .where(and_(Product.is_active, Product.driver_name == driver_name))
            .distinct()
        )

        categories = self.session.execute(query).scalars().all()
        return sorted([cat for cat in categories if cat])

    def get_feed_stats(self) -> dict:
        """Get statistics about available feeds."""
        stats = {"total_active_products": 0, "drivers": {}, "categories": {}}

        # Total active products
        total_query = select(Product).where(Product.is_active)
        stats["total_active_products"] = len(
            list(self.session.execute(total_query).scalars().all())
        )

        # Driver stats
        driver_mappings = self._get_driver_mappings()
        for short_name, full_name in driver_mappings.items():
            driver_query = select(Product).where(
                and_(Product.is_active, Product.driver_name == full_name)
            )
            count = len(list(self.session.execute(driver_query).scalars().all()))
            if count > 0:
                stats["drivers"][short_name] = count

        # Category stats by driver
        for short_name in stats["drivers"]:
            categories = self.get_available_categories(short_name)
            for category in categories:
                items = self.get_category_items(short_name, category, limit=999999)
                key = f"{short_name}/{category}"
                stats["categories"][key] = len(items)

        return stats
