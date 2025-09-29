"""Database migration system for automated schema updates."""

import logging
from typing import List, Callable
from datetime import datetime, timezone

from sqlalchemy import text, Engine, MetaData, Table, Column, Integer, String, DateTime
from sqlalchemy.sql import func

logger = logging.getLogger(__name__)


class Migration:
    """Represents a single database migration."""

    def __init__(
        self,
        version: int,
        description: str,
        up_sql: str | Callable[[Engine], None],
        down_sql: str | None = None,
    ):
        """Initialize a migration.

        Args:
            version: Migration version number (should be sequential)
            description: Human-readable description of the migration
            up_sql: SQL statement(s) to apply the migration, or callable that takes engine
            down_sql: SQL statement(s) to rollback the migration (optional)
        """
        self.version = version
        self.description = description
        self.up_sql = up_sql
        self.down_sql = down_sql

    def apply(self, engine: Engine) -> None:
        """Apply this migration to the database."""
        logger.info(f"Applying migration {self.version}: {self.description}")

        with engine.begin() as conn:
            if callable(self.up_sql):
                # If it's a callable, execute it with the engine
                self.up_sql(engine)
            else:
                # If it's a string, execute as SQL
                for statement in self.up_sql.split(";"):
                    statement = statement.strip()
                    if statement:
                        conn.execute(text(statement))

        logger.info(f"Migration {self.version} applied successfully")

    def rollback(self, engine: Engine) -> None:
        """Rollback this migration from the database."""
        if not self.down_sql:
            raise ValueError(f"Migration {self.version} does not support rollback")

        logger.info(f"Rolling back migration {self.version}: {self.description}")

        with engine.begin() as conn:
            for statement in self.down_sql.split(";"):
                statement = statement.strip()
                if statement:
                    conn.execute(text(statement))

        logger.info(f"Migration {self.version} rolled back successfully")


class MigrationManager:
    """Manages database migrations and version tracking."""

    def __init__(self, engine: Engine):
        self.engine = engine
        self.migrations: List[Migration] = []
        self._ensure_migration_table()

    def _ensure_migration_table(self) -> None:
        """Create the migration tracking table if it doesn't exist."""
        # Use SQLAlchemy's MetaData to create the table
        metadata = MetaData()

        Table(
            "schema_migrations",
            metadata,
            Column("version", Integer, primary_key=True),
            Column("description", String(255), nullable=False),
            Column(
                "applied_at",
                DateTime(timezone=True),
                nullable=False,
                default=func.now(),
            ),
        )

        # Create the table if it doesn't exist
        metadata.create_all(self.engine)
        logger.debug("Migration tracking table ensured")

    def add_migration(self, migration: Migration) -> None:
        """Add a migration to the manager."""
        self.migrations.append(migration)
        # Keep migrations sorted by version
        self.migrations.sort(key=lambda m: m.version)

    def get_applied_versions(self) -> List[int]:
        """Get list of migration versions that have been applied."""
        with self.engine.begin() as conn:
            result = conn.execute(
                text("SELECT version FROM schema_migrations ORDER BY version")
            )
            return [row[0] for row in result]

    def get_pending_migrations(self) -> List[Migration]:
        """Get list of migrations that haven't been applied yet."""
        applied_versions = set(self.get_applied_versions())
        return [m for m in self.migrations if m.version not in applied_versions]

    def apply_migrations(self) -> None:
        """Apply all pending migrations."""
        pending = self.get_pending_migrations()

        if not pending:
            logger.info("No pending migrations")
            return

        logger.info(f"Applying {len(pending)} pending migrations")

        for migration in pending:
            try:
                migration.apply(self.engine)
                self._record_migration(migration)
            except Exception as e:
                logger.error(f"Migration {migration.version} failed: {e}")
                raise

        logger.info("All migrations applied successfully")

    def _record_migration(self, migration: Migration) -> None:
        """Record that a migration has been applied."""
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO schema_migrations (version, description, applied_at) VALUES (:version, :description, :applied_at)"
                ),
                {
                    "version": migration.version,
                    "description": migration.description,
                    "applied_at": datetime.now(timezone.utc),
                },
            )

    def get_current_version(self) -> int:
        """Get the current schema version (highest applied migration)."""
        applied_versions = self.get_applied_versions()
        return max(applied_versions) if applied_versions else 0

    def rollback_to_version(self, target_version: int) -> None:
        """Rollback to a specific version (not implemented for safety)."""
        # This could be implemented if needed, but requires careful consideration
        # of rollback order and dependencies
        raise NotImplementedError("Rollback functionality not implemented for safety")


