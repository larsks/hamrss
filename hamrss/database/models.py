"""Database models for the ham radio scraper server."""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Boolean,
    Index,
    UniqueConstraint,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class Product(Base):
    """Model for storing scraped product data."""

    __tablename__ = "products"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Product information
    url = Column(String(500), nullable=False)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    manufacturer = Column(String(100), nullable=True)
    model = Column(String(100), nullable=True)
    product_id = Column(String(100), nullable=True)
    location = Column(String(100), nullable=True)
    date_added = Column(
        String(50), nullable=True
    )  # Store as string since format varies
    price = Column(String(50), nullable=True)
    image_url = Column(String(500), nullable=True)

    # Scraping metadata
    driver_name = Column(String(100), nullable=False)
    category = Column(String(50), nullable=False)
    scraped_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    scrape_run_id = Column(Integer, nullable=False)

    # Tracking fields
    first_seen = Column(DateTime(timezone=True), nullable=False, default=func.now())
    last_seen = Column(DateTime(timezone=True), nullable=False, default=func.now())
    is_active = Column(Boolean, nullable=False, default=True)

    # Indexes for performance
    __table_args__ = (
        Index("idx_products_driver_category", "driver_name", "category"),
        Index("idx_products_scraped_at", "scraped_at"),
        Index("idx_products_url", "url"),
        Index("idx_products_product_id", "product_id"),
        Index("idx_products_active", "is_active"),
        UniqueConstraint("url", "driver_name", name="uq_product_url_driver"),
    )

    def __repr__(self):
        return f"<Product(id={self.id}, url='{self.url[:50]}...', driver='{self.driver_name}')>"


class ScrapeRun(Base):
    """Model for tracking scraping sessions."""

    __tablename__ = "scrape_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Run information
    started_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(
        String(20), nullable=False, default="running"
    )  # running, completed, failed

    # Statistics
    total_drivers = Column(Integer, nullable=False, default=0)
    completed_drivers = Column(Integer, nullable=False, default=0)
    failed_drivers = Column(Integer, nullable=False, default=0)
    total_products = Column(Integer, nullable=False, default=0)

    # Configuration snapshot
    enabled_drivers = Column(Text, nullable=True)  # JSON string of driver list

    # Error information
    error_message = Column(Text, nullable=True)

    # Indexes
    __table_args__ = (
        Index("idx_scrape_runs_started_at", "started_at"),
        Index("idx_scrape_runs_status", "status"),
    )

    def __repr__(self):
        return f"<ScrapeRun(id={self.id}, started_at='{self.started_at}', status='{self.status}')>"


class ScrapeError(Base):
    """Model for logging scraping errors."""

    __tablename__ = "scrape_errors"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Error information
    scrape_run_id = Column(Integer, nullable=False)
    driver_name = Column(String(100), nullable=False)
    category = Column(String(50), nullable=True)
    error_type = Column(String(100), nullable=False)
    error_message = Column(Text, nullable=False)
    error_traceback = Column(Text, nullable=True)

    # Timing
    occurred_at = Column(DateTime(timezone=True), nullable=False, default=func.now())

    # Indexes
    __table_args__ = (
        Index("idx_scrape_errors_run_id", "scrape_run_id"),
        Index("idx_scrape_errors_driver", "driver_name"),
        Index("idx_scrape_errors_occurred_at", "occurred_at"),
    )

    def __repr__(self):
        return f"<ScrapeError(id={self.id}, driver='{self.driver_name}', error='{self.error_type}')>"


class DriverStats(Base):
    """Model for tracking per-driver statistics."""

    __tablename__ = "driver_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Driver information
    scrape_run_id = Column(Integer, nullable=False)
    driver_name = Column(String(100), nullable=False)
    category = Column(String(50), nullable=False)

    # Statistics
    products_found = Column(Integer, nullable=False, default=0)
    products_new = Column(Integer, nullable=False, default=0)
    products_updated = Column(Integer, nullable=False, default=0)

    # Timing
    started_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Integer, nullable=True)

    # Status
    status = Column(
        String(20), nullable=False, default="running"
    )  # running, completed, failed
    error_message = Column(Text, nullable=True)

    # Indexes
    __table_args__ = (
        Index("idx_driver_stats_run_id", "scrape_run_id"),
        Index("idx_driver_stats_driver", "driver_name"),
        Index("idx_driver_stats_started_at", "started_at"),
        UniqueConstraint(
            "scrape_run_id", "driver_name", "category", name="uq_driver_stat_per_run"
        ),
    )

    def __repr__(self):
        return f"<DriverStats(id={self.id}, driver='{self.driver_name}', category='{self.category}', products={self.products_found})>"
