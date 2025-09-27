"""Swap QTH catalog scraper driver."""

import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin, urlparse, parse_qs

from ..model import Product


class Catalog:
    """Swap QTH catalog scraper for ham radio equipment classified ads."""

    def __init__(self, playwright_server=None, max_products=100):
        """Initialize the catalog with optional product limit."""
        # Ignore the playwright_server parameter as we use requests instead
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
            print(f"Error discovering categories: {e}")
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
                title_parts = title.split()
                if len(title_parts) >= 2:
                    # Skip generic prefixes
                    start_idx = 0
                    if title_parts[0].upper() in ['FOR', 'FS:', 'SALE', 'NEW', 'USED']:
                        start_idx = 1

                    if start_idx < len(title_parts):
                        # First meaningful word is often the manufacturer
                        potential_manufacturer = title_parts[start_idx]
                        if potential_manufacturer[0].isupper() and not potential_manufacturer.startswith("-"):
                            product_data["manufacturer"] = potential_manufacturer
                            # Next 1-2 words could be the model
                            if start_idx + 1 < len(title_parts):
                                model_parts = title_parts[start_idx + 1:start_idx + 3]
                                product_data["model"] = " ".join(model_parts)

                # Find the containing structure to get associated links and content
                container = bold_element.find_parent(['dt', 'dd', 'DT', 'DD'])
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
                    current = current.find_next_sibling(['dd', 'DD'])
                    if current:
                        text = current.get_text().strip()
                        # Skip if this looks like metadata or action links
                        if not text.startswith(("Listing #", "Click to")) and len(text) > 10:
                            description_dd = current
                            break
                    else:
                        break

                # Extract description and other details from the description DD
                if description_dd:
                    desc_text = description_dd.get_text().strip()

                    # Look for price patterns first
                    price_pattern = r"\$[\d,]+(?:\.\d{2})?(?:\s+(?:shipped|OBO|Firm|plus))?|Free|SOLD"
                    price_match = re.search(price_pattern, desc_text, re.IGNORECASE)
                    if price_match:
                        product_data["price"] = price_match.group().strip()

                    # Clean description by removing price and payment info
                    desc_clean = re.sub(price_pattern, "", desc_text, flags=re.IGNORECASE)
                    desc_clean = re.sub(r'\b(paypal|check|money order|payment)\b', "", desc_clean, flags=re.IGNORECASE)
                    desc_clean = re.sub(r'\s+', ' ', desc_clean).strip()

                    # Take first sentence or up to 200 chars as description
                    if desc_clean:
                        # Split on periods and take first substantial sentence
                        sentences = desc_clean.split('.')
                        if sentences and len(sentences[0]) > 20:
                            product_data["description"] = sentences[0].strip()
                        elif len(desc_clean) <= 200:
                            product_data["description"] = desc_clean
                        else:
                            product_data["description"] = desc_clean[:200] + "..."

                # Look for metadata in subsequent DD elements
                metadata_dd = None
                if description_dd:
                    metadata_dd = description_dd.find_next_sibling(['dd', 'DD'])

                if metadata_dd:
                    metadata_text = metadata_dd.get_text()

                    # Look for submission date
                    date_pattern = r"Submitted on (\d{2}/\d{2}/\d{2})"
                    date_match = re.search(date_pattern, metadata_text)
                    if date_match:
                        product_data["date_added"] = date_match.group(1)

                    # Look for callsign
                    callsign_pattern = r"by Callsign ([A-Z0-9]+)"
                    callsign_match = re.search(callsign_pattern, metadata_text)
                    if callsign_match:
                        callsign = callsign_match.group(1)
                        product_data["location"] = f"Seller: {callsign}"

                # Set default URL if none found
                if "url" not in product_data:
                    product_data["url"] = f"{self.base_url}/"

                # Only add if we have a title (required field)
                if product_data.get("title"):
                    product = Product(**product_data)
                    products.append(product)

            except Exception as e:
                print(f"Error extracting product '{title}': {e}")
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
            print(f"Error finding next page: {e}")

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

    def _scrape_category(self, url: str, category_name: str) -> list[Product]:
        """Scrape a category page with pagination support and product limits."""
        all_products = []
        current_url = url
        page_count = 0

        try:
            while current_url:
                page_count += 1
                print(f"Scraping {category_name} page {page_count}...")

                response = requests.get(current_url)
                response.raise_for_status()

                # Extract products from current page
                products = self._extract_products_from_html(response.text)
                print(f"Found {len(products)} products on page {page_count}")

                # Add products, respecting the limit
                for product in products:
                    if self.max_products > 0 and len(all_products) >= self.max_products:
                        print(f"Reached product limit of {self.max_products}")
                        return all_products
                    all_products.append(product)

                # Check if we should continue to next page
                if self.max_products > 0 and len(all_products) >= self.max_products:
                    break

                # Find next page URL
                next_url = self._get_next_page_url(response.text, current_url)
                if next_url and next_url != current_url:
                    current_url = next_url
                else:
                    break

                # Safety check to prevent infinite loops
                if page_count > 100:
                    print("Warning: Stopped after 100 pages to prevent infinite loop")
                    break

        except Exception as e:
            print(f"Error scraping category {category_name}: {e}")

        print(
            f"Scraping {category_name} completed! Total products found: {len(all_products)}"
        )
        return all_products

    def get_items(self, category_name: str) -> list[Product]:
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
        return self._scrape_category(category_url, category_name)
