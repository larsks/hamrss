"""QRZ RSS feed driver for ham radio gear for sale."""

import requests
import feedparser
from enum import Enum
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ..model import Product


class QRZSettings(BaseSettings):
    """QRZ driver configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="HAMRSS_QRZ_",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    username: str = Field(default="", description="QRZ username for authentication")
    password: str = Field(default="", description="QRZ password for authentication")


class Category(str, Enum):
    """Available product categories."""

    ham_radio_gear_for_sale = "ham-radio-gear-for-sale"


class Catalog:
    """QRZ RSS feed scraper for ham radio gear for sale."""

    def __init__(self, playwright_server=None):
        # Ignore the playwright_server parameter as we use requests instead
        self.settings = QRZSettings()
        self.session = requests.Session()
        self._authenticated = False

    def _authenticate(self) -> bool:
        """Authenticate with QRZ login form."""
        if self._authenticated:
            return True

        # Check if credentials are provided
        if not self.settings.username or not self.settings.password:
            print("QRZ credentials not provided - authentication skipped")
            return False

        try:
            # First, get the login page to establish a session
            login_page_response = self.session.get("https://www.qrz.com/login")
            login_page_response.raise_for_status()

            # Parse the login page to get the correct form action and fields
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(login_page_response.text, 'html.parser')

            # Find the login form
            login_form = soup.find('form')
            if not login_form:
                print("Could not find login form")
                return False

            # Get the correct form action
            form_action = login_form.get('action', '/login')
            if form_action.startswith('//'):
                login_url = f"https:{form_action}"
            elif form_action.startswith('/'):
                login_url = f"https://www.qrz.com{form_action}"
            else:
                login_url = form_action

            # Extract all form fields
            form_data = {}
            inputs = login_form.find_all('input')

            for inp in inputs:
                input_name = inp.get('name')
                input_type = inp.get('type', 'text')
                input_value = inp.get('value', '')

                if input_name:
                    if input_name == 'username':
                        form_data[input_name] = self.settings.username
                    elif input_name == 'password':
                        form_data[input_name] = self.settings.password
                    elif input_type.lower() in ['hidden', 'checkbox']:
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
                "incorrect password"
            ]

            login_failed = any(error in response_text_lower for error in error_indicators)

            if login_failed:
                print("Authentication with QRZ failed")
                return False
            else:
                # No error messages found, assume success
                self._authenticated = True
                print("Successfully authenticated with QRZ")
                return True

        except Exception as e:
            print(f"Error during QRZ authentication: {e}")
            return False

    def _fetch_rss_feed(self, url: str):
        """Fetch and parse RSS feed. Authentication is attempted but not required for this specific feed."""
        # Try to authenticate first, but don't fail if it doesn't work
        # since the RSS feed appears to be publicly accessible
        try:
            self._authenticate()
        except Exception as e:
            print(f"Authentication failed, but continuing anyway: {e}")

        try:
            # Fetch the RSS feed
            response = self.session.get(url)
            response.raise_for_status()

            # Parse the RSS feed content
            feed = feedparser.parse(response.content)

            if hasattr(feed, "bozo") and feed.bozo:
                print(f"Warning: RSS feed parsing had issues: {feed.bozo_exception}")

            return feed

        except Exception as e:
            print(f"Error fetching RSS feed: {e}")
            raise

    def _extract_products_from_feed(self, feed) -> list[Product]:
        """Extract product information from RSS feed entries."""
        products = []

        for entry in feed.entries:
            try:
                product_data = {}

                # Map RSS entry fields to Product model
                # entry.title becomes Product.description as requested
                if hasattr(entry, "title") and entry.title:
                    product_data["description"] = entry.title.strip()

                # entry.link becomes Product.url as requested
                if hasattr(entry, "link") and entry.link:
                    product_data["url"] = entry.link.strip()

                # Extract additional information if available
                if hasattr(entry, "published") and entry.published:
                    product_data["date_added"] = entry.published

                # Try to extract manufacturer and model from title if possible
                if "description" in product_data:
                    title = product_data["description"]
                    # Basic pattern matching for common formats like "Brand Model - Description"
                    if " - " in title:
                        parts = title.split(" - ", 1)
                        brand_model = parts[0].strip()
                        brand_parts = brand_model.split()
                        if len(brand_parts) >= 2:
                            product_data["manufacturer"] = brand_parts[0]
                            product_data["model"] = " ".join(brand_parts[1:])
                    else:
                        # Try to parse simple "Brand Model" format without dash
                        title_parts = title.split()
                        if len(title_parts) >= 2:
                            product_data["manufacturer"] = title_parts[0]
                            product_data["model"] = " ".join(title_parts[1:])

                # Only create Product if we have the required fields
                if "description" in product_data and "url" in product_data:
                    product = Product(**product_data)
                    products.append(product)

            except Exception as e:
                print(f"Error extracting product from RSS entry: {e}")
                continue

        return products

    def get_categories(self) -> list[str]:
        """Get available categories."""
        return [x.value for x in Category]

    def get_items(self, category_name: str) -> list[Product]:
        """Get items from specified category."""
        if category_name == Category.ham_radio_gear_for_sale:
            return self.get_ham_radio_gear_for_sale()
        else:
            raise ValueError(f"Unknown category: {category_name}")

    def get_ham_radio_gear_for_sale(self) -> list[Product]:
        """Fetch all ham radio gear for sale from QRZ RSS feed."""
        rss_url = "https://forums.qrz.com/index.php?forums/ham-radio-gear-for-sale.7/index.rss"

        print("Fetching QRZ ham radio gear for sale RSS feed...")

        try:
            feed = self._fetch_rss_feed(rss_url)
            products = self._extract_products_from_feed(feed)

            print(f"Found {len(products)} products in QRZ RSS feed")
            return products

        except Exception as e:
            print(f"Error scraping QRZ RSS feed: {e}")
            return []
