"""RSS publisher main application."""

import logging
import sys
from contextlib import contextmanager
from typing import Generator

import uvicorn
from fastapi import FastAPI, HTTPException, Depends
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


# Create FastAPI app
app = FastAPI(
    title="Ham Radio RSS Publisher",
    description="RSS feeds for ham radio equipment catalogs",
    version="1.0.0",
)

# Dependency to get settings
def get_current_settings() -> PublisherSettings:
    return get_settings()


@app.on_event("startup")
async def startup_event():
    """Initialize the application."""
    settings = get_settings()
    setup_database(settings)
    logger.info("RSS Publisher started")


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources."""
    global engine
    if engine:
        engine.dispose()
    logger.info("RSS Publisher stopped")


@app.get("/")
async def root():
    """Root endpoint with service information."""
    settings = get_current_settings()

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
            "/stats": "Feed statistics"
        },
        "stats": stats,
        "available_feeds": {
            "drivers": list(stats["drivers"].keys()),
            "categories": list(stats["categories"].keys())
        }
    }


@app.get("/stats")
async def get_stats():
    """Get feed statistics."""
    with get_db_session() as session:
        queries = FeedQueries(session)
        return queries.get_feed_stats()


@app.get("/feed")
async def get_all_items_feed(settings: PublisherSettings = Depends(get_current_settings)):
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
            headers={"Content-Type": "application/rss+xml; charset=utf-8"}
        )


@app.get("/feed/{driver}")
async def get_driver_feed(
    driver: str,
    settings: PublisherSettings = Depends(get_current_settings)
):
    """Get RSS feed for a specific driver."""
    with get_db_session() as session:
        queries = FeedQueries(session)
        products = queries.get_driver_items(driver, limit=settings.max_items_per_feed)

        if not products:
            available_drivers = queries.get_available_drivers()
            raise HTTPException(
                status_code=404,
                detail=f"No products found for driver '{driver}'. Available drivers: {available_drivers}"
            )

        generator = RSSFeedGenerator(settings)
        rss_content = generator.create_driver_feed(products, driver)

        return Response(
            content=rss_content,
            media_type="application/rss+xml",
            headers={"Content-Type": "application/rss+xml; charset=utf-8"}
        )


@app.get("/feed/{driver}/{category}")
async def get_category_feed(
    driver: str,
    category: str,
    settings: PublisherSettings = Depends(get_current_settings)
):
    """Get RSS feed for a specific driver and category."""
    with get_db_session() as session:
        queries = FeedQueries(session)
        products = queries.get_category_items(driver, category, limit=settings.max_items_per_feed)

        if not products:
            available_categories = queries.get_available_categories(driver)
            raise HTTPException(
                status_code=404,
                detail=f"No products found for driver '{driver}' and category '{category}'. "
                       f"Available categories for {driver}: {available_categories}"
            )

        generator = RSSFeedGenerator(settings)
        rss_content = generator.create_category_feed(products, driver, category)

        return Response(
            content=rss_content,
            media_type="application/rss+xml",
            headers={"Content-Type": "application/rss+xml; charset=utf-8"}
        )


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