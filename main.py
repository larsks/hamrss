"""CLI interface for Ham Radio Outlet catalog scraper."""

from playwright.sync_api import sync_playwright
import json
import typer

from hamrss.drivers.hrocatalog import HROCatalog, Category
from hamrss import PlaywrightServer

app = typer.Typer(help="Ham Radio Outlet catalog scraper")


@app.command()
def main(
    category: Category = typer.Option(
        Category.used,
        "--category",
        "-c",
        help="Category of products to scrape (used, open, consignment)",
    ),
    output: str | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file path. If not specified, prints to stdout.",
    ),
):
    """Scrape Ham Radio Outlet catalog and output product data as JSON."""

    with PlaywrightServer() as server:
        with sync_playwright() as p:
            browser = p.chromium.connect(server.get_ws_url())
            catalog = HROCatalog(browser)

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
                f"Successfully scraped {len(products)} {category.value} products",
                err=True,
            )


if __name__ == "__main__":
    app()
