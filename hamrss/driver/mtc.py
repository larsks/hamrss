"""MTC Radio catalog scraper driver."""

import requests
from bs4 import BeautifulSoup
import re
from enum import Enum

from ..model import Product


class Category(str, Enum):
    """Available product categories."""

    used = "used"


class Catalog:
    """MTC Radio catalog scraper for used equipment."""

    def __init__(self, playwright_server=None):
        # Ignore the playwright_server parameter as we use requests instead
        pass

    def _extract_products_from_html(self, html_content: str) -> list[Product]:
        """Extract product information from HTML content."""
        products = []
        soup = BeautifulSoup(html_content, 'html.parser')

        # Get the main product list (not sidebar lists)
        main_product_list = soup.select_one('#CategoryContent .ProductList')
        if not main_product_list:
            return products

        # Get all product list items
        product_items = main_product_list.find_all("li")

        for item in product_items:
            try:
                product_data = {}

                # Extract product URL and title from the main link
                title_link = item.select_one(".ProductDetails strong a")
                if title_link:
                    href = title_link.get("href")
                    # Convert relative URL to fully qualified URL
                    if href and not href.startswith("http"):
                        product_data["url"] = f"https://www.mtcradio.com{href}"
                    else:
                        product_data["url"] = href

                    # Extract title and try to parse manufacturer/model
                    title = title_link.get_text().strip()
                    product_data["description"] = title

                    # Try to parse manufacturer and model from title
                    # Common patterns: "U17582 Used ACOM A1200S..." or "Certified Pre-Loved Flex 6600..."
                    if title:
                        # Remove used item number prefix if present
                        title_cleaned = re.sub(r'^U\d+\s+Used\s+', '', title, flags=re.IGNORECASE)
                        title_cleaned = re.sub(r'^Certified Pre-Loved\s+', '', title_cleaned, flags=re.IGNORECASE)

                        # Split on first space to get potential manufacturer
                        parts = title_cleaned.split()
                        if len(parts) >= 2:
                            product_data["manufacturer"] = parts[0]
                            # Take next 1-2 words as model
                            model_parts = parts[1:3]
                            product_data["model"] = " ".join(model_parts)

                # Extract price
                price_elem = item.select_one(".ProductPriceRating em")
                if price_elem:
                    product_data["price"] = price_elem.get_text().strip()

                # Extract image URL
                img_elem = item.select_one(".ProductImage a img")
                if img_elem:
                    src = img_elem.get("src")
                    # Image URLs are already fully qualified
                    product_data["image_url"] = src

                # Extract product ID from URL or cart action
                cart_link = item.select_one(".ProductActionAdd a")
                if cart_link:
                    cart_href = cart_link.get("href")
                    if cart_href and "product_id=" in cart_href:
                        product_id = cart_href.split("product_id=")[1].split("&")[0]
                        product_data["product_id"] = product_id

                if product_data:  # Only add if we extracted some data
                    product = Product(**product_data)
                    products.append(product)

            except Exception as e:
                print(f"Error extracting product: {e}")
                continue

        return products

    def _get_total_pages(self, html_content: str) -> int:
        """Extract the total number of pages from the pagination."""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            # Look for pagination list
            paging_list = soup.select_one(".CategoryPagination .PagingList")
            if paging_list:
                # Get all page links
                page_links = paging_list.find_all("li")
                max_page = 1

                for li in page_links:
                    link = li.find("a")
                    if link:
                        href = link.get("href")
                        if href and "page=" in href:
                            # Extract page number from URL
                            page_match = re.search(r'page=(\d+)', href)
                            if page_match:
                                page_num = int(page_match.group(1))
                                max_page = max(max_page, page_num)

                return max_page

        except Exception as e:
            print(f"Error getting total pages: {e}")

        return 1

    def _scrape_catalog(self, url: str, catalog_name: str) -> list[Product]:
        """Generic method to scrape MTC catalog with pagination."""
        all_products: list[Product] = []

        try:
            # Fetch the first page to get total page count
            print(f"Fetching {catalog_name}...")
            response = requests.get(url)
            response.raise_for_status()

            # Get total number of pages
            total_pages = self._get_total_pages(response.text)
            print(f"Found {total_pages} pages to scrape")

            # Scrape each page
            for page_num in range(1, total_pages + 1):
                print(f"Scraping page {page_num} of {total_pages}...")

                # Build URL for current page
                if page_num == 1:
                    page_url = url
                    page_content = response.text
                else:
                    page_url = f"{url}?page={page_num}"
                    page_response = requests.get(page_url)
                    page_response.raise_for_status()
                    page_content = page_response.text

                # Extract products from current page
                products = self._extract_products_from_html(page_content)
                all_products.extend(products)
                print(f"Found {len(products)} products on page {page_num}")

            print(f"Scraping completed! Total products found: {len(all_products)}")

        except Exception as e:
            print(f"Error during scraping: {e}")

        return all_products

    def get_categories(self) -> list[str]:
        """Get available categories."""
        return [x.value for x in Category]

    def get_items(self, category: str) -> list[Product]:
        """Get items from specified category."""
        if category == Category.used:
            return self.get_used_items()
        else:
            raise ValueError(f"Unknown category: {category}")

    def get_used_items(self) -> list[Product]:
        """Fetch all used equipment from MTC Radio."""
        return self._scrape_catalog("https://www.mtcradio.com/used-gear/", "MTC Radio used equipment")