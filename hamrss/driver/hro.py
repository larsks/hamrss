"""Ham Radio Outlet catalog scraper driver."""

from playwright.sync_api import Page
import re
import time
from enum import Enum

from .base import BaseCatalog, EnumCatalogMixin
from ..model import Product


class Category(str, Enum):
    """Available product categories."""

    used = "used"
    open = "open"
    consignment = "consignment"


class Catalog(EnumCatalogMixin, BaseCatalog):
    """Ham Radio Outlet catalog scraper for used, open item, and consignment products."""

    Category = Category

    def __init__(self, playwright_server):
        super().__init__(playwright_server)
        self.base_url = "https://www.hamradio.com"

    def _extract_products_from_page(self, page: Page) -> list[Product]:
        """Extract product information from the current page."""
        products = []

        # Wait for products to load
        page.wait_for_selector(".hero-feature", timeout=10000)

        # Get all product containers
        product_containers = page.query_selector_all(".hero-feature")

        for container in product_containers:
            try:
                product_data = {}

                # Extract manufacturer and model from the h4 elements
                manufacturer = None
                model = None
                h4_elements = container.query_selector_all(".prod-caption h4")
                if len(h4_elements) >= 2:
                    manufacturer_elem = h4_elements[0].query_selector("strong")
                    if manufacturer_elem:
                        manufacturer = manufacturer_elem.inner_text().strip()
                        product_data["manufacturer"] = manufacturer

                    model_elem = h4_elements[1]
                    if model_elem:
                        model = model_elem.inner_text().strip()
                        product_data["model"] = model

                # Create title from manufacturer and model
                title_parts = []
                if manufacturer:
                    title_parts.append(manufacturer)
                if model:
                    title_parts.append(model)
                if title_parts:
                    product_data["title"] = " ".join(title_parts)
                else:
                    # Fallback if no manufacturer/model found
                    product_data["title"] = "Ham Radio Equipment"

                # Extract product URL from the first link
                link_elem = container.query_selector(".prod-caption a")
                if link_elem:
                    href = link_elem.get_attribute("href")
                    # Convert relative URL to fully qualified URL
                    product_data["url"] = self._normalize_url(href, self.base_url)

                    # Extract product ID from URL
                    if href and "pid=" in href:
                        product_data["product_id"] = href.split("pid=")[1]

                # Extract description from h6 element
                desc_elem = container.query_selector(".prod-caption h6")
                if desc_elem:
                    product_data["description"] = desc_elem.inner_text().strip()

                # Extract location
                location_elem = container.query_selector(
                    '.prod-caption h6 a[href*="locations.cfm"]'
                )
                if location_elem:
                    location_text = location_elem.inner_text().strip()
                    if "Located:" in location_text:
                        product_data["location"] = location_text.replace(
                            "Located:", ""
                        ).strip()

                # Extract date added
                p_elements = container.query_selector_all(".prod-caption p")
                for p in p_elements:
                    text = p.inner_text().strip()
                    if "Added:" in text:
                        product_data["date_added"] = text.replace("Added:", "").strip()

                # Extract price from the button with price (try multiple selectors for different page types)
                price_elem = container.query_selector(
                    '.btn-primary[style*="background-color:#FFF"]'
                )
                if not price_elem:
                    # Try open items page format (orange background)
                    price_elem = container.query_selector(
                        '.btn-primary[style*="background-color:#FF9900"]'
                    )
                if not price_elem:
                    # Try other possible price button formats
                    price_elem = container.query_selector(
                        ".btn-group .btn-primary:first-child"
                    )
                if price_elem:
                    price_text = price_elem.inner_text().strip()
                    price = self._extract_price(price_text)
                    if price:
                        product_data["price"] = price

                # Extract image URL
                img_elem = container.query_selector("img")
                if img_elem:
                    src = img_elem.get_attribute("src")
                    # Convert relative image URL to fully qualified URL
                    product_data["image_url"] = self._normalize_url(src, self.base_url)

                if product_data.get(
                    "title"
                ):  # Only add if we have a title (required field)
                    product = Product(**product_data)
                    products.append(product)

            except Exception as e:
                self.logger.error(f"Error extracting product: {e}")
                continue

        return products

    def _get_total_pages(self, page: Page) -> int:
        """Extract total page count from HRO page."""
        try:
            # Look for text like "of 6" after the select element
            page_info = page.query_selector('select[name="jumpPage"] + span')
            if page_info:
                text = page_info.inner_text().strip()
                # Extract number from text like " of 6"
                match = re.search(r"of (\d+)", text)
                if match:
                    return int(match.group(1))
        except Exception as e:
            self.logger.error(f"Error getting total pages: {e}")

        return 1

    def _scrape_catalog(self, url: str, catalog_name: str, max_items: int | None = None) -> list[Product]:
        """Generic method to scrape any HRO catalog with pagination."""
        all_products: list[Product] = []

        with self.playwright_server.get_browser() as browser:
            page = browser.new_page()
            try:
                # Navigate to the catalog page
                self.logger.info(f"Navigating to {catalog_name}...")
                page.goto(url)

                # Wait for the page to load
                page.wait_for_selector('select[name="jumpPage"]', timeout=10000)

                # Get total number of pages
                total_pages = self._get_total_pages(page)
                self.logger.info(f"Found {total_pages} pages to scrape")

                # Scrape each page
                for page_num in range(total_pages):
                    self.logger.info(f"Scraping page {page_num + 1} of {total_pages}...")

                    # Extract products from current page
                    products = self._extract_products_from_page(page)
                    all_products.extend(products)
                    self.logger.info(f"Found {len(products)} products on page {page_num + 1}")

                    # Check if we've reached the limit
                    if max_items and len(all_products) >= max_items:
                        all_products = all_products[:max_items]
                        self.logger.info(f"Reached limit of {max_items} items, stopping early")
                        break

                    # Navigate to next page if not the last page
                    if page_num < total_pages - 1:
                        try:
                            # Find the select element and get the next page value
                            select_elem = page.query_selector('select[name="jumpPage"]')
                            options = select_elem.query_selector_all("option")

                            # Get the value for the next page
                            next_page_value = options[page_num + 1].get_attribute(
                                "value"
                            )

                            # Select the next page
                            page.select_option(
                                'select[name="jumpPage"]', next_page_value
                            )

                            # Wait for the page to update
                            time.sleep(2)
                            page.wait_for_selector(".hero-feature", timeout=10000)

                        except Exception as e:
                            self.logger.error(f"Error navigating to page {page_num + 2}: {e}")
                            break

                self.logger.info(f"Scraping completed! Total products found: {len(all_products)}")

            except Exception as e:
                self.logger.error(f"Error during scraping: {e}")

            finally:
                page.close()

        return all_products

    def get_used_items(self, max_items: int | None = None) -> list[Product]:
        """Fetch all used equipment from /used.cfm"""
        return self._scrape_catalog(
            "https://www.hamradio.com/used.cfm", "Ham Radio used equipment", max_items
        )

    def get_open_items(self, max_items: int | None = None) -> list[Product]:
        """Fetch all open items from /open_item.cfm"""
        return self._scrape_catalog(
            "https://www.hamradio.com/open_item.cfm", "Ham Radio open items", max_items
        )

    def get_consignment_items(self, max_items: int | None = None) -> list[Product]:
        """Fetch all consignment items from /consignment.cfm"""
        return self._scrape_catalog(
            "https://www.hamradio.com/consignment.cfm", "Ham Radio consignment items", max_items
        )


    def get_items(self, category_name: str, max_items: int | None = None) -> list[Product]:
        if category_name == Category.used:
            return self.get_used_items(max_items)
        elif category_name == Category.open:
            return self.get_open_items(max_items)
        elif category_name == Category.consignment:
            return self.get_consignment_items(max_items)
        else:
            raise ValueError(category_name)
