"""Database queries for RSS feed generation."""

import logging
from typing import List, Optional

from sqlalchemy import select, and_, desc
from sqlalchemy.orm import Session

from ..database.models import Product

logger = logging.getLogger(__name__)

# Driver name mappings
DRIVER_MAPPINGS = {
    "hro": "hamrss.driver.hro",
    "mtc": "hamrss.driver.mtc",
    "rlelectronics": "hamrss.driver.rlelectronics",
}


class FeedQueries:
    """Database queries for RSS feeds."""

    def __init__(self, session: Session):
        self.session = session

    def get_all_items(self, limit: int = 100) -> List[Product]:
        """Get all active items from all drivers."""
        query = (
            select(Product)
            .where(Product.is_active == True)
            .order_by(desc(Product.last_seen))
            .limit(limit)
        )
        return list(self.session.execute(query).scalars().all())

    def get_driver_items(self, driver_short_name: str, limit: int = 100) -> List[Product]:
        """Get all active items from a specific driver."""
        driver_name = DRIVER_MAPPINGS.get(driver_short_name)
        if not driver_name:
            logger.warning(f"Unknown driver short name: {driver_short_name}")
            return []

        query = (
            select(Product)
            .where(and_(
                Product.is_active == True,
                Product.driver_name == driver_name
            ))
            .order_by(desc(Product.last_seen))
            .limit(limit)
        )
        return list(self.session.execute(query).scalars().all())

    def get_category_items(
        self,
        driver_short_name: str,
        category: str,
        limit: int = 100
    ) -> List[Product]:
        """Get all active items from a specific driver and category."""
        driver_name = DRIVER_MAPPINGS.get(driver_short_name)
        if not driver_name:
            logger.warning(f"Unknown driver short name: {driver_short_name}")
            return []

        query = (
            select(Product)
            .where(and_(
                Product.is_active == True,
                Product.driver_name == driver_name,
                Product.category == category
            ))
            .order_by(desc(Product.last_seen))
            .limit(limit)
        )
        return list(self.session.execute(query).scalars().all())

    def get_available_drivers(self) -> List[str]:
        """Get list of available driver short names that have active products."""
        query = (
            select(Product.driver_name)
            .where(Product.is_active == True)
            .distinct()
        )

        full_names = self.session.execute(query).scalars().all()

        # Convert full driver names back to short names
        short_names = []
        reverse_mappings = {v: k for k, v in DRIVER_MAPPINGS.items()}
        for full_name in full_names:
            short_name = reverse_mappings.get(full_name, full_name)
            short_names.append(short_name)

        return sorted(short_names)

    def get_available_categories(self, driver_short_name: str) -> List[str]:
        """Get list of available categories for a specific driver."""
        driver_name = DRIVER_MAPPINGS.get(driver_short_name)
        if not driver_name:
            return []

        query = (
            select(Product.category)
            .where(and_(
                Product.is_active == True,
                Product.driver_name == driver_name
            ))
            .distinct()
        )

        categories = self.session.execute(query).scalars().all()
        return sorted([cat for cat in categories if cat])

    def get_feed_stats(self) -> dict:
        """Get statistics about available feeds."""
        stats = {
            "total_active_products": 0,
            "drivers": {},
            "categories": {}
        }

        # Total active products
        total_query = select(Product).where(Product.is_active == True)
        stats["total_active_products"] = len(list(self.session.execute(total_query).scalars().all()))

        # Driver stats
        for short_name, full_name in DRIVER_MAPPINGS.items():
            driver_query = select(Product).where(and_(
                Product.is_active == True,
                Product.driver_name == full_name
            ))
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