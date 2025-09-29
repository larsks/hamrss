"""RSS publisher main application."""

import logging
import sys
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator

import uvicorn
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import Response
from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker, Session

from .config import get_settings, PublisherSettings
from .feeds import RSSFeedGenerator
from .queries import FeedQueries

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Global database engine and session factory
engine: Engine = None
session_factory: sessionmaker = None


def setup_database(settings: PublisherSettings) -> None:
    """Initialize database connection."""
    global engine, session_factory

    logger.info(f"Connecting to database: {_get_log_safe_url(settings.database_url)}")

    engine = create_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_pool_overflow,
        pool_pre_ping=True,
    )

    session_factory = sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Get database session with automatic cleanup."""
    if not session_factory:
        raise RuntimeError("Database not initialized")

    session = session_factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _get_log_safe_url(url: str) -> str:
    """Get database URL with password masked for logging."""
    if "@" in url and "://" in url:
        scheme, rest = url.split("://", 1)
        if "@" in rest:
            credentials, host_part = rest.split("@", 1)
            if ":" in credentials:
                user, _ = credentials.split(":", 1)
                return f"{scheme}://{user}:***@{host_part}"
            else:
                return f"{scheme}://{credentials}:***@{host_part}"
    return url


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifespan events."""
    # Startup
    settings = get_settings()
    setup_database(settings)
    logger.info("RSS Publisher started")

    yield

    # Shutdown
    global engine
    if engine:
        engine.dispose()
    logger.info("RSS Publisher stopped")


# Create FastAPI app
app = FastAPI(
    title="Ham Radio RSS Publisher",
    description="RSS feeds for ham radio equipment catalogs",
    version="1.0.0",
    lifespan=lifespan,
)


# Dependency to get settings
def get_current_settings() -> PublisherSettings:
    return get_settings()


@app.get("/")
async def root():
    """Root endpoint with service information."""
    with get_db_session() as session:
        queries = FeedQueries(session)
        stats = queries.get_feed_stats()

    return {
        "service": "Ham Radio RSS Publisher",
        "version": "1.0.0",
        "endpoints": {
            "/feed": "All items RSS feed",
            "/feed/{driver}": "Driver-specific RSS feed",
            "/feed/{driver}/{category}": "Category-specific RSS feed",
            "/stats": "Feed statistics",
            "/opml": "OPML format listing of per-driver feeds",
        },
        "stats": stats,
        "available_feeds": {
            "drivers": list(stats["drivers"].keys()),
            "categories": list(stats["categories"].keys()),
        },
    }


@app.get("/stats")
async def get_stats():
    """Get feed statistics."""
    with get_db_session() as session:
        queries = FeedQueries(session)
        return queries.get_feed_stats()


@app.get("/feed")
async def get_all_items_feed(
    settings: PublisherSettings = Depends(get_current_settings),
):
    """Get RSS feed of all items."""
    with get_db_session() as session:
        queries = FeedQueries(session)
        products = queries.get_all_items(limit=settings.max_items_per_feed)

        if not products:
            raise HTTPException(status_code=404, detail="No products found")

        generator = RSSFeedGenerator(settings)
        rss_content = generator.create_all_items_feed(products)

        return Response(
            content=rss_content,
            media_type="application/rss+xml",
            headers={"Content-Type": "application/rss+xml; charset=utf-8"},
        )


@app.get("/feed/{driver}")
async def get_driver_feed(
    driver: str, settings: PublisherSettings = Depends(get_current_settings)
):
    """Get RSS feed for a specific driver."""
    with get_db_session() as session:
        queries = FeedQueries(session)
        products = queries.get_driver_items(driver, limit=settings.max_items_per_feed)

        if not products:
            available_drivers = queries.get_available_drivers()
            raise HTTPException(
                status_code=404,
                detail=f"No products found for driver '{driver}'. Available drivers: {available_drivers}",
            )

        generator = RSSFeedGenerator(settings)
        rss_content = generator.create_driver_feed(products, driver)

        return Response(
            content=rss_content,
            media_type="application/rss+xml",
            headers={"Content-Type": "application/rss+xml; charset=utf-8"},
        )


@app.get("/feed/{driver}/{category}")
async def get_category_feed(
    driver: str,
    category: str,
    settings: PublisherSettings = Depends(get_current_settings),
):
    """Get RSS feed for a specific driver and category."""
    with get_db_session() as session:
        queries = FeedQueries(session)
        products = queries.get_category_items(
            driver, category, limit=settings.max_items_per_feed
        )

        if not products:
            available_categories = queries.get_available_categories(driver)
            raise HTTPException(
                status_code=404,
                detail=f"No products found for driver '{driver}' and category '{category}'. "
                f"Available categories for {driver}: {available_categories}",
            )

        generator = RSSFeedGenerator(settings)
        rss_content = generator.create_category_feed(products, driver, category)

        return Response(
            content=rss_content,
            media_type="application/rss+xml",
            headers={"Content-Type": "application/rss+xml; charset=utf-8"},
        )


@app.get("/opml")
async def get_opml(
    request: Request, settings: PublisherSettings = Depends(get_current_settings)
):
    """Get OPML format listing of per-driver feeds."""
    with get_db_session() as session:
        queries = FeedQueries(session)
        stats = queries.get_feed_stats()

        drivers = stats["drivers"]

        # Use Host header to build base URL
        host = request.headers.get("host", "localhost:8080")
        scheme = (
            "https" if request.headers.get("x-forwarded-proto") == "https" else "http"
        )
        base_url = f"{scheme}://{host}"

        # Generate OPML content (even if empty)
        opml_content = _generate_opml(drivers, base_url)

        return Response(
            content=opml_content,
            media_type="application/xml",
            headers={"Content-Type": "application/xml; charset=utf-8"},
        )


def _generate_opml(drivers: dict[str, int], base_url: str) -> str:
    """Generate OPML format content for per-driver feeds."""
    from xml.sax.saxutils import escape
    from datetime import datetime

    now = datetime.now().strftime("%a, %d %b %Y %H:%M:%S GMT")

    opml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<opml version="1.0">',
        "  <head>",
        "    <title>Ham RSS Feeds</title>",
        f"    <dateCreated>{now}</dateCreated>",
        f"    <dateModified>{now}</dateModified>",
        "    <ownerName>Ham RSS Publisher</ownerName>",
        "  </head>",
        "  <body>",
        '    <outline text="Ham RSS Feeds" title="Ham RSS Feeds">',
    ]

    # Add feed for all items
    opml_lines.append(
        f'      <outline type="rss" text="All Items" title="All Items" '
        f'xmlUrl="{escape(base_url)}/feed" htmlUrl="{escape(base_url)}" />'
    )

    # Add per-driver feeds
    for driver in sorted(drivers.keys()):
        count = drivers[driver]
        title = f"{driver} ({count} items)"
        opml_lines.append(
            f'      <outline type="rss" text="{escape(title)}" title="{escape(title)}" '
            f'xmlUrl="{escape(base_url)}/feed/{escape(driver)}" htmlUrl="{escape(base_url)}" />'
        )

    opml_lines.extend(
        [
            "    </outline>",
            "  </body>",
            "</opml>",
        ]
    )

    return "\n".join(opml_lines)


def run_server() -> None:
    """Entry point for the console script."""
    settings = get_settings()

    logger.info(f"Starting RSS Publisher on {settings.host}:{settings.port}")

    try:
        uvicorn.run(
            "hamrss.publisher.main:app",
            host=settings.host,
            port=settings.port,
            log_level="info",
            access_log=True,
        )
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_server()
