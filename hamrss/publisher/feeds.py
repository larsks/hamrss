"""RSS feed generation using feedgen."""

import logging
import re
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
            # Ensure timezone awareness
            if latest_update.tzinfo is None:
                latest_update = latest_update.replace(tzinfo=timezone.utc)
            fg.lastBuildDate(latest_update)
        else:
            fg.lastBuildDate(datetime.now(timezone.utc))

        # Add items
        for product in products:
            self._add_product_to_feed(fg, product)

        # Generate RSS and post-process to add Dublin Core creator elements
        rss_xml = fg.rss_str(pretty=True).decode("utf-8")
        return self._add_dublin_core_creators(rss_xml, products)

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
            pub_date = product.first_seen
            if pub_date.tzinfo is None:
                pub_date = pub_date.replace(tzinfo=timezone.utc)
            fe.pubDate(pub_date)
        elif product.scraped_at:
            pub_date = product.scraped_at
            if pub_date.tzinfo is None:
                pub_date = pub_date.replace(tzinfo=timezone.utc)
            fe.pubDate(pub_date)

        # Author information (callsign)
        if product.author:
            fe.author(name=product.author)

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
        """Create content for a product with title and description outside the metadata table."""
        content_parts = []

        # Add title (required field, always present)
        content_parts.append(f"<h3>{product.title}</h3>")

        # Add description if available (outside the table)
        if product.description:
            content_parts.append(f"<p>{product.description}</p><br/>")

        # Create metadata table for the rest of the information
        metadata_lines = []

        # Helper function to add line if value exists
        def add_line(label: str, value: str | None):
            if value:
                metadata_lines.append(f"{label}: {value}")

        add_line("Manufacturer", product.manufacturer)
        add_line("Model", product.model)
        add_line("Price", product.price)
        add_line("Location", product.location)
        add_line("Date Added", product.date_added)
        add_line("Author", product.author)
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

        # Add metadata table if there are any metadata lines
        if metadata_lines:
            content_parts.append("<pre>" + "\n".join(metadata_lines) + "</pre>")

        return "\n".join(content_parts)

    def _add_dublin_core_creators(self, rss_xml: str, products: list[Product]) -> str:
        """Post-process RSS XML to add Dublin Core creator elements for callsigns."""
        # First, add the Dublin Core namespace if not already present
        if 'xmlns:dc="http://purl.org/dc/elements/1.1/"' not in rss_xml:
            rss_xml = rss_xml.replace(
                '<rss xmlns:atom="http://www.w3.org/2005/Atom" xmlns:content="http://purl.org/rss/1.0/modules/content/" version="2.0">',
                '<rss xmlns:atom="http://www.w3.org/2005/Atom" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:dc="http://purl.org/dc/elements/1.1/" version="2.0">',
            )

        # Create a mapping of product URLs to authors for items that have authors
        url_to_author = {}
        for product in products:
            if product.author and product.url:
                url_to_author[product.url] = product.author

        # Add dc:creator elements to items that have authors
        if url_to_author:
            # Use regex to find and modify <item> elements
            def add_creator_to_item(match):
                item_content = match.group(1)

                # Find the link URL in this item
                link_match = re.search(r"<link>([^<]+)</link>", item_content)
                if link_match:
                    item_url = link_match.group(1)
                    if item_url in url_to_author:
                        author = url_to_author[item_url]
                        # Add dc:creator before the closing </item>
                        creator_element = (
                            f"      <dc:creator>{author}</dc:creator>\n    "
                        )
                        item_content = item_content.rstrip() + "\n" + creator_element

                return f"<item>\n{item_content}</item>"

            # Apply the transformation to all <item> elements
            rss_xml = re.sub(
                r"<item>\s*(.*?)\s*</item>",
                add_creator_to_item,
                rss_xml,
                flags=re.DOTALL,
            )

        return rss_xml

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
