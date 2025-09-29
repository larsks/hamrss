"""Tests for RSS feed generation module."""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from hamrss.publisher.feeds import RSSFeedGenerator
from hamrss.publisher.config import PublisherSettings
from hamrss.database.models import Product


class TestRSSFeedGenerator:
    """Test cases for RSSFeedGenerator."""

    @pytest.fixture
    def settings(self):
        """Create test settings."""
        return PublisherSettings(
            feed_title="Test RSS Feed",
            feed_description="Test feed description",
            feed_link="http://test.example.com",
            max_items_per_feed=100,
        )

    @pytest.fixture
    def feed_generator(self, settings):
        """Create RSSFeedGenerator instance."""
        return RSSFeedGenerator(settings)

    @pytest.fixture
    def sample_product(self):
        """Create a sample product for testing."""
        now = datetime.now(timezone.utc)
        return Product(
            id=1,
            url="http://example.com/product1",
            title="Test Manufacturer TM-123",
            description="Test Ham Radio",
            manufacturer="Test Manufacturer",
            model="TM-123",
            product_id="PROD123",
            location="New York",
            date_added="2024-01-01",
            price="$299.99",
            image_url="http://example.com/image.jpg",
            author="W5RG",  # Add author field
            driver_name="hamrss.driver.hro",
            category="transceivers",
            scraped_at=now,
            first_seen=now,
            last_seen=now,
            is_active=True,
            scrape_run_id=1,
        )

    @pytest.fixture
    def sample_products(self, sample_product):
        """Create multiple sample products."""
        now = datetime.now(timezone.utc)
        product2 = Product(
            id=2,
            url="http://example.com/product2",
            title="Antenna Co ANT-456",
            description="Test Antenna",
            manufacturer="Antenna Co",
            model="ANT-456",
            price="$149.99",
            author="K8BB",  # Add author field to second product
            driver_name="hamrss.driver.mtc",
            category="antennas",
            scraped_at=now,
            first_seen=now,
            last_seen=now,
            is_active=True,
            scrape_run_id=1,
        )
        return [sample_product, product2]

    def test_init(self, settings):
        """Test RSSFeedGenerator initialization."""
        generator = RSSFeedGenerator(settings)
        assert generator.settings is settings

    def test_create_product_content(self, feed_generator, sample_product):
        """Test content creation for products with title and description outside metadata."""
        content = feed_generator._create_product_content(sample_product)

        # Should not contain HTML table elements
        assert "<table" not in content
        assert "<tr>" not in content
        assert "<td>" not in content

        # Should contain title as HTML heading
        assert "<h3>Test Manufacturer TM-123</h3>" in content
        # Should contain description as HTML paragraph
        assert "<p>Test Ham Radio</p>" in content

        # Should contain metadata in plain text format within pre tags
        assert "Manufacturer: Test Manufacturer" in content
        assert "Model: TM-123" in content
        assert "Price: $299.99" in content
        assert "Location: New York" in content
        assert "Author: W5RG" in content  # Check author field
        assert "Driver: hro" in content
        assert "Category: transceivers" in content
        assert "Link: http://example.com/product1" in content

    def test_create_product_content_minimal(self, feed_generator):
        """Test content creation with minimal product data."""
        now = datetime.now(timezone.utc)
        minimal_product = Product(
            id=1,
            url="http://example.com/minimal",
            title="Minimal Ham Radio Equipment",
            description="Minimal Product",
            driver_name="hamrss.driver.test",
            category="test",
            scraped_at=now,
            first_seen=now,
            last_seen=now,
            is_active=True,
            scrape_run_id=1,
        )

        content = feed_generator._create_product_content(minimal_product)

        # Should contain title as HTML heading
        assert "<h3>Minimal Ham Radio Equipment</h3>" in content
        # Should contain description as HTML paragraph
        assert "<p>Minimal Product</p>" in content

        # Should contain metadata in plain text format
        assert "Driver: test" in content
        assert "Category: test" in content
        assert "Link: http://example.com/minimal" in content

        # Should not contain image line (since no image_url was provided)
        assert "Image:" not in content
        # Should contain metadata in HTML pre tags
        assert "<pre>" in content and "</pre>" in content

    @patch("hamrss.publisher.feeds.FeedGenerator")
    def test_create_feed_basic(self, mock_feed_gen, feed_generator, sample_products):
        """Test basic feed creation."""
        # Mock FeedGenerator
        mock_fg = Mock()
        mock_feed_gen.return_value = mock_fg
        mock_fg.rss_str.return_value = b"<rss>test feed</rss>"

        result = feed_generator.create_feed(
            sample_products,
            title="Test Feed",
            description="Test Description",
            feed_path="/test",
        )

        assert result == "<rss>test feed</rss>"
        mock_fg.title.assert_called_with("Test Feed")
        mock_fg.description.assert_called_with("Test Description")
        mock_fg.language.assert_called_with("en")
        mock_fg.generator.assert_called_with("hamrss-publisher")

    def test_create_all_items_feed(self, feed_generator, sample_products):
        """Test creating all items feed."""
        with patch.object(feed_generator, "create_feed") as mock_create:
            mock_create.return_value = "test feed"

            result = feed_generator.create_all_items_feed(sample_products)

            assert result == "test feed"
            mock_create.assert_called_once_with(
                sample_products,
                title="Test RSS Feed",
                description="Test feed description",
                feed_path="/feed",
            )

    def test_create_driver_feed(self, feed_generator, sample_products):
        """Test creating driver-specific feed."""
        with patch.object(feed_generator, "create_feed") as mock_create:
            mock_create.return_value = "driver feed"

            result = feed_generator.create_driver_feed(sample_products, "hro")

            assert result == "driver feed"
            mock_create.assert_called_once_with(
                sample_products,
                title="Test RSS Feed - HRO",
                description="Items from HRO driver",
                feed_path="/feed/hro",
            )

    @patch("hamrss.publisher.feeds.FeedGenerator")
    def test_add_product_to_feed_with_author(
        self, mock_feed_gen, feed_generator, sample_product
    ):
        """Test that author information is added to RSS feed entries."""
        # Mock FeedGenerator and entry
        mock_fg = Mock()
        mock_fe = Mock()
        mock_feed_gen.return_value = mock_fg
        mock_fg.add_entry.return_value = mock_fe

        # Call the method
        feed_generator._add_product_to_feed(mock_fg, sample_product)

        # Verify author was set on the feed entry
        mock_fe.author.assert_called_once_with(name="W5RG")

        # Verify other required fields were also set
        mock_fe.title.assert_called_once()
        mock_fe.id.assert_called_once()
        mock_fe.link.assert_called_once()
        mock_fe.description.assert_called_once()

    @patch("hamrss.publisher.feeds.FeedGenerator")
    def test_add_product_to_feed_without_author(self, mock_feed_gen, feed_generator):
        """Test RSS feed entry creation when product has no author."""
        # Create product without author
        now = datetime.now(timezone.utc)
        product_no_author = Product(
            id=1,
            url="http://example.com/product1",
            title="Test Product",
            description="Test Description",
            driver_name="hamrss.driver.test",
            category="test",
            scraped_at=now,
            first_seen=now,
            last_seen=now,
            is_active=True,
            scrape_run_id=1,
        )

        # Mock FeedGenerator and entry
        mock_fg = Mock()
        mock_fe = Mock()
        mock_feed_gen.return_value = mock_fg
        mock_fg.add_entry.return_value = mock_fe

        # Call the method
        feed_generator._add_product_to_feed(mock_fg, product_no_author)

        # Verify author was NOT called (since product has no author)
        mock_fe.author.assert_not_called()

        # Verify other required fields were still set
        mock_fe.title.assert_called_once()
        mock_fe.id.assert_called_once()
        mock_fe.link.assert_called_once()
        mock_fe.description.assert_called_once()

    def test_create_category_feed(self, feed_generator, sample_products):
        """Test creating category-specific feed."""
        with patch.object(feed_generator, "create_feed") as mock_create:
            mock_create.return_value = "category feed"

            result = feed_generator.create_category_feed(
                sample_products, "hro", "transceivers"
            )

            assert result == "category feed"
            mock_create.assert_called_once_with(
                sample_products,
                title="Test RSS Feed - HRO Transceivers",
                description="Transceivers items from HRO driver",
                feed_path="/feed/hro/transceivers",
            )

    def test_dublin_core_creator_elements(self, feed_generator, sample_products):
        """Test that Dublin Core creator elements are added to RSS XML."""
        # Generate actual RSS feed (not mocked)
        rss_output = feed_generator.create_all_items_feed(sample_products)

        # Check for Dublin Core namespace
        assert 'xmlns:dc="http://purl.org/dc/elements/1.1/"' in rss_output

        # Check for dc:creator element for product with author (W5RG)
        assert "<dc:creator>W5RG</dc:creator>" in rss_output

        # Check for dc:creator element for product with author (K8BB)
        assert "<dc:creator>K8BB</dc:creator>" in rss_output

        # Verify the XML structure is valid by checking item structure
        lines = rss_output.split("\n")
        w5rg_item_found = False
        k8bb_item_found = False

        for i, line in enumerate(lines):
            if "Test Manufacturer TM-123" in line:
                # Look for dc:creator in the next lines until we find </item>
                for j in range(i, len(lines)):
                    if "<dc:creator>W5RG</dc:creator>" in lines[j]:
                        w5rg_item_found = True
                        break
                    elif "</item>" in lines[j]:
                        break
            elif "Antenna Co ANT-456" in line:
                # Look for dc:creator in the next lines until we find </item>
                for j in range(i, len(lines)):
                    if "<dc:creator>K8BB</dc:creator>" in lines[j]:
                        k8bb_item_found = True
                        break
                    elif "</item>" in lines[j]:
                        break

        assert w5rg_item_found, "dc:creator for W5RG not found in correct item"
        assert k8bb_item_found, "dc:creator for K8BB not found in correct item"

    def test_dublin_core_creator_no_author(self, feed_generator):
        """Test that products without authors don't get dc:creator elements."""
        # Create product without author
        now = datetime.now(timezone.utc)
        product_no_author = Product(
            id=1,
            url="http://example.com/product1",
            title="Test Product",
            description="Test Description",
            driver_name="hamrss.driver.test",
            category="test",
            scraped_at=now,
            first_seen=now,
            last_seen=now,
            is_active=True,
            scrape_run_id=1,
        )

        # Generate RSS feed
        rss_output = feed_generator.create_all_items_feed([product_no_author])

        # Should still have Dublin Core namespace (for consistency)
        assert 'xmlns:dc="http://purl.org/dc/elements/1.1/"' in rss_output

        # Should not have any dc:creator elements
        assert "<dc:creator>" not in rss_output
