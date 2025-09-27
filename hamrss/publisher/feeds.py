"""RSS feed generation using feedgen."""

import logging
from datetime import datetime, timezone
from urllib.parse import urljoin

from feedgen.feed import FeedGenerator

from ..database.models import Product
from .config import PublisherSettings

logger = logging.getLogger(__name__)


class RSSFeedGenerator:
    """Generates RSS feeds from product data."""

    def __init__(self, settings: PublisherSettings):
        self.settings = settings

    def create_feed(
        self,
        products: list[Product],
        title: str,
        description: str,
        feed_path: str = "/feed",
    ) -> str:
        """Create an RSS feed from a list of products."""
        fg = FeedGenerator()

        # Feed metadata
        fg.title(title)
        fg.link(href=self.settings.feed_link, rel="alternate")
        fg.description(description)
        fg.language("en")
        fg.generator("hamrss-publisher")

        # Feed self link
        feed_url = urljoin(self.settings.feed_link, feed_path)
        fg.link(href=feed_url, rel="self")

        # Add last update time
        if products:
            latest_update = max(
                product.last_seen for product in products if product.last_seen
            )
            fg.lastBuildDate(latest_update)
        else:
            fg.lastBuildDate(datetime.now(timezone.utc))

        # Add items
        for product in products:
            self._add_product_to_feed(fg, product)

        return fg.rss_str(pretty=True).decode("utf-8")

    def _add_product_to_feed(self, fg: FeedGenerator, product: Product) -> None:
        """Add a single product as an RSS item."""
        fe = fg.add_entry()

        # Extract short driver name for prefix
        driver_short = None
        if product.driver_name:
            driver_short = (
                product.driver_name.split(".")[-1]
                if "." in product.driver_name
                else product.driver_name
            )

        # Create title from driver prefix, product title and price
        title_parts = []

        # Add driver prefix
        if driver_short:
            prefix = f"[{driver_short}]"
            if product.title:
                title_parts.append(f"{prefix} {product.title}")
            else:
                title_parts.append(f"{prefix} Ham Radio Equipment")
        elif product.title:
            title_parts.append(product.title)
        else:
            title_parts.append("Ham Radio Equipment")

        # Add price
        if product.price:
            title_parts.append(f"- {product.price}")

        title = " ".join(title_parts)

        # Required fields
        fe.title(title)
        fe.id(product.url or f"product-{product.id}")
        fe.link(href=product.url or "")

        # Description/content - create HTML table with all product info
        content = self._create_product_content(product)
        fe.description(content)

        # Publication date
        if product.first_seen:
            fe.pubDate(product.first_seen)
        elif product.scraped_at:
            fe.pubDate(product.scraped_at)

        # Categories
        categories = []
        if driver_short:
            categories.append(driver_short)
        if product.category:
            categories.append(product.category)
        if product.manufacturer:
            categories.append(product.manufacturer)

        for category in categories:
            fe.category(term=category)

    def _create_product_content(self, product: Product) -> str:
        """Create plain-text content for a product."""
        lines = []

        # Helper function to add line if value exists
        def add_line(label: str, value: str | None):
            if value:
                lines.append(f"{label}: {value}")

        add_line("Title", product.title)
        add_line("Description", product.description)
        add_line("Manufacturer", product.manufacturer)
        add_line("Model", product.model)
        add_line("Price", product.price)
        add_line("Location", product.location)
        add_line("Date Added", product.date_added)
        add_line(
            "Driver",
            product.driver_name.split(".")[-1]
            if product.driver_name and "." in product.driver_name
            else product.driver_name,
        )
        add_line("Category", product.category)

        if product.first_seen:
            add_line("First Seen", product.first_seen.strftime("%Y-%m-%d %H:%M:%S UTC"))
        if product.last_seen:
            add_line("Last Seen", product.last_seen.strftime("%Y-%m-%d %H:%M:%S UTC"))

        if product.url:
            add_line("Link", product.url)

        content = "<pre>" + "\n".join(lines) + "</pre>"

        return content

    def create_all_items_feed(self, products: list[Product]) -> str:
        """Create feed for all items."""
        return self.create_feed(
            products,
            title=self.settings.feed_title,
            description=self.settings.feed_description,
            feed_path="/feed",
        )

    def create_driver_feed(self, products: list[Product], driver: str) -> str:
        """Create feed for a specific driver."""
        return self.create_feed(
            products,
            title=f"{self.settings.feed_title} - {driver.upper()}",
            description=f"Items from {driver.upper()} driver",
            feed_path=f"/feed/{driver}",
        )

    def create_category_feed(
        self, products: list[Product], driver: str, category: str
    ) -> str:
        """Create feed for a specific driver and category."""
        return self.create_feed(
            products,
            title=f"{self.settings.feed_title} - {driver.upper()} {category.title()}",
            description=f"{category.title()} items from {driver.upper()} driver",
            feed_path=f"/feed/{driver}/{category}",
        )
