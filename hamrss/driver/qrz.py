"""QRZ RSS feed driver for ham radio gear for sale."""

import requests
import feedparser
import re
from enum import Enum
from pydantic_settings import SettingsConfigDict

from .base import BaseCatalog, EnumCatalogMixin
from .config import AuthenticatedDriverSettings
from ..model import Product


class QRZSettings(AuthenticatedDriverSettings):
    """QRZ driver configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="HAMRSS_QRZ_",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


class Category(str, Enum):
    """Available product categories."""

    ham_radio_gear_for_sale = "ham-radio-gear-for-sale"


class Catalog(EnumCatalogMixin, BaseCatalog):
    """QRZ RSS feed scraper for ham radio gear for sale."""

    Category = Category

    def __init__(self, playwright_server=None):
        super().__init__(playwright_server)
        self.settings = QRZSettings()
        self.session = requests.Session()
        self._authenticated = False

    def _authenticate(self) -> bool:
        """Authenticate with QRZ login form."""
        if self._authenticated:
            return True

        # Check if credentials are provided
        if not self.settings.username or not self.settings.password:
            self.logger.info("QRZ credentials not provided - authentication skipped")
            return False

        try:
            # First, get the login page to establish a session
            login_page_response = self.session.get("https://www.qrz.com/login")
            login_page_response.raise_for_status()

            # Parse the login page to get the correct form action and fields
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(login_page_response.text, "html.parser")

            # Find the login form
            login_form = soup.find("form")
            if not login_form:
                self.logger.error("Could not find login form")
                return False

            # Get the correct form action
            form_action = login_form.get("action", "/login")
            if form_action.startswith("//"):
                login_url = f"https:{form_action}"
            elif form_action.startswith("/"):
                login_url = f"https://www.qrz.com{form_action}"
            else:
                login_url = form_action

            # Extract all form fields
            form_data = {}
            inputs = login_form.find_all("input")

            for inp in inputs:
                input_name = inp.get("name")
                input_type = inp.get("type", "text")
                input_value = inp.get("value", "")

                if input_name:
                    if input_name == "username":
                        form_data[input_name] = self.settings.username
                    elif input_name == "password":
                        form_data[input_name] = self.settings.password
                    elif input_type.lower() in ["hidden", "checkbox"]:
                        form_data[input_name] = input_value

            # Submit the login form
            login_response = self.session.post(
                login_url, data=form_data, allow_redirects=True
            )
            login_response.raise_for_status()

            # Check if login was successful by looking for error messages
            # QRZ shows specific error messages for failed logins
            response_text_lower = login_response.text.lower()

            # Check for specific QRZ error messages
            error_indicators = [
                "no user found with the argument",
                "we could not log you in",
                "login failed",
                "invalid username",
                "invalid password",
                "incorrect username",
                "incorrect password",
            ]

            login_failed = any(
                error in response_text_lower for error in error_indicators
            )

            if login_failed:
                self.logger.error("Authentication with QRZ failed")
                return False
            else:
                # No error messages found, assume success
                self._authenticated = True
                self.logger.info("Successfully authenticated with QRZ")
                return True

        except Exception as e:
            self.logger.error(f"Error during QRZ authentication: {e}")
            return False

    def _fetch_rss_feed(self, url: str):
        """Fetch and parse RSS feed. Authentication is attempted but not required for this specific feed."""
        # Try to authenticate first, but don't fail if it doesn't work
        # since the RSS feed appears to be publicly accessible
        try:
            self._authenticate()
        except Exception as e:
            self.logger.warning(f"Authentication failed, but continuing anyway: {e}")

        try:
            # Fetch the RSS feed
            response = self.session.get(url)
            response.raise_for_status()

            # Parse the RSS feed content
            feed = feedparser.parse(response.content)

            if hasattr(feed, "bozo") and feed.bozo:
                self.logger.warning(f"RSS feed parsing had issues: {feed.bozo_exception}")

            return feed

        except Exception as e:
            self.logger.error(f"Error fetching RSS feed: {e}")
            raise

    def _extract_products_from_feed(self, feed) -> list[Product]:
        """Extract product information from RSS feed entries."""
        products = []

        for entry in feed.entries:
            try:
                product_data = {}

                # Map RSS entry fields to Product model
                # entry.title becomes Product.title as requested
                if hasattr(entry, "title") and entry.title:
                    title = entry.title.strip()
                    product_data["title"] = title

                    # If available, try to extract summary as description
                    if hasattr(entry, "summary") and entry.summary:
                        product_data["description"] = entry.summary.strip()

                # entry.link becomes Product.url as requested
                if hasattr(entry, "link") and entry.link:
                    product_data["url"] = entry.link.strip()

                # Extract additional information if available
                if hasattr(entry, "published") and entry.published:
                    product_data["date_added"] = entry.published

                # Extract author (callsign) from RSS author field
                # Note: dc:creator contains the same info but feedparser doesn't parse XML namespaces properly
                if hasattr(entry, "author") and entry.author:
                    # QRZ RSS feeds provide the callsign in both author and dc:creator fields
                    author = entry.author.strip()
                    # Validate it looks like a callsign (alphanumeric, typically 3-6 chars)
                    if re.match(r'^[A-Z0-9]{2,6}$', author):
                        product_data["author"] = author

                # Try to extract manufacturer and model from title if possible
                if "title" in product_data:
                    title = product_data["title"]
                    # Basic pattern matching for common formats like "Brand Model - Description"
                    if " - " in title:
                        parts = title.split(" - ", 1)
                        brand_model = parts[0].strip()
                        manufacturer, model = self._extract_manufacturer_model_from_title(brand_model)
                        if manufacturer:
                            product_data["manufacturer"] = manufacturer
                        if model:
                            product_data["model"] = model
                        # Use the part after " - " as additional description if we don't have one
                        if len(parts) > 1 and not product_data.get("description"):
                            product_data["description"] = parts[1].strip()
                    else:
                        # Try to parse simple "Brand Model" format without dash
                        manufacturer, model = self._extract_manufacturer_model_from_title(title)
                        if manufacturer:
                            product_data["manufacturer"] = manufacturer
                        if model:
                            product_data["model"] = model

                # Only create Product if we have the required fields
                if "title" in product_data and "url" in product_data:
                    product = Product(**product_data)
                    products.append(product)

            except Exception as e:
                self.logger.error(f"Error extracting product from RSS entry: {e}")
                continue

        return products


    def get_items(self, category_name: str, max_items: int | None = None) -> list[Product]:
        """Get items from specified category."""
        if category_name == Category.ham_radio_gear_for_sale:
            return self.get_ham_radio_gear_for_sale(max_items)
        else:
            raise ValueError(f"Unknown category: {category_name}")

    def get_ham_radio_gear_for_sale(self, max_items: int | None = None) -> list[Product]:
        """Fetch all ham radio gear for sale from QRZ RSS feed."""
        rss_url = "https://forums.qrz.com/index.php?forums/ham-radio-gear-for-sale.7/index.rss"

        self.logger.info("Fetching QRZ ham radio gear for sale RSS feed...")

        try:
            feed = self._fetch_rss_feed(rss_url)
            products = self._extract_products_from_feed(feed)

            # Apply limit if specified
            if max_items and len(products) > max_items:
                products = products[:max_items]
                self.logger.info(f"Limited to {max_items} items")

            self.logger.info(f"Found {len(products)} products in QRZ RSS feed")
            return products

        except Exception as e:
            self.logger.error(f"Error scraping QRZ RSS feed: {e}")
            return []
