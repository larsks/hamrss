"""Tests for QRZ RSS feed driver."""

import pytest
from unittest.mock import Mock, patch

from hamrss.driver.qrz import Catalog, Category, QRZSettings
from hamrss.model import Product


class TestQRZSettings:
    """Test cases for QRZSettings."""

    def test_settings_with_env_vars(self, monkeypatch):
        """Test settings loading from environment variables."""
        monkeypatch.setenv("HAMRSS_QRZ_USERNAME", "testuser")
        monkeypatch.setenv("HAMRSS_QRZ_PASSWORD", "testpass")

        settings = QRZSettings()
        assert settings.username == "testuser"
        assert settings.password == "testpass"


class TestCatalog:
    """Test cases for QRZ Catalog."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        with patch("hamrss.driver.qrz.QRZSettings") as mock:
            mock_instance = Mock()
            mock_instance.username = "testuser"
            mock_instance.password = "testpass"
            mock.return_value = mock_instance
            yield mock_instance

    @pytest.fixture
    def catalog(self, mock_settings):
        """Create Catalog instance with mocked settings."""
        return Catalog()

    def test_init(self, catalog):
        """Test Catalog initialization."""
        assert catalog.session is not None
        assert not catalog._authenticated

    def test_get_categories(self, catalog):
        """Test get_categories method."""
        categories = catalog.get_categories()
        assert "ham-radio-gear-for-sale" in categories
        assert categories == [Category.ham_radio_gear_for_sale]

    @patch("requests.Session.get")
    @patch("requests.Session.post")
    def test_authenticate_success(self, mock_post, mock_get, catalog):
        """Test successful authentication."""
        # Mock login page response with proper form
        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.text = """
        <form action="//www.qrz.com/login" method="post">
            <input type="hidden" name="nojs" value="test123">
            <input type="text" name="username" value="">
            <input type="password" name="password" value="">
        </form>
        """

        # Mock successful login response
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.text = "welcome user logout"
        mock_post.return_value.url = "https://www.qrz.com/home"

        result = catalog._authenticate()

        assert result is True
        assert catalog._authenticated is True
        mock_get.assert_called_with("https://www.qrz.com/login")

    @patch("requests.Session.get")
    @patch("requests.Session.post")
    def test_authenticate_failure(self, mock_post, mock_get, catalog):
        """Test failed authentication."""
        # Mock login page response
        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.text = "login page"

        # Mock failed login response (stays on login page)
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.text = "login failed"
        mock_post.return_value.url = "https://www.qrz.com/login"

        result = catalog._authenticate()

        assert result is False
        assert catalog._authenticated is False

    @patch("requests.Session.get")
    def test_authenticate_already_authenticated(self, mock_get, catalog):
        """Test authentication when already authenticated."""
        catalog._authenticated = True

        result = catalog._authenticate()

        assert result is True
        mock_get.assert_not_called()

    @patch("requests.Session.get")
    @patch("feedparser.parse")
    def test_fetch_rss_feed_success(self, mock_parse, mock_get, catalog):
        """Test successful RSS feed fetching."""
        catalog._authenticated = True

        # Mock successful RSS response
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.content = b"<rss>test feed</rss>"
        mock_get.return_value = mock_response

        # Mock feedparser response
        mock_feed = Mock()
        mock_feed.entries = []
        mock_feed.bozo = False
        mock_parse.return_value = mock_feed

        result = catalog._fetch_rss_feed("http://test.rss")

        assert result == mock_feed
        mock_get.assert_called_with("http://test.rss")
        mock_parse.assert_called_with(b"<rss>test feed</rss>")

    @patch("requests.Session.get")
    def test_fetch_rss_feed_with_failed_auth(self, mock_get, catalog):
        """Test RSS feed fetching when authentication fails but feed is still accessible."""
        # Mock authentication failure
        with patch.object(
            catalog, "_authenticate", side_effect=Exception("Auth failed")
        ):
            # Mock successful RSS response despite auth failure
            mock_response = Mock()
            mock_response.raise_for_status.return_value = None
            mock_response.content = b"<rss><channel><title>Test</title></channel></rss>"
            mock_get.return_value = mock_response

            # Mock feedparser response
            with patch("feedparser.parse") as mock_parse:
                mock_feed = Mock()
                mock_feed.entries = []
                mock_feed.bozo = False
                mock_parse.return_value = mock_feed

                # Should succeed despite auth failure
                result = catalog._fetch_rss_feed("http://test.rss")
                assert result == mock_feed

    def test_extract_products_from_feed(self, catalog):
        """Test product extraction from RSS feed."""

        # Create a proper mock entry class to simulate feedparser entries
        class MockEntry:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

        # Mock RSS feed entries
        mock_entry1 = MockEntry(
            title="Yaesu FT-991A - Excellent Condition",
            link="https://forums.qrz.com/index.php?threads/yaesu-ft-991a.123456/",
            published="2024-01-15",
            summary="Full description from RSS summary field",
            author="W5RG",  # Add author field for testing
        )

        mock_entry2 = MockEntry(
            title="Icom IC-7300",
            link="https://forums.qrz.com/index.php?threads/icom-ic-7300.789012/",
            # No published attribute for second entry
            author="K8BB",  # Add author field for testing
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
        assert product1.title == "Yaesu FT-991A - Excellent Condition"
        assert (
            product1.description == "Full description from RSS summary field"
        )  # Description from RSS summary
        assert (
            product1.url
            == "https://forums.qrz.com/index.php?threads/yaesu-ft-991a.123456/"
        )
        assert product1.date_added == "2024-01-15"
        assert product1.author == "W5RG"  # Check author extraction
        assert product1.manufacturer == "Yaesu"
        assert product1.model == "FT-991A"

        # Check second product
        product2 = products[1]
        assert product2.title == "Icom IC-7300"
        assert (
            product2.description is None
        )  # No dash separator, so no description extracted
        assert (
            product2.url
            == "https://forums.qrz.com/index.php?threads/icom-ic-7300.789012/"
        )
        assert product2.author == "K8BB"  # Check author extraction
        assert product2.manufacturer == "Icom"
        assert product2.model == "IC-7300"

    def test_get_items_valid_category(self, catalog):
        """Test get_items with valid category."""
        with patch.object(
            catalog, "get_ham_radio_gear_for_sale", return_value=[]
        ) as mock_method:
            result = catalog.get_items("ham-radio-gear-for-sale")
            mock_method.assert_called_once()
            assert result == []

    def test_get_items_invalid_category(self, catalog):
        """Test get_items with invalid category."""
        with pytest.raises(ValueError, match="Unknown category"):
            catalog.get_items("invalid-category")

    @patch.object(Catalog, "_fetch_rss_feed")
    @patch.object(Catalog, "_extract_products_from_feed")
    def test_get_ham_radio_gear_for_sale_success(
        self, mock_extract, mock_fetch, catalog
    ):
        """Test successful ham radio gear for sale fetching."""
        mock_feed = {"entries": []}
        mock_products = [Mock(spec=Product)]

        mock_fetch.return_value = mock_feed
        mock_extract.return_value = mock_products

        result = catalog.get_ham_radio_gear_for_sale()

        assert result == mock_products
        expected_url = "https://forums.qrz.com/index.php?forums/ham-radio-gear-for-sale.7/index.rss"
        mock_fetch.assert_called_with(expected_url)
        mock_extract.assert_called_with(mock_feed)

    @patch.object(Catalog, "_fetch_rss_feed")
    def test_get_ham_radio_gear_for_sale_error(self, mock_fetch, catalog):
        """Test ham radio gear for sale fetching with error."""
        mock_fetch.side_effect = Exception("Network error")

        result = catalog.get_ham_radio_gear_for_sale()

        assert result == []  # Should return empty list on error

    def test_extract_products_with_simple_title(self, catalog):
        """Test product extraction with simple title (no manufacturer/model parsing)."""

        # Create a proper mock entry class to simulate feedparser entries
        class MockEntry:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

        mock_entry = MockEntry(
            title="Simple title without dash",
            link="http://example.com/item",
            # No published attribute
        )

        mock_feed = Mock()
        mock_feed.entries = [mock_entry]

        products = catalog._extract_products_from_feed(mock_feed)

        assert len(products) == 1
        product = products[0]
        assert product.title == "Simple title without dash"
        assert (
            product.description is None
        )  # No dash separator, so no description extracted
        assert product.url == "http://example.com/item"
        assert product.manufacturer == "Simple"
        assert product.model == "title without dash"