def _add_author_column_migration(engine: Engine) -> None:
    """Migration function to add author column to products table."""
    logger.info("Adding author column to products table")

    # First, check if products table exists (separate transaction)
    table_exists = False
    try:
        with engine.begin() as conn:
            if str(engine.url).startswith("sqlite"):
                table_check = conn.execute(
                    text(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='products'"
                    )
                ).fetchone()
            else:
                table_check = conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables WHERE table_name='products'"
                    )
                ).fetchone()

            table_exists = table_check is not None

    except Exception as e:
        logger.info(
            f"Could not check for products table existence: {e}, skipping migration"
        )
        return

    if not table_exists:
        logger.info("Products table doesn't exist yet, skipping migration")
        return

    # Check if author column already exists (separate transaction)
    column_exists = False
    try:
        with engine.begin() as conn:
            if str(engine.url).startswith("sqlite"):
                # For SQLite, try selecting the column
                conn.execute(text("SELECT author FROM products LIMIT 1"))
                column_exists = True
            else:
                # For PostgreSQL, use information_schema
                result = conn.execute(
                    text("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'products' AND column_name = 'author'
                """)
                ).fetchone()
                column_exists = result is not None

    except Exception:
        # Column doesn't exist, proceed with migration
        column_exists = False

    if column_exists:
        logger.info("Author column already exists, skipping")
        return

    # Apply the migration: Add the column
    try:
        with engine.begin() as conn:
            # Add the author column (nullable for existing data)
            if str(engine.url).startswith("sqlite"):
                conn.execute(text("ALTER TABLE products ADD COLUMN author TEXT"))
            else:
                conn.execute(text("ALTER TABLE products ADD COLUMN author VARCHAR(100)"))
            logger.info("Author column added successfully")
    except Exception as e:
        logger.error(f"Failed to add author column: {e}")
        raise


def _add_title_column_migration(engine: Engine) -> None:
    """Migration function to add title column to products table."""
    logger.info("Adding title column to products table")

    # First, check if products table exists (separate transaction)
    table_exists = False
    try:
        with engine.begin() as conn:
            if str(engine.url).startswith("sqlite"):
                table_check = conn.execute(
                    text(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='products'"
                    )
                ).fetchone()
            else:
                table_check = conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables WHERE table_name='products'"
                    )
                ).fetchone()

            table_exists = table_check is not None

    except Exception as e:
        logger.info(
            f"Could not check for products table existence: {e}, skipping migration"
        )
        return

    if not table_exists:
        logger.info("Products table doesn't exist yet, skipping migration")
        return

    # Check if title column already exists (separate transaction)
    column_exists = False
    try:
        with engine.begin() as conn:
            if str(engine.url).startswith("sqlite"):
                # For SQLite, try selecting the column
                conn.execute(text("SELECT title FROM products LIMIT 1"))
                column_exists = True
            else:
                # For PostgreSQL, use information_schema
                result = conn.execute(
                    text("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'products' AND column_name = 'title'
                """)
                ).fetchone()
                column_exists = result is not None

    except Exception:
        # Column doesn't exist, proceed with migration
        column_exists = False

    if column_exists:
        logger.info("Title column already exists, skipping")
        return

    # Apply the migration: Add the column
    try:
        with engine.begin() as conn:
            # Add the title column (initially nullable)
            conn.execute(text("ALTER TABLE products ADD COLUMN title TEXT"))
            logger.info("Title column added")
    except Exception as e:
        logger.error(f"Failed to add title column: {e}")
        raise

    # Update existing data (separate transaction)
    try:
        with engine.begin() as conn:
            # Update existing rows to have a title based on description
            # This provides a reasonable default for existing data
            if str(engine.url).startswith("sqlite"):
                # SQLite syntax
                conn.execute(
                    text("""
                    UPDATE products
                    SET title = CASE
                        WHEN manufacturer IS NOT NULL AND model IS NOT NULL
                        THEN manufacturer || ' ' || model
                        WHEN description IS NOT NULL
                        THEN SUBSTR(description, 1, 100)
                        ELSE 'Ham Radio Equipment'
                    END
                    WHERE title IS NULL
                """)
                )
            else:
                # PostgreSQL/MySQL syntax
                conn.execute(
                    text("""
                    UPDATE products
                    SET title = CASE
                        WHEN manufacturer IS NOT NULL AND model IS NOT NULL
                        THEN manufacturer || ' ' || model
                        WHEN description IS NOT NULL
                        THEN SUBSTRING(description FROM 1 FOR 100)
                        ELSE 'Ham Radio Equipment'
                    END
                    WHERE title IS NULL
                """)
                )
            logger.info("Updated existing products with default titles")
    except Exception as e:
        logger.error(f"Failed to update existing products with titles: {e}")
        raise

    # Apply constraints (separate transaction for PostgreSQL)
    try:
        with engine.begin() as conn:
            # For SQLite, we need to recreate the table to add NOT NULL constraint
            # For other databases, we can use ALTER COLUMN
            if str(engine.url).startswith("sqlite"):
                # SQLite doesn't support ALTER COLUMN, so we'll skip making it NOT NULL for now
                # The application code will ensure new records have titles
                logger.info(
                    "SQLite detected - skipping NOT NULL constraint (handled by application)"
                )
            else:
                # Make the column NOT NULL after populating it
                conn.execute(
                    text("ALTER TABLE products ALTER COLUMN title SET NOT NULL")
                )
                logger.info("Title column set to NOT NULL")

                # Make description column nullable if it isn't already
                conn.execute(
                    text("ALTER TABLE products ALTER COLUMN description DROP NOT NULL")
                )
                logger.info("Description column set to nullable")
    except Exception as e:
        logger.error(f"Failed to apply column constraints: {e}")
        raise


def get_all_migrations() -> List[Migration]:
    """Get all available migrations in order."""
    return [
        Migration(
            version=1,
            description="Add title column to products table and make description optional",
            up_sql=_add_title_column_migration,
            down_sql=None,  # Rollback not supported for data safety
        ),
        Migration(
            version=2,
            description="Add author column to products table",
            up_sql=_add_author_column_migration,
            down_sql=None,  # Rollback not supported for data safety
        ),
        # Future migrations can be added here
    ]


def setup_migrations(engine: Engine) -> MigrationManager:
    """Set up the migration manager with all migrations."""
    manager = MigrationManager(engine)

    # Add all migrations
    for migration in get_all_migrations():
        manager.add_migration(migration)

    return manager
