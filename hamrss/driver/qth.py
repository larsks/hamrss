"""Swap QTH catalog scraper driver."""

import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin, urlparse, parse_qs

from .base import BaseCatalog
from ..model import Product


class Catalog(BaseCatalog):
    """Swap QTH catalog scraper for ham radio equipment classified ads."""

    def __init__(self, playwright_server=None, max_products=100):
        """Initialize the catalog with optional product limit."""
        super().__init__(playwright_server)
        self.max_products = max_products
        self._categories_cache = None
        self.base_url = "https://swap.qth.com"

    def _discover_categories(self) -> dict[str, str]:
        """Discover available categories from the main page."""
        try:
            response = requests.get(f"{self.base_url}/index.php")
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            # Find the "VIEW BY CATEGORY" section
            categories = {}

            # Look for links in the category section
            # The categories are typically in a table or list format
            category_links = soup.find_all("a", href=re.compile(r"c_\w+\.php"))

            for link in category_links:
                href = link.get("href")
                if href and href.startswith("c_") and href.endswith(".php"):
                    # Extract category name from link text
                    category_name = link.get_text().strip()
                    if category_name:
                        # Convert relative URL to absolute
                        category_url = urljoin(self.base_url, href)
                        categories[category_name] = category_url

            return categories

        except Exception as e:
            self.logger.error(f"Error discovering categories: {e}")
            return {}

    def get_categories(self) -> list[str]:
        """Get available categories, using cached result if available."""
        if self._categories_cache is None:
            discovered = self._discover_categories()
            self._categories_cache = discovered

        return list(self._categories_cache.keys())

    def _extract_products_from_html(self, html_content: str) -> list[Product]:
        """Extract product information from HTML content.

        The HTML structure is malformed - all products are nested within a single
        large DT element. We need to find all bold elements (titles) and extract
        their associated content.
        """
        products = []
        soup = BeautifulSoup(html_content, "html.parser")

        # Find the main DL element
        dl_element = soup.find("dl") or soup.find("DL")
        if not dl_element:
            return products

        # The HTML structure is malformed - all products are in nested bold elements
        # Find all bold elements which contain the titles
        bold_elements = dl_element.find_all("b") + dl_element.find_all("B")

        for bold_element in bold_elements:
            try:
                product_data = {}

                # Extract title from bold element
                title = bold_element.get_text().strip()
                if not title:
                    continue

                product_data["title"] = title

                # Try to extract manufacturer and model from title
                manufacturer, model = self._extract_manufacturer_model_from_title(title)
                if manufacturer:
                    product_data["manufacturer"] = manufacturer
                if model:
                    product_data["model"] = model

                # Find the containing structure to get associated links and content
                container = bold_element.find_parent(["dt", "dd", "DT", "DD"])
                if not container:
                    container = bold_element.find_parent()

                # Look for photo/detail link near the bold element
                detail_link = None
                current = bold_element
                for _ in range(3):  # Search nearby elements
                    if current:
                        link = current.find_next("a", href=re.compile(r"view_ad\.php"))
                        if link:
                            detail_link = link
                            break
                        current = current.find_next_sibling()
                    else:
                        break

                if detail_link:
                    href = detail_link.get("href")
                    product_data["url"] = urljoin(self.base_url, href)

                    # Extract product ID from URL
                    counter_match = re.search(r"counter=(\d+)", href)
                    if counter_match:
                        product_data["product_id"] = counter_match.group(1)

                # Find the content that follows this title
                # Look for the next DD element after this bold element
                description_dd = None
                current = bold_element

                # Navigate through the DOM to find the description DD
                for _ in range(5):
                    current = current.find_next_sibling(["dd", "DD"])
                    if current:
                        text = current.get_text().strip()
                        # Skip if this looks like metadata or action links
                        if (
                            not text.startswith(("Listing #", "Click to"))
                            and len(text) > 10
                        ):
                            description_dd = current
                            break
                    else:
                        break

                # Extract description and other details from the description DD
                if description_dd:
                    # Use separator to ensure spacing between HTML elements
                    desc_text = description_dd.get_text(separator=' ').strip()

                    # Take full description text - QTH listings are freeform text
                    if desc_text:
                        # The DD element may contain multiple listings concatenated
                        # Extract only the description for this specific item by looking for boundaries

                        # Split on "Listing #" to separate individual items
                        if "Listing #" in desc_text:
                            # Find the first "Listing #" which marks the end of our item's description
                            listing_index = desc_text.find("Listing #")
                            if listing_index > 0:
                                desc_text = desc_text[:listing_index].strip()

                        # Normalize whitespace but preserve full content
                        desc_clean = re.sub(r'\s+', ' ', desc_text).strip()

                        # Use a reasonable limit for QTH descriptions (800 chars)
                        if len(desc_clean) <= 800:
                            product_data["description"] = desc_clean
                        else:
                            product_data["description"] = desc_clean[:800] + "..."

                # Look for metadata in DD elements that contain listing information
                # The metadata appears in a DD element with italic text like:
                # <DD><i><font size=2 face=arial>Listing #1744126 - Submitted on 09/24/25 by Callsign <a href="...">W6TTM</a>, Modified on 09/28/25 - IP: ...</i></font>

                # Search through all DD elements after the title for metadata
                current = bold_element
                for _ in range(10):  # Search through multiple DD elements
                    current = current.find_next_sibling(["dd", "DD"])
                    if current:
                        dd_text = current.get_text(separator=' ', strip=True)

                        # Check if this DD contains listing metadata
                        if "Listing #" in dd_text and "Submitted on" in dd_text:
                            # Look for submission date
                            date_pattern = r"Submitted on (\d{2}/\d{2}/\d{2})"
                            date_match = re.search(date_pattern, dd_text)
                            if date_match:
                                product_data["date_added"] = date_match.group(1)

                            # Look for callsign - handle both plain text and link formats
                            # Pattern handles: "by Callsign W6TTM" or "by Callsign <a href="...">W6TTM</a>"
                            callsign_pattern = r"by Callsign[^\w]*([A-Z0-9]+)"
                            callsign_match = re.search(callsign_pattern, dd_text)
                            if callsign_match:
                                callsign = callsign_match.group(1)
                                product_data["author"] = callsign

                            # Found metadata, break out of loop
                            break
                    else:
                        break

                # Set default URL if none found
                if "url" not in product_data:
                    product_data["url"] = f"{self.base_url}/"

                # Only add if we have a title (required field)
                if product_data.get("title"):
                    product = Product(**product_data)
                    products.append(product)

            except Exception as e:
                self.logger.error(f"Error extracting product '{title}': {e}")
                continue

        return products

    def _get_next_page_url(self, html_content: str, current_url: str) -> str | None:
        """Extract the next page URL from pagination links."""
        try:
            soup = BeautifulSoup(html_content, "html.parser")

            # Look for "Next" links
            next_links = soup.find_all("a", string=re.compile(r"Next|next|\>|»"))

            for link in next_links:
                href = link.get("href")
                if href:
                    return urljoin(self.base_url, href)

            # Alternative: look for numbered pagination
            page_links = soup.find_all("a", href=re.compile(r"page=|start="))
            if page_links:
                # Find the highest page number that's greater than current
                current_page = self._extract_page_number(current_url)
                best_next_url = None
                best_page_num = current_page

                for link in page_links:
                    href = link.get("href")
                    if href:
                        page_num = self._extract_page_number(href)
                        if page_num > current_page and (
                            best_next_url is None or page_num < best_page_num
                        ):
                            best_next_url = urljoin(self.base_url, href)
                            best_page_num = page_num

                return best_next_url

        except Exception as e:
            self.logger.error(f"Error finding next page: {e}")

        return None

    def _extract_page_number(self, url: str) -> int:
        """Extract page number from URL."""
        try:
            parsed = urlparse(url)
            query_params = parse_qs(parsed.query)

            # Check common pagination parameters
            for param in ["page", "start", "offset"]:
                if param in query_params:
                    return int(query_params[param][0])

            return 1
        except (ValueError, KeyError, IndexError):
            return 1

    def _scrape_category(self, url: str, category_name: str, max_items: int | None = None) -> list[Product]:
        """Scrape a category page with pagination support and product limits."""
        all_products = []
        current_url = url
        page_count = 0

        # Use parameter limit if provided, otherwise fall back to instance limit
        limit = max_items if max_items is not None else (self.max_products if self.max_products > 0 else None)

        try:
            while current_url:
                page_count += 1
                self.logger.info(f"Scraping {category_name} page {page_count}...")

                response = requests.get(current_url)
                response.raise_for_status()

                # Extract products from current page
                products = self._extract_products_from_html(response.text)
                self.logger.info(f"Found {len(products)} products on page {page_count}")

                # Add products, respecting the limit
                for product in products:
                    if limit and len(all_products) >= limit:
                        self.logger.info(f"Reached product limit of {limit}")
                        return all_products
                    all_products.append(product)

                # Check if we should continue to next page
                if limit and len(all_products) >= limit:
                    break

                # Find next page URL
                next_url = self._get_next_page_url(response.text, current_url)
                if next_url and next_url != current_url:
                    current_url = next_url
                else:
                    break

                # Safety check to prevent infinite loops
                if page_count > 100:
                    self.logger.warning("Stopped after 100 pages to prevent infinite loop")
                    break

        except Exception as e:
            self.logger.error(f"Error scraping category {category_name}: {e}")

        self.logger.info(
            f"Scraping {category_name} completed! Total products found: {len(all_products)}"
        )
        return all_products

    def get_items(self, category_name: str, max_items: int | None = None) -> list[Product]:
        """Get items from specified category."""
        # Ensure categories are discovered
        if self._categories_cache is None:
            self.get_categories()

        if category_name not in self._categories_cache:
            available_categories = list(self._categories_cache.keys())
            raise ValueError(
                f"Unknown category: {category_name}. Available categories: {available_categories}"
            )

        category_url = self._categories_cache[category_name]
        return self._scrape_category(category_url, category_name, max_items)
