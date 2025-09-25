from playwright.sync_api import sync_playwright, Page, Playwright
import re
import json
import time
import sys
from pydantic import BaseModel
from enum import Enum
import typer


class Category(str, Enum):
    """Available product categories."""
    used = "used"
    open = "open"
    consignment = "consignment"


class Product(BaseModel):
    manufacturer: str | None = None
    model: str | None = None
    url: str | None = None
    product_id: str | None = None
    description: str | None = None
    location: str | None = None
    date_added: str | None = None
    price: str | None = None
    image_url: str | None = None


class HROCatalog:
    """Ham Radio Outlet catalog scraper for used, open item, and consignment products."""

    def __init__(self, playwright: Playwright):
        self.playwright = playwright
        self.browser = playwright.chromium.connect("ws://127.0.0.1:3000/")

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
                h4_elements = container.query_selector_all(".prod-caption h4")
                if len(h4_elements) >= 2:
                    manufacturer_elem = h4_elements[0].query_selector("strong")
                    if manufacturer_elem:
                        product_data["manufacturer"] = (
                            manufacturer_elem.inner_text().strip()
                        )

                    model_elem = h4_elements[1]
                    if model_elem:
                        product_data["model"] = model_elem.inner_text().strip()

                # Extract product URL from the first link
                link_elem = container.query_selector(".prod-caption a")
                if link_elem:
                    product_data["url"] = link_elem.get_attribute("href")
                    # Extract product ID from URL
                    href = product_data["url"]
                    if "pid=" in href:
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
                price_elem = container.query_selector('.btn-primary[style*="background-color:#FFF"]')
                if not price_elem:
                    # Try open items page format (orange background)
                    price_elem = container.query_selector('.btn-primary[style*="background-color:#FF9900"]')
                if not price_elem:
                    # Try other possible price button formats
                    price_elem = container.query_selector('.btn-group .btn-primary:first-child')
                if price_elem:
                    price_text = price_elem.inner_text().strip()
                    # Only set price if it looks like a price (starts with $)
                    if price_text.startswith('$'):
                        product_data["price"] = price_text

                # Extract image URL
                img_elem = container.query_selector("img")
                if img_elem:
                    product_data["image_url"] = img_elem.get_attribute("src")

                if product_data:  # Only add if we extracted some data
                    product = Product(**product_data)
                    products.append(product)

            except Exception as e:
                print(f"Error extracting product: {e}")
                continue

        return products

    def _get_total_pages(self, page: Page) -> int:
        """Extract the total number of pages from the pagination text."""
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
            print(f"Error getting total pages: {e}")

        return 1

    def _scrape_catalog(self, url: str, catalog_name: str) -> list[Product]:
        """Generic method to scrape any HRO catalog with pagination."""
        all_products: list[Product] = []
        page = self.browser.new_page()

        try:
            # Navigate to the catalog page
            print(f"Navigating to {catalog_name}...")
            page.goto(url)

            # Wait for the page to load
            page.wait_for_selector('select[name="jumpPage"]', timeout=10000)

            # Get total number of pages
            total_pages = self._get_total_pages(page)
            print(f"Found {total_pages} pages to scrape")

            # Scrape each page
            for page_num in range(total_pages):
                print(f"Scraping page {page_num + 1} of {total_pages}...")

                # Extract products from current page
                products = self._extract_products_from_page(page)
                all_products.extend(products)
                print(f"Found {len(products)} products on page {page_num + 1}")

                # Navigate to next page if not the last page
                if page_num < total_pages - 1:
                    try:
                        # Find the select element and get the next page value
                        select_elem = page.query_selector('select[name="jumpPage"]')
                        options = select_elem.query_selector_all("option")

                        # Get the value for the next page
                        next_page_value = options[page_num + 1].get_attribute("value")

                        # Select the next page
                        page.select_option('select[name="jumpPage"]', next_page_value)

                        # Wait for the page to update
                        time.sleep(2)
                        page.wait_for_selector(".hero-feature", timeout=10000)

                    except Exception as e:
                        print(f"Error navigating to page {page_num + 2}: {e}")
                        break

            print(f"Scraping completed! Total products found: {len(all_products)}")

        except Exception as e:
            print(f"Error during scraping: {e}")

        finally:
            page.close()

        return all_products

    def get_used_items(self) -> list[Product]:
        """Fetch all used equipment from /used.cfm"""
        return self._scrape_catalog("https://www.hamradio.com/used.cfm", "Ham Radio used equipment")

    def get_open_items(self) -> list[Product]:
        """Fetch all open items from /open_item.cfm"""
        return self._scrape_catalog("https://www.hamradio.com/open_item.cfm", "Ham Radio open items")

    def get_consignment_items(self) -> list[Product]:
        """Fetch all consignment items from /consignment.cfm"""
        return self._scrape_catalog("https://www.hamradio.com/consignment.cfm", "Ham Radio consignment items")


app = typer.Typer(help="Ham Radio Outlet catalog scraper")


@app.command()
def main(
    category: Category = typer.Option(
        Category.used,
        "--category",
        "-c",
        help="Category of products to scrape (used, open, consignment)"
    ),
    output: str | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file path. If not specified, prints to stdout."
    )
):
    """Scrape Ham Radio Outlet catalog and output product data as JSON."""

    with sync_playwright() as p:
        catalog = HROCatalog(p)

        # Get products based on category
        if category == Category.used:
            products = catalog.get_used_items()
        elif category == Category.open:
            products = catalog.get_open_items()
        elif category == Category.consignment:
            products = catalog.get_consignment_items()
        else:
            typer.echo(f"Error: Unknown category '{category}'", err=True)
            raise typer.Exit(1)

        # Convert products to JSON
        json_data = json.dumps([product.model_dump() for product in products], indent=2)

        # Output to file or stdout
        if output:
            with open(output, "w") as f:
                f.write(json_data)
            typer.echo(f"Results saved to {output}", err=True)
        else:
            typer.echo(json_data)

        typer.echo(f"Successfully scraped {len(products)} {category.value} products", err=True)


if __name__ == "__main__":
    app()
