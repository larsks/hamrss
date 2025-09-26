"""CLI interface for Ham Radio catalog scraper."""

from playwright.sync_api import sync_playwright
import json
import typer
import importlib

from hamrss import PlaywrightServer
from hamrss import protocol

from typing import cast

app = typer.Typer(help="Ham Radio Outlet catalog scraper")


def load_driver(driver_name: str) -> protocol.Catalog:
    """Load a catalog driver module and return its Catalog class."""
    try:
        module = importlib.import_module(driver_name)
        assert isinstance(module.Catalog, protocol.Catalog)
        return module.Catalog
    except ImportError as e:
        typer.echo(f"Error: Could not load driver '{driver_name}': {e}", err=True)
        raise typer.Exit(1)


@app.command()
def main(
    driver: str = typer.Option(
        "hamrss.driver.hro",
        "--driver",
        "-d",
        help="Catalog driver to use (e.g., hro for Ham Radio Outlet)",
    ),
    category: str | None = typer.Option(
        None,
        "--category",
        "-c",
        help="Category of products to scrape. If not specified, shows available categories.",
    ),
    output: str | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file path. If not specified, prints to stdout.",
    ),
    playwright_server: str = typer.Option(
        "ws://127.0.0.1:3000/",
        "--playwright-server",
        "-S",
        help="WebSocket URL for the Playwright server.",
    ),
):
    """Scrape catalog and output product data as JSON."""

    # Load the specified driver
    CatalogClass = load_driver(driver)

    # Create PlaywrightServer instance (will only connect when needed)
    playwright_server_instance = PlaywrightServer(playwright_server)

    # Create catalog instance with the playwright server
    catalog = CatalogClass(playwright_server_instance)

    # Get available categories
    available_categories = catalog.get_categories()

    # If no category specified, show available categories
    if category is None:
        typer.echo(f"Available categories for driver '{driver}':")
        for cat in available_categories:
            typer.echo(f"  - {cat}")
        typer.echo("\nUse --category (-c) to specify a category to scrape.")
        return

    # Validate category
    if category not in available_categories:
        typer.echo(
            f"Error: Unknown category '{category}' for driver '{driver}'",
            err=True,
        )
        typer.echo(
            f"Available categories: {', '.join(available_categories)}", err=True
        )
        raise typer.Exit(1)

    # Get products from specified category
    products = catalog.get_items(category)

    # Convert products to JSON
    json_data = json.dumps(
        [product.model_dump() for product in products], indent=2
    )

    # Output to file or stdout
    if output:
        with open(output, "w") as f:
            f.write(json_data)
        typer.echo(f"Results saved to {output}", err=True)
    else:
        typer.echo(json_data)

    typer.echo(
        f"Successfully scraped {len(products)} {category} products using driver '{driver}'",
        err=True,
    )


if __name__ == "__main__":
    app()
