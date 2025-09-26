"""MTC Radio catalog scraper driver."""

from playwright.sync_api import Page, Browser
import re
import time
from enum import Enum

from ..model import Product


class Category(str, Enum):
    """Available product categories."""

    used = "used"


class Catalog:
    """MTC Radio catalog scraper for used equipment."""

    def __init__(self, browser: Browser):
        self.browser = browser

    def _extract_products_from_page(self, page: Page) -> list[Product]:
        """Extract product information from the current page."""
        products = []

        # Wait for products to load
        page.wait_for_load_state("networkidle")
        time.sleep(2)  # Give extra time for dynamic content

        # Get the main product list (not sidebar lists)
        main_product_list = page.query_selector('#CategoryContent .ProductList')
        if not main_product_list:
            return products

        # Get all product list items
        product_items = main_product_list.query_selector_all("li")

        for item in product_items:
            try:
                product_data = {}

                # Extract product URL and title from the main link
                title_link = item.query_selector(".ProductDetails strong a")
                if title_link:
                    href = title_link.get_attribute("href")
                    # Convert relative URL to fully qualified URL
                    if href and not href.startswith("http"):
                        product_data["url"] = f"https://www.mtcradio.com{href}"
                    else:
                        product_data["url"] = href

                    # Extract title and try to parse manufacturer/model
                    title = title_link.inner_text().strip()
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
                price_elem = item.query_selector(".ProductPriceRating em")
                if price_elem:
                    product_data["price"] = price_elem.inner_text().strip()

                # Extract image URL
                img_elem = item.query_selector(".ProductImage a img")
                if img_elem:
                    src = img_elem.get_attribute("src")
                    # Image URLs are already fully qualified
                    product_data["image_url"] = src

                # Extract product ID from URL or cart action
                cart_link = item.query_selector(".ProductActionAdd a")
                if cart_link:
                    cart_href = cart_link.get_attribute("href")
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

    def _get_total_pages(self, page: Page) -> int:
        """Extract the total number of pages from the pagination."""
        try:
            # Look for pagination list
            paging_list = page.query_selector(".CategoryPagination .PagingList")
            if paging_list:
                # Get all page links
                page_links = paging_list.query_selector_all("li a")
                max_page = 1

                for link in page_links:
                    href = link.get_attribute("href")
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
        page = self.browser.new_page()

        try:
            # Navigate to the catalog page
            print(f"Navigating to {catalog_name}...")
            page.goto(url)

            # Wait for the page to load
            page.wait_for_load_state("networkidle")

            # Get total number of pages
            total_pages = self._get_total_pages(page)
            print(f"Found {total_pages} pages to scrape")

            # Scrape each page
            for page_num in range(1, total_pages + 1):
                print(f"Scraping page {page_num} of {total_pages}...")

                # Extract products from current page
                products = self._extract_products_from_page(page)
                all_products.extend(products)
                print(f"Found {len(products)} products on page {page_num}")

                # Navigate to next page if not the last page
                if page_num < total_pages:
                    try:
                        # Build URL for next page
                        next_page_url = f"{url}?page={page_num + 1}"
                        page.goto(next_page_url)

                        # Wait for the page to update
                        page.wait_for_load_state("networkidle")
                        time.sleep(1)

                    except Exception as e:
                        print(f"Error navigating to page {page_num + 1}: {e}")
                        break

            print(f"Scraping completed! Total products found: {len(all_products)}")

        except Exception as e:
            print(f"Error during scraping: {e}")

        finally:
            page.close()

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