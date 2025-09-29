"""Tests for database migration system."""

import pytest
import tempfile
import os
from unittest.mock import Mock

from hamrss.database.migrations import Migration, MigrationManager, setup_migrations
from hamrss.database.connection import DatabaseManager
from sqlalchemy import create_engine, text


class TestMigration:
    """Test cases for Migration class."""

    def test_migration_init(self):
        """Test Migration initialization."""
        migration = Migration(
            version=1,
            description="Test migration",
            up_sql="CREATE TABLE test (id INTEGER PRIMARY KEY)",
            down_sql="DROP TABLE test",
        )

        assert migration.version == 1
        assert migration.description == "Test migration"
        assert migration.up_sql == "CREATE TABLE test (id INTEGER PRIMARY KEY)"
        assert migration.down_sql == "DROP TABLE test"

    def test_migration_init_callable(self):
        """Test Migration initialization with callable."""

        def test_func(engine):
            pass

        migration = Migration(version=1, description="Test migration", up_sql=test_func)

        assert migration.version == 1
        assert callable(migration.up_sql)


class TestMigrationManager:
    """Test cases for MigrationManager class."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        engine = create_engine(f"sqlite:///{db_path}")
        yield engine

        engine.dispose()
        if os.path.exists(db_path):
            os.unlink(db_path)

    def test_migration_manager_init(self, temp_db):
        """Test MigrationManager initialization."""
        manager = MigrationManager(temp_db)

        assert manager.engine is temp_db
        assert manager.migrations == []

        # Check that migration table was created
        with temp_db.begin() as conn:
            result = conn.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
                )
            ).fetchone()
            assert result is not None

    def test_add_migration(self, temp_db):
        """Test adding migrations to manager."""
        manager = MigrationManager(temp_db)

        migration1 = Migration(2, "Second migration", "SELECT 2")
        migration2 = Migration(1, "First migration", "SELECT 1")

        manager.add_migration(migration1)
        manager.add_migration(migration2)

        # Should be sorted by version
        assert len(manager.migrations) == 2
        assert manager.migrations[0].version == 1
        assert manager.migrations[1].version == 2

    def test_get_applied_versions_empty(self, temp_db):
        """Test getting applied versions with no migrations."""
        manager = MigrationManager(temp_db)
        applied = manager.get_applied_versions()
        assert applied == []

    def test_apply_migrations(self, temp_db):
        """Test applying migrations."""
        manager = MigrationManager(temp_db)

        # Add a simple migration that creates a table
        migration = Migration(
            version=1,
            description="Create test table",
            up_sql="CREATE TABLE test_migration (id INTEGER PRIMARY KEY, data TEXT)",
        )
        manager.add_migration(migration)

        # Apply migrations
        manager.apply_migrations()

        # Check that migration was recorded
        applied = manager.get_applied_versions()
        assert applied == [1]

        # Check that table was created
        with temp_db.begin() as conn:
            result = conn.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='test_migration'"
                )
            ).fetchone()
            assert result is not None

    def test_apply_migrations_callable(self, temp_db):
        """Test applying migrations with callable."""

        def create_table(engine):
            with engine.begin() as conn:
                conn.execute(
                    text("CREATE TABLE test_callable (id INTEGER PRIMARY KEY)")
                )

        manager = MigrationManager(temp_db)
        migration = Migration(
            version=1, description="Create table via callable", up_sql=create_table
        )
        manager.add_migration(migration)

        manager.apply_migrations()

        # Check that table was created
        with temp_db.begin() as conn:
            result = conn.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='test_callable'"
                )
            ).fetchone()
            assert result is not None

    def test_get_pending_migrations(self, temp_db):
        """Test getting pending migrations."""
        manager = MigrationManager(temp_db)

        migration1 = Migration(1, "First", "SELECT 1")
        migration2 = Migration(2, "Second", "SELECT 2")

        manager.add_migration(migration1)
        manager.add_migration(migration2)

        # All should be pending initially
        pending = manager.get_pending_migrations()
        assert len(pending) == 2

        # Apply first migration manually
        migration1.apply(temp_db)
        manager._record_migration(migration1)

        # Now only second should be pending
        pending = manager.get_pending_migrations()
        assert len(pending) == 1
        assert pending[0].version == 2

    def test_get_current_version(self, temp_db):
        """Test getting current schema version."""
        manager = MigrationManager(temp_db)

        # Should be 0 initially
        assert manager.get_current_version() == 0

        # Apply a migration
        migration = Migration(1, "Test", "SELECT 1")
        migration.apply(temp_db)
        manager._record_migration(migration)

        assert manager.get_current_version() == 1


class TestMigrationIntegration:
    """Integration tests for migration system."""

    def test_setup_migrations(self):
        """Test setting up migration manager with all migrations."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            engine = create_engine(f"sqlite:///{db_path}")
            manager = setup_migrations(engine)

            # Should have at least two migrations (title column and author column)
            assert len(manager.migrations) >= 2
            assert any(
                m.description.startswith("Add title column") for m in manager.migrations
            )
            assert any(
                m.description.startswith("Add author column") for m in manager.migrations
            )

            engine.dispose()

        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_author_column_migration(self):
        """Test the author column migration specifically."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            engine = create_engine(f"sqlite:///{db_path}")

            # Create a basic products table first (without author column)
            with engine.begin() as conn:
                conn.execute(text("""
                    CREATE TABLE products (
                        id INTEGER PRIMARY KEY,
                        url TEXT NOT NULL,
                        title TEXT NOT NULL,
                        description TEXT,
                        manufacturer TEXT,
                        model TEXT,
                        product_id TEXT,
                        location TEXT,
                        date_added TEXT,
                        price TEXT,
                        image_url TEXT
                    )
                """))

                # Insert a test record
                conn.execute(text("""
                    INSERT INTO products (url, title, description)
                    VALUES ('http://test.com', 'Test Product', 'Test Description')
                """))

            # Set up migrations and apply them
            manager = setup_migrations(engine)
            manager.apply_migrations()

            # Check that author column was added
            with engine.begin() as conn:
                # Try to select from author column - this will fail if column doesn't exist
                result = conn.execute(text("SELECT author FROM products LIMIT 1")).fetchone()
                # Should succeed and return None for existing record
                assert result[0] is None

                # Test inserting a record with author
                conn.execute(text("""
                    INSERT INTO products (url, title, author)
                    VALUES ('http://test2.com', 'Test Product 2', 'W5RG')
                """))

                # Verify the author was stored correctly
                result = conn.execute(text("""
                    SELECT author FROM products WHERE title = 'Test Product 2'
                """)).fetchone()
                assert result[0] == 'W5RG'

            engine.dispose()

        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_database_manager_with_migrations(self):
        """Test that DatabaseManager runs migrations automatically."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            # Mock settings
            settings = Mock()
            settings.database_url = f"sqlite:///{db_path}"
            settings.db_pool_size = 5
            settings.db_pool_overflow = 10
            settings.log_level = "INFO"

            # Initialize database manager
            db_manager = DatabaseManager(settings)
            db_manager.initialize()

            # Check that migrations table exists
            with db_manager.get_session() as session:
                result = session.execute(
                    text(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
                    )
                ).fetchone()
                assert result is not None

                # Check that at least one migration was applied
                migrations = session.execute(
                    text("SELECT version FROM schema_migrations ORDER BY version")
                ).fetchall()
                assert len(migrations) >= 1

            db_manager.close()

        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
