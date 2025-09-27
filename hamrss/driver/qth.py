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
        """Extract product information from HTML content."""
        products = []
        soup = BeautifulSoup(html_content, "html.parser")

        # Find the definition list containing all listings - try both cases
        dl_element = soup.find("dl") or soup.find("DL")
        if not dl_element:
            return products

        # Get all DT and DD elements
        all_dt = dl_element.find_all("dt") + dl_element.find_all("DT")
        all_dd = dl_element.find_all("dd") + dl_element.find_all("DD")

        # Group DD elements with their corresponding DT
        # Since BeautifulSoup might nest everything, we need a different approach
        dt_index = 0

        for dt in all_dt:
            try:
                product_data = {}

                # Extract title from DT element - look for bold text
                title_element = dt.find("b") or dt.find("B")
                if title_element:
                    title = title_element.get_text().strip()
                    product_data["description"] = title

                    # Try to extract manufacturer and model from title
                    title_parts = title.split()
                    if len(title_parts) >= 2:
                        # First word is often the manufacturer
                        potential_manufacturer = title_parts[0]
                        if potential_manufacturer[0].isupper():
                            product_data["manufacturer"] = potential_manufacturer
                            # Next 1-2 words could be the model
                            if len(title_parts) >= 2:
                                model_parts = title_parts[1:3]
                                product_data["model"] = " ".join(model_parts)

                # Look for photo/detail link in DT
                detail_link = dt.find("a", href=re.compile(r"view_ad\.php"))
                if detail_link:
                    href = detail_link.get("href")
                    product_data["url"] = urljoin(self.base_url, href)

                # Find DD elements that belong to this DT
                # Since the structure might be nested, look for DD elements within this DT
                related_dd = dt.find_all("dd") + dt.find_all("DD")

                # If no DD found within DT, try to find by position
                if not related_dd and dt_index < len(all_dt):
                    # Estimate which DD elements belong to this DT
                    # Usually there are 3 DD elements per DT (description, metadata, actions)
                    start_idx = dt_index * 3
                    end_idx = min(start_idx + 3, len(all_dd))
                    related_dd = all_dd[start_idx:end_idx]

                # Process DD elements for this listing
                all_dd_text = ""
                for dd in related_dd:
                    dd_text = dd.get_text().strip()
                    all_dd_text += " " + dd_text

                    # Look for contact link to extract listing number
                    contact_link = dd.find("a", href=re.compile(r"contact\.php"))
                    if contact_link:
                        href = contact_link.get("href")
                        counter_match = re.search(r"counter=(\d+)", href)
                        if counter_match:
                            product_data["product_id"] = counter_match.group(1)

                # Parse the combined DD content for details
                if all_dd_text:
                    # Look for price patterns
                    price_pattern = r"\$[\d,]+(?:\.\d{2})?(?:\s+(?:Shipped|OBO|Firm))?|Free|SOLD"
                    price_match = re.search(price_pattern, all_dd_text, re.IGNORECASE)
                    if price_match:
                        product_data["price"] = price_match.group().strip()

                    # Look for submission date
                    date_pattern = r"Submitted on (\d{2}/\d{2}/\d{2})"
                    date_match = re.search(date_pattern, all_dd_text)
                    if date_match:
                        product_data["date_added"] = date_match.group(1)

                    # Look for callsign
                    callsign_pattern = r"by Callsign ([A-Z0-9]+)"
                    callsign_match = re.search(callsign_pattern, all_dd_text)
                    if callsign_match:
                        # Store callsign in location field for now
                        product_data["location"] = f"Seller: {callsign_match.group(1)}"

                # Set default URL if none found
                if "url" not in product_data:
                    product_data["url"] = f"{self.base_url}/index.php"

                # Only add if we have meaningful data
                if product_data.get("description"):
                    product = Product(**product_data)
                    products.append(product)

                dt_index += 1

            except Exception as e:
                print(f"Error extracting product: {e}")
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
