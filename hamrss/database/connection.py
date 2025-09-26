"""Database connection management."""

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import event, create_engine, Engine, text
from sqlalchemy.orm import sessionmaker, Session

from ..config import ServerSettings
from .models import Base

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database connections and sessions."""

    def __init__(self, settings: ServerSettings):
        self.settings = settings
        self.engine: Engine | None = None
        self.session_factory: sessionmaker[Session] | None = None

    def initialize(self) -> None:
        """Initialize the database connection and create tables."""
        logger.info(f"Connecting to database: {self._get_log_safe_url()}")

        # Use the database URL as-is for sync operations
        database_url = self.settings.database_url

        # Create sync engine
        self.engine = create_engine(
            database_url,
            pool_size=self.settings.db_pool_size,
            max_overflow=self.settings.db_pool_overflow,
            pool_pre_ping=True,  # Verify connections before use
            echo=self.settings.log_level == "DEBUG",  # Log SQL queries in debug mode
        )

        # Add connection event listeners
        @event.listens_for(self.engine, "connect")
        def receive_connect(dbapi_connection, connection_record):
            logger.debug("Database connection established")

        # Create session factory
        self.session_factory = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
        )

        # Create tables if they don't exist
        Base.metadata.create_all(self.engine)
        logger.info("Database tables created/verified")

    def close(self) -> None:
        """Close the database connection."""
        if self.engine:
            self.engine.dispose()
            logger.info("Database connections closed")

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """Get a database session with automatic cleanup."""
        if not self.session_factory:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        session = self.session_factory()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        else:
            session.commit()
        finally:
            session.close()

    def health_check(self) -> bool:
        """Check if the database connection is healthy."""
        try:
            with self.get_session() as session:
                session.execute(text("SELECT 1"))
                return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False

    def _get_log_safe_url(self) -> str:
        """Get database URL with password masked for logging."""
        url = self.settings.database_url
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


# Global database manager instance
_db_manager: DatabaseManager | None = None


def get_database_manager(settings: ServerSettings | None = None) -> DatabaseManager:
    """Get the global database manager instance."""
    global _db_manager
    if _db_manager is None:
        if settings is None:
            from ..config import get_settings
            settings = get_settings()
        _db_manager = DatabaseManager(settings)
    return _db_manager


def init_database(settings: ServerSettings | None = None) -> DatabaseManager:
    """Initialize the database and return the manager."""
    db_manager = get_database_manager(settings)
    db_manager.initialize()
    return db_manager


def close_database() -> None:
    """Close the database connection."""
    global _db_manager
    if _db_manager:
        _db_manager.close()
        _db_manager = None