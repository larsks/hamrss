from playwright.sync_api import sync_playwright
import re
import json
import time
from pydantic import BaseModel


class Product(BaseModel):
    manufacturer: str | None = None
    model: str | None = None
    url: str
    product_id: str | None = None
    description: str
    location: str | None = None
    date_added: str | None = None
    price: str
    image_url: str | None = None


def extract_products_from_page(page) -> list[Product]:
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

            # Extract price from the button with price
            price_elem = container.query_selector(
                '.btn-primary[style*="background-color:#FFF"]'
            )
            if price_elem:
                product_data["price"] = price_elem.inner_text().strip()

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


def get_total_pages(page) -> int:
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


def scrape_hamradio_used_equipment() -> list[Product]:
    """Main scraper function to fetch all pages of used equipment."""
    all_products: list[Product] = []

    with sync_playwright() as p:
        # Connect to the existing Playwright server
        browser = p.chromium.connect("ws://127.0.0.1:3000/")
        page = browser.new_page()

        try:
            # Navigate to the used equipment page
            print("Navigating to Ham Radio used equipment page...")
            page.goto("https://www.hamradio.com/used.cfm")

            # Wait for the page to load
            page.wait_for_selector('select[name="jumpPage"]', timeout=10000)

            # Get total number of pages
            total_pages = get_total_pages(page)
            print(f"Found {total_pages} pages to scrape")

            # Scrape each page
            for page_num in range(total_pages):
                print(f"Scraping page {page_num + 1} of {total_pages}...")

                # Extract products from current page
                products = extract_products_from_page(page)
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

            # Save results to JSON file
            with open("hamradio_used_equipment.json", "w") as f:
                json.dump(
                    [product.model_dump() for product in all_products], f, indent=2
                )

            print("Results saved to hamradio_used_equipment.json")

        except Exception as e:
            print(f"Error during scraping: {e}")

        finally:
            page.close()

    return all_products


if __name__ == "__main__":
    products = scrape_hamradio_used_equipment()
    print(f"Successfully scraped {len(products)} products")
