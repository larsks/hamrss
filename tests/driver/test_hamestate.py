"""Tests for HamEstate RSS feed driver."""

import pytest
from unittest.mock import Mock, patch
import requests

from hamrss.driver.hamestate import Catalog, HamEstateSettings
from hamrss.model import Product


class TestHamEstateSettings:
    """Test cases for HamEstateSettings."""

    def test_settings_initialization(self):
        """Test settings initialization with defaults."""
        settings = HamEstateSettings()
        assert settings.max_items == 1000
        assert settings.timeout == 30


class TestCatalog:
    """Test cases for HamEstate Catalog."""

    @pytest.fixture
    def catalog(self):
        """Create Catalog instance."""
        return Catalog()

    def test_init(self, catalog):
        """Test Catalog initialization."""
        assert catalog.session is not None
        assert catalog.base_url == "https://www.hamestate.com"
        assert (
            catalog.equipment_categories_url
            == "https://www.hamestate.com/product-category/ham_equipment/"
        )
        assert catalog._cached_categories is None
        assert "User-Agent" in catalog.session.headers

    @patch("requests.Session.get")
    def test_get_categories_success(self, mock_get, catalog):
        """Test successful category discovery."""
        # Mock HTML response with category links
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.text = """
        <html>
            <body>
                <a href="/product-category/ham_equipment/amps/">Amplifiers</a>
                <a href="/product-category/ham_equipment/antennas/">Antennas</a>
                <a href="/product-category/ham_equipment/radios/">Radios</a>
                <a href="/product-category/other/stuff/">Other Stuff</a>
            </body>
        </html>
        """
        mock_get.return_value = mock_response

        categories = catalog.get_categories()

        assert len(categories) == 3  # Should exclude 'other' category
        assert "amps" in categories
        assert "antennas" in categories
        assert "radios" in categories
        assert categories == sorted(categories)  # Should be sorted

        # Should cache the result
        assert catalog._cached_categories == categories

        # Second call should use cache
        categories2 = catalog.get_categories()
        assert categories2 == categories
        mock_get.assert_called_once()  # Should only be called once due to caching

    @patch("requests.Session.get")
    def test_get_categories_network_error(self, mock_get, catalog):
        """Test category discovery with network error."""
        mock_get.side_effect = requests.RequestException("Network error")

        categories = catalog.get_categories()

        assert categories == []
        assert catalog._cached_categories is None

    @patch("requests.Session.get")
    def test_get_categories_parsing_error(self, mock_get, catalog):
        """Test category discovery with parsing error."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.text = "Invalid HTML"
        mock_get.return_value = mock_response

        categories = catalog.get_categories()

        assert categories == []
        assert catalog._cached_categories == []  # Empty list is cached, not None

    def test_build_rss_url(self, catalog):
        """Test RSS URL building."""
        url = catalog._build_rss_url("amps")
        assert (
            url == "https://www.hamestate.com/product-category/ham_equipment/amps/feed/"
        )

    @patch("requests.Session.get")
    @patch("feedparser.parse")
    def test_fetch_rss_feed_success(self, mock_parse, mock_get, catalog):
        """Test successful RSS feed fetching."""
        # Mock successful RSS response
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.content = b"<rss>test feed</rss>"
        mock_get.return_value = mock_response

        # Mock feedparser response
        mock_feed = Mock()
        mock_feed.entries = [Mock()]
        mock_feed.bozo = False
        mock_parse.return_value = mock_feed

        result = catalog._fetch_rss_feed("http://test.rss")

        assert result == mock_feed
        mock_get.assert_called_with("http://test.rss", timeout=30)
        mock_parse.assert_called_with(b"<rss>test feed</rss>")

    @patch("requests.Session.get")
    def test_fetch_rss_feed_empty_response(self, mock_get, catalog):
        """Test RSS feed fetching with empty response."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.content = b""
        mock_get.return_value = mock_response

        result = catalog._fetch_rss_feed("http://test.rss")

        assert result is None

    @patch("requests.Session.get")
    @patch("feedparser.parse")
    def test_fetch_rss_feed_no_entries(self, mock_parse, mock_get, catalog):
        """Test RSS feed fetching with no entries."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.content = b"<rss><channel></channel></rss>"
        mock_get.return_value = mock_response

        mock_feed = Mock()
        mock_feed.entries = []
        mock_feed.bozo = False
        mock_parse.return_value = mock_feed

        result = catalog._fetch_rss_feed("http://test.rss")

        assert result == mock_feed

    @patch("requests.Session.get")
    @patch("feedparser.parse")
    def test_fetch_rss_feed_bozo(self, mock_parse, mock_get, catalog):
        """Test RSS feed fetching with parsing issues."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.content = b"<rss>malformed feed</rss>"
        mock_get.return_value = mock_response

        mock_feed = Mock()
        mock_feed.entries = []
        mock_feed.bozo = True
        mock_feed.bozo_exception = "XML parsing error"
        mock_parse.return_value = mock_feed

        result = catalog._fetch_rss_feed("http://test.rss")

        assert result == mock_feed

    @patch("requests.Session.get")
    def test_fetch_rss_feed_network_error(self, mock_get, catalog):
        """Test RSS feed fetching with network error."""
        mock_get.side_effect = requests.RequestException("Network error")

        with pytest.raises(requests.RequestException):
            catalog._fetch_rss_feed("http://test.rss")

    def test_extract_products_from_feed(self, catalog):
        """Test product extraction from RSS feed."""

        # Create a proper mock entry class to simulate feedparser entries
        class MockEntry:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

        # Mock RSS feed entries
        mock_entry1 = MockEntry(
            title="ICOM IC-7300 HF Transceiver",
            link="https://www.hamestate.com/product/icom-ic-7300/",
            published="2024-01-15",
            summary="ICOM IC-7300 Used Item appears to be in Good condition. Serial #: 12345",
            author="Andrea Kizer",
        )

        mock_entry2 = MockEntry(
            title="Yaesu FT-991A All Band Transceiver",
            link="https://www.hamestate.com/product/yaesu-ft-991a/",
            author="Andrea Kizer",
            content=[Mock(value="Detailed description from content field")],
        )

        # Test entry with missing required fields
        mock_entry3 = MockEntry(
            title="Missing Link"
            # No link attribute
        )

        mock_feed = Mock()
        mock_feed.entries = [mock_entry1, mock_entry2, mock_entry3]

        products = catalog._extract_products_from_feed(mock_feed)

        assert len(products) == 2  # Third entry should be skipped

        # Check first product
        product1 = products[0]
        assert product1.title == "ICOM IC-7300 HF Transceiver"
        assert (
            product1.description
            == "ICOM IC-7300 Used Item appears to be in Good condition. Serial #: 12345"
        )
        assert product1.url == "https://www.hamestate.com/product/icom-ic-7300/"
        assert product1.date_added == "2024-01-15"
        assert product1.author == "Andrea Kizer"
        assert product1.manufacturer == "ICOM"
        assert product1.model == "IC-7300 HF Transceiver"

        # Check second product
        product2 = products[1]
        assert product2.title == "Yaesu FT-991A All Band Transceiver"
        assert product2.description == "Detailed description from content field"
        assert product2.url == "https://www.hamestate.com/product/yaesu-ft-991a/"
        assert product2.author == "Andrea Kizer"
        assert product2.manufacturer == "Yaesu"
        assert product2.model == "FT-991A All Band"

    def test_extract_products_from_feed_error_handling(self, catalog):
        """Test product extraction with malformed entries."""

        class MockEntry:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

        # Mock entry that will cause an error in Product creation
        mock_entry = MockEntry(title="Valid Title", link="https://example.com/product")

        mock_feed = Mock()
        mock_feed.entries = [mock_entry]

        # Mock Product constructor to raise an exception
        with patch(
            "hamrss.driver.hamestate.Product",
            side_effect=ValueError("Invalid product data"),
        ):
            products = catalog._extract_products_from_feed(mock_feed)

        assert len(products) == 0  # Should handle error gracefully

    @patch.object(Catalog, "get_categories")
    @patch.object(Catalog, "_fetch_rss_feed")
    @patch.object(Catalog, "_extract_products_from_feed")
    def test_get_items_success(
        self, mock_extract, mock_fetch, mock_categories, catalog
    ):
        """Test successful item fetching."""
        mock_categories.return_value = ["amps", "antennas"]
        mock_feed = Mock()
        mock_products = [Mock(spec=Product), Mock(spec=Product)]

        mock_fetch.return_value = mock_feed
        mock_extract.return_value = mock_products

        result = catalog.get_items("amps")

        assert result == mock_products
        mock_categories.assert_called_once()
        mock_fetch.assert_called_with(
            "https://www.hamestate.com/product-category/ham_equipment/amps/feed/"
        )
        mock_extract.assert_called_with(mock_feed)

    @patch.object(Catalog, "get_categories")
    def test_get_items_invalid_category(self, mock_categories, catalog):
        """Test get_items with invalid category."""
        mock_categories.return_value = ["amps", "antennas"]

        with pytest.raises(ValueError, match="Unknown category: invalid"):
            catalog.get_items("invalid")

    @patch.object(Catalog, "get_categories")
    @patch.object(Catalog, "_fetch_rss_feed")
    @patch.object(Catalog, "_extract_products_from_feed")
    def test_get_items_with_limit(
        self, mock_extract, mock_fetch, mock_categories, catalog
    ):
        """Test item fetching with max_items limit."""
        mock_categories.return_value = ["amps"]
        mock_feed = Mock()
        mock_products = [Mock(spec=Product) for _ in range(10)]

        mock_fetch.return_value = mock_feed
        mock_extract.return_value = mock_products

        result = catalog.get_items("amps", max_items=5)

        assert len(result) == 5
        assert result == mock_products[:5]

    @patch.object(Catalog, "get_categories")
    @patch.object(Catalog, "_fetch_rss_feed")
    def test_get_items_empty_feed(self, mock_fetch, mock_categories, catalog):
        """Test item fetching with empty feed."""
        mock_categories.return_value = ["amps"]
        mock_fetch.return_value = None

        result = catalog.get_items("amps")

        assert result == []

    @patch.object(Catalog, "get_categories")
    @patch.object(Catalog, "_fetch_rss_feed")
    def test_get_items_network_error(self, mock_fetch, mock_categories, catalog):
        """Test item fetching with network error."""
        mock_categories.return_value = ["amps"]
        mock_fetch.side_effect = requests.RequestException("Network error")

        result = catalog.get_items("amps")

        assert result == []

    @patch.object(Catalog, "get_categories")
    @patch.object(Catalog, "_fetch_rss_feed")
    def test_get_items_general_error(self, mock_fetch, mock_categories, catalog):
        """Test item fetching with general error."""
        mock_categories.return_value = ["amps"]
        mock_fetch.side_effect = Exception("General error")

        result = catalog.get_items("amps")

        assert result == []
