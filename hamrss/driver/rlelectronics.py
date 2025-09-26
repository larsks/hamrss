"""R&L Electronics catalog scraper driver."""

import requests
from bs4 import BeautifulSoup
import re
from enum import Enum

from ..model import Product


class Category(str, Enum):
    """Available product categories."""

    used = "used"


class Catalog:
    """R&L Electronics catalog scraper for used equipment."""

    def __init__(self, playwright_server=None):
        # Ignore the playwright_server parameter as we use requests instead
        pass

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
                    if href and not href.startswith("http"):
                        product_data["url"] = f"https://www2.randl.com/{href}"
                    else:
                        product_data["url"] = href

                    # Extract product ID from URL
                    if href and "products_id=" in href:
                        product_id = href.split("products_id=")[1].split("&")[0]
                        product_data["product_id"] = product_id

                # Extract full description text
                desc_text = desc_cell.get_text().strip()
                if desc_text:
                    product_data["description"] = desc_text

                    # Try to parse model from description
                    # Look for text after "Used " prefix
                    desc_cleaned = re.sub(
                        r"^Used\s+", "", desc_text, flags=re.IGNORECASE
                    )
                    if desc_cleaned:
                        # Take first few words as potential model
                        model_parts = desc_cleaned.split()[:2]
                        if model_parts:
                            product_data["model"] = " ".join(model_parts)

                # Extract price from third cell
                price_cell = cells[2]
                price_text = price_cell.get_text().strip()
                if price_text and price_text.startswith("$"):
                    product_data["price"] = price_text

                if product_data:  # Only add if we extracted some data
                    product = Product(**product_data)
                    products.append(product)

            except Exception as e:
                print(f"Error extracting product: {e}")
                continue

        return products

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
        """Fetch all used equipment from R&L Electronics."""
        try:
            print("Fetching R&L Electronics used equipment...")
            response = requests.get(
                "https://www2.randl.com/index.php?main_page=usedbrand"
            )
            response.raise_for_status()

            # Extract products from the HTML content
            products = self._extract_products_from_html(response.text)

            print(f"Scraping completed! Total products found: {len(products)}")
            return products

        except Exception as e:
            print(f"Error during scraping: {e}")
            return []

