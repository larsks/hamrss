"""R&L Electronics (randl) catalog scraper driver."""

import requests
from bs4 import BeautifulSoup
import re
from enum import Enum

from .base import BaseCatalog, EnumCatalogMixin
from ..model import Product


class Category(str, Enum):
    """Available product categories."""

    used = "used"


class Catalog(EnumCatalogMixin, BaseCatalog):
    """R&L Electronics catalog scraper for used equipment."""

    Category = Category

    def __init__(self, playwright_server=None):
        super().__init__(playwright_server)
        self.base_url = "https://www2.randl.com"

    def _extract_products_from_html(self, html_content: str) -> list[Product]:
        """Extract product information from the HTML content."""
        products = []
        soup = BeautifulSoup(html_content, "html.parser")

        # Find the main table with products
        table = soup.find("table", {"border": "1", "bordercolor": "#000000"})
        if not table:
            return products

        # Get all rows from table (no tbody element)
        rows = table.find_all("tr")

        for row in rows:
            try:
                cells = row.find_all("td")
                if len(cells) < 3:
                    continue

                product_data = {}

                # Extract manufacturer from first cell
                manufacturer_cell = cells[0]
                manufacturer = manufacturer_cell.get_text().strip()
                if manufacturer:
                    product_data["manufacturer"] = manufacturer

                # Extract description and URL from second cell
                desc_cell = cells[1]

                # Extract URL from the link
                link_elem = desc_cell.find("a")
                if link_elem:
                    href = link_elem.get("href")
                    product_data["url"] = self._normalize_url(href, self.base_url)

                    # Extract product ID from URL
                    if href and "products_id=" in href:
                        product_id = href.split("products_id=")[1].split("&")[0]
                        product_data["product_id"] = product_id

                # Extract full description text
                desc_text = desc_cell.get_text().strip()
                model = None
                if desc_text:
                    # Try to parse model from description
                    # Look for text after "Used " prefix
                    desc_cleaned = re.sub(
                        r"^Used\s+", "", desc_text, flags=re.IGNORECASE
                    )
                    if desc_cleaned:
                        # Extract manufacturer and model using base class method
                        manufacturer_from_desc, model = self._extract_manufacturer_model_from_title(desc_cleaned)
                        if model:
                            product_data["model"] = model

                    # Set description to full text (may include more details than just model)
                    product_data["description"] = desc_text

                # Create title from manufacturer and model
                title_parts = []
                if manufacturer:
                    title_parts.append(manufacturer)
                if model:
                    title_parts.append(model)
                elif desc_text:
                    # If no model parsed, use first part of description
                    desc_cleaned = re.sub(
                        r"^Used\s+", "", desc_text, flags=re.IGNORECASE
                    )
                    first_words = " ".join(desc_cleaned.split()[:3])
                    if first_words:
                        title_parts.append(first_words)

                if title_parts:
                    product_data["title"] = " ".join(title_parts)
                else:
                    product_data["title"] = "Ham Radio Equipment"

                # Extract price from third cell
                price_cell = cells[2]
                price_text = price_cell.get_text().strip()
                price = self._extract_price(price_text)
                if price:
                    product_data["price"] = price

                if product_data.get(
                    "title"
                ):  # Only add if we have a title (required field)
                    product = Product(**product_data)
                    products.append(product)

            except Exception as e:
                self.logger.error(f"Error extracting product: {e}")
                continue

        return products


    def get_items(self, category_name: str, max_items: int | None = None) -> list[Product]:
        """Get items from specified category."""
        if category_name == Category.used:
            return self.get_used_items(max_items)
        else:
            raise ValueError(f"Unknown category: {category_name}")

    def get_used_items(self, max_items: int | None = None) -> list[Product]:
        """Fetch all used equipment from R&L Electronics."""
        try:
            self.logger.info("Fetching R&L Electronics used equipment...")
            response = requests.get(
                "https://www2.randl.com/index.php?main_page=usedbrand"
            )
            response.raise_for_status()

            # Extract products from the HTML content
            products = self._extract_products_from_html(response.text)

            # Apply limit if specified
            if max_items and len(products) > max_items:
                products = products[:max_items]
                self.logger.info(f"Limited to {max_items} items")

            self.logger.info(f"Scraping completed! Total products found: {len(products)}")
            return products

        except Exception as e:
            self.logger.error(f"Error during scraping: {e}")
            return []
