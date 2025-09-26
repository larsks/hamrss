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

        # Create title from driver prefix, description and price
        title_parts = []

        # Add driver prefix
        if driver_short:
            prefix = f"[{driver_short}]"
            if product.description:
                title_parts.append(f"{prefix} {product.description}")
            else:
                title_parts.append(f"{prefix} Ham Radio Equipment")
        elif product.description:
            title_parts.append(product.description)
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
        """Create HTML content for a product."""
        rows = []

        # Helper function to add row if value exists
        def add_row(label: str, value: str | None):
            if value:
                rows.append(
                    f"<tr><td><strong>{label}:</strong></td><td>{value}</td></tr>"
                )

        add_row("Description", product.description)
        add_row("Manufacturer", product.manufacturer)
        add_row("Model", product.model)
        add_row("Price", product.price)
        add_row("Location", product.location)
        add_row("Date Added", product.date_added)
        add_row(
            "Driver",
            product.driver_name.split(".")[-1]
            if product.driver_name and "." in product.driver_name
            else product.driver_name,
        )
        add_row("Category", product.category)

        if product.first_seen:
            add_row("First Seen", product.first_seen.strftime("%Y-%m-%d %H:%M:%S UTC"))
        if product.last_seen:
            add_row("Last Seen", product.last_seen.strftime("%Y-%m-%d %H:%M:%S UTC"))

        if product.url:
            rows.append(
                f'<tr><td><strong>Link:</strong></td><td><a href="{product.url}">View Item</a></td></tr>'
            )

        content = "<table border='1' cellpadding='5' cellspacing='0'>\n"
        content += "\n".join(rows)
        content += "\n</table>"

        # Add image if available
        if product.image_url:
            content += f'<br><img src="{product.image_url}" alt="Product Image" style="max-width: 300px;">'

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

