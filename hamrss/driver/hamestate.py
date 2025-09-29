"""HamEstate.com RSS feed driver for ham radio equipment."""

import requests
import feedparser
from bs4 import BeautifulSoup
import re
from typing import Optional

from .base import BaseCatalog
from .config import BaseDriverSettings
from ..model import Product


class HamEstateSettings(BaseDriverSettings):
    """HamEstate driver configuration loaded from environment variables."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class Catalog(BaseCatalog):
    """HamEstate.com RSS feed scraper for ham radio equipment."""

    def __init__(self, playwright_server=None):
        super().__init__(playwright_server)
        self.settings = HamEstateSettings()
        self.session = requests.Session()
        self.base_url = "https://www.hamestate.com"
        self.equipment_categories_url = (
            f"{self.base_url}/product-category/ham_equipment/"
        )

        # Set reasonable headers to avoid being blocked
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
            }
        )

        # Cache categories to avoid repeated requests
        self._cached_categories: Optional[list[str]] = None

    def get_categories(self) -> list[str]:
        """Get available categories by scraping the main equipment page."""
        # Return cached categories if available
        if self._cached_categories is not None:
            return self._cached_categories

        try:
            self.logger.info("Discovering categories from HamEstate.com...")
            response = self.session.get(
                self.equipment_categories_url, timeout=self.settings.timeout
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            categories = []

            # Find all category links in the equipment section
            # Look for links that contain product-category/ham_equipment/ followed by a category slug
            category_links = soup.find_all(
                "a", href=re.compile(r"/product-category/ham_equipment/[^/]+/$")
            )

            for link in category_links:
                href = link.get("href")
                if href:
                    # Extract the category slug from the URL
                    # e.g., "/product-category/ham_equipment/amps/" -> "amps"
                    parts = href.rstrip("/").split("/")
                    if len(parts) >= 3 and parts[-2] == "ham_equipment":
                        category_slug = parts[-1]
                        if category_slug and category_slug not in categories:
                            categories.append(category_slug)

            categories = sorted(categories)
            self.logger.info(f"Found {len(categories)} categories")

            # Cache the result
            self._cached_categories = categories
            return categories

        except requests.RequestException as e:
            self.logger.error(f"Network error discovering categories: {e}")
            return []
        except Exception as e:
            self.logger.error(f"Error discovering categories: {e}")
            return []

    def _build_rss_url(self, category_name: str) -> str:
        """Build RSS feed URL for a given category."""
        return f"{self.base_url}/product-category/ham_equipment/{category_name}/feed/"

    def _fetch_rss_feed(self, url: str):
        """Fetch and parse RSS feed."""
        try:
            self.logger.info(f"Fetching RSS feed: {url}")
            response = self.session.get(url, timeout=self.settings.timeout)
            response.raise_for_status()

            # Check if we got an empty response
            if not response.content:
                self.logger.warning(f"Empty RSS feed response from {url}")
                return None

            # Parse the RSS feed content
            feed = feedparser.parse(response.content)

            if hasattr(feed, "bozo") and feed.bozo:
                self.logger.warning(
                    f"RSS feed parsing had issues: {feed.bozo_exception}"
                )

            # Check if the feed has any entries
            if not hasattr(feed, "entries") or len(feed.entries) == 0:
                self.logger.info(f"RSS feed contains no entries: {url}")

            return feed

        except requests.RequestException as e:
            self.logger.error(f"Network error fetching RSS feed from {url}: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Error fetching RSS feed from {url}: {e}")
            raise

    def _extract_products_from_feed(self, feed) -> list[Product]:
        """Extract product information from RSS feed entries."""
        products = []

        for entry in feed.entries:
            try:
                product_data = {}

                # Extract title
                if hasattr(entry, "title") and entry.title:
                    title = entry.title.strip()
                    product_data["title"] = title

                    # Try to extract manufacturer and model from title
                    manufacturer, model = self._extract_manufacturer_model_from_title(
                        title
                    )
                    if manufacturer:
                        product_data["manufacturer"] = manufacturer
                    if model:
                        product_data["model"] = model

                # Extract URL
                if hasattr(entry, "link") and entry.link:
                    product_data["url"] = entry.link.strip()

                # Extract description from summary or content
                if hasattr(entry, "summary") and entry.summary:
                    product_data["description"] = entry.summary.strip()
                elif hasattr(entry, "content") and entry.content:
                    # content is usually a list, take the first one
                    if isinstance(entry.content, list) and len(entry.content) > 0:
                        product_data["description"] = entry.content[0].value.strip()

                # Extract date
                if hasattr(entry, "published") and entry.published:
                    product_data["date_added"] = entry.published

                # Extract author
                if hasattr(entry, "author") and entry.author:
                    author = entry.author.strip()
                    product_data["author"] = author

                # Only create Product if we have the required fields
                if "title" in product_data and "url" in product_data:
                    product = Product(**product_data)
                    products.append(product)

            except Exception as e:
                self.logger.error(f"Error extracting product from RSS entry: {e}")
                continue

        return products

    def get_items(
        self, category_name: str, max_items: int | None = None
    ) -> list[Product]:
        """Get items from specified category."""
        # Validate that the category exists
        available_categories = self.get_categories()
        if category_name not in available_categories:
            raise ValueError(
                f"Unknown category: {category_name}. Available categories: {available_categories}"
            )

        rss_url = self._build_rss_url(category_name)

        try:
            feed = self._fetch_rss_feed(rss_url)

            # Handle empty or None feed
            if feed is None:
                self.logger.warning(f"No feed data for category '{category_name}'")
                return []

            products = self._extract_products_from_feed(feed)

            # Apply limit if specified
            if max_items and len(products) > max_items:
                products = products[:max_items]
                self.logger.info(f"Limited to {max_items} items")

            self.logger.info(
                f"Found {len(products)} products in category '{category_name}'"
            )
            return products

        except requests.RequestException as e:
            self.logger.error(f"Network error scraping category '{category_name}': {e}")
            return []
        except Exception as e:
            self.logger.error(f"Error scraping category '{category_name}': {e}")
            return []
