"""Tests for Swap QTH driver."""

import pytest
from unittest.mock import Mock, patch
import requests

from hamrss.driver.qth import Catalog


class TestCatalog:
    """Test cases for Swap QTH Catalog."""

    @pytest.fixture
    def catalog(self):
        """Create Catalog instance."""
        return Catalog()

    @pytest.fixture
    def catalog_with_limit(self):
        """Create Catalog instance with custom product limit."""
        return Catalog(max_products=5)

    @pytest.fixture
    def catalog_unlimited(self):
        """Create Catalog instance with no product limit."""
        return Catalog(max_products=0)

    def test_init_default(self, catalog):
        """Test Catalog initialization with defaults."""
        assert catalog.max_products == 100
        assert catalog._categories_cache is None
        assert catalog.base_url == "https://swap.qth.com"

    def test_init_custom_limit(self, catalog_with_limit):
        """Test Catalog initialization with custom limit."""
        assert catalog_with_limit.max_products == 5

    def test_init_unlimited(self, catalog_unlimited):
        """Test Catalog initialization with unlimited products."""
        assert catalog_unlimited.max_products == 0

    @patch("requests.get")
    def test_discover_categories_success(self, mock_get, catalog):
        """Test successful category discovery."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.text = """
        <html>
            <body>
                <a href="c_radiohf.php">RADIOS - HF</a>
                <a href="c_amphf.php">AMPLIFIERS - HF</a>
                <a href="c_antvhf.php">ANTENNAS - VHF/UHF</a>
                <a href="c_misc.php">MISCELLANEOUS</a>
            </body>
        </html>
        """
        mock_get.return_value = mock_response

        categories = catalog._discover_categories()

        assert len(categories) == 4
        assert "RADIOS - HF" in categories
        assert "AMPLIFIERS - HF" in categories
        assert "ANTENNAS - VHF/UHF" in categories
        assert "MISCELLANEOUS" in categories
        assert categories["RADIOS - HF"] == "https://swap.qth.com/c_radiohf.php"
        assert categories["AMPLIFIERS - HF"] == "https://swap.qth.com/c_amphf.php"

    @patch("requests.get")
    def test_discover_categories_network_error(self, mock_get, catalog):
        """Test category discovery with network error."""
        mock_get.side_effect = requests.RequestException("Network error")

        categories = catalog._discover_categories()

        assert categories == {}

    @patch("requests.get")
    def test_discover_categories_empty_response(self, mock_get, catalog):
        """Test category discovery with no categories found."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.text = "<html><body>No categories here</body></html>"
        mock_get.return_value = mock_response

        categories = catalog._discover_categories()

        assert categories == {}

    @patch.object(Catalog, "_discover_categories")
    def test_get_categories_caching(self, mock_discover, catalog):
        """Test that categories are cached after first discovery."""
        mock_discover.return_value = {"Category 1": "url1", "Category 2": "url2"}

        # First call should discover categories
        categories1 = catalog.get_categories()
        assert categories1 == ["Category 1", "Category 2"]
        mock_discover.assert_called_once()

        # Second call should use cache
        categories2 = catalog.get_categories()
        assert categories2 == ["Category 1", "Category 2"]
        # Should still only be called once due to caching
        mock_discover.assert_called_once()

    def test_extract_products_from_html_success(self, catalog):
        """Test successful product extraction from malformed HTML structure."""
        # This HTML represents the actual malformed structure from swap.qth.com
        # where all products are nested within a single DT element
        html_content = """
        <html>
            <body>
                <dl>
                    <dt>
                        <b>Yaesu FT-991A Transceiver</b> <a href="view_ad.php?counter=123">View</a>
                        <dd>Excellent condition transceiver with all accessories. $1,200 shipped.</dd>
                        <dd>Listing #123 - Submitted on 12/15/24 by Callsign W1ABC - IP: test.com</dd>
                        <dd><a href="contact.php?counter=123">Click to Contact</a></dd>

                        <b>Icom IC-7300 Radio</b> <a href="view_ad.php?counter=456">View</a>
                        <dd>Great HF radio in working condition. $950 OBO.</dd>
                        <dd>Listing #456 - Submitted on 01/10/24 by Callsign K2XYZ - IP: test2.com</dd>
                        <dd><a href="contact.php?counter=456">Click to Contact</a></dd>
                    </dt>
                </dl>
            </body>
        </html>
        """

        products = catalog._extract_products_from_html(html_content)

        assert len(products) == 2

        # Check first product
        product1 = products[0]
        assert product1.title == "Yaesu FT-991A Transceiver"
        assert "Excellent condition transceiver" in product1.description
        assert product1.price is None
        assert product1.manufacturer == "Yaesu"
        assert product1.model == "FT-991A Transceiver"
        assert product1.url == "https://swap.qth.com/view_ad.php?counter=123"
        assert product1.date_added == "12/15/24"
        assert product1.author == "W1ABC"
        assert product1.location is None  # Location no longer used for callsign
        assert product1.product_id == "123"

        # Check second product
        product2 = products[1]
        assert product2.title == "Icom IC-7300 Radio"
        assert "Great HF radio" in product2.description
        assert product2.price is None
        assert product2.manufacturer == "Icom"
        assert product2.model == "IC-7300 Radio"
        assert product2.url == "https://swap.qth.com/view_ad.php?counter=456"
        assert product2.date_added == "01/10/24"
        assert product2.author == "K2XYZ"
        assert product2.location is None  # Location no longer used for callsign
        assert product2.product_id == "456"

    def test_extract_products_from_html_empty(self, catalog):
        """Test product extraction from empty HTML."""
        html_content = "<html><body></body></html>"

        products = catalog._extract_products_from_html(html_content)

        assert products == []

    def test_extract_products_with_callsign_pattern(self, catalog):
        """Test product extraction with ham radio callsign patterns."""
        html_content = """
        <dl>
            <dt>
                <b>Kenwood TS-590SG Transceiver</b> <a href="view_ad.php?counter=789">View</a>
                <dd>Great radio in excellent condition. $800 firm.</dd>
                <dd>Listing #789 - Submitted on 01/15/24 by Callsign N4TEST - IP: test.com</dd>
                <dd><a href="contact.php?counter=789">Click to Contact</a></dd>
            </dt>
        </dl>
        """

        products = catalog._extract_products_from_html(html_content)

        assert len(products) == 1
        product = products[0]
        assert (
            product.manufacturer == "Kenwood"
        )  # Should extract the brand name, not callsign
        assert product.author == "N4TEST"  # Callsign should be in author field
        assert product.location is None  # Location no longer used for callsign
        assert product.date_added == "01/15/24"
        assert product.price is None

    def test_get_next_page_url_with_next_link(self, catalog):
        """Test extracting next page URL from 'Next' link."""
        html_content = """
        <html>
            <body>
                <a href="category.php?page=2">Next 10 Ads</a>
            </body>
        </html>
        """

        next_url = catalog._get_next_page_url(html_content, "category.php?page=1")

        assert next_url == "https://swap.qth.com/category.php?page=2"

    def test_get_next_page_url_no_next(self, catalog):
        """Test extracting next page URL when no next page exists."""
        html_content = "<html><body>No more pages</body></html>"

        next_url = catalog._get_next_page_url(html_content, "category.php?page=1")

        assert next_url is None

    def test_extract_page_number(self, catalog):
        """Test extracting page number from URL."""
        assert catalog._extract_page_number("http://example.com?page=5") == 5
        assert catalog._extract_page_number("http://example.com?start=10") == 10
        assert catalog._extract_page_number("http://example.com") == 1
        assert catalog._extract_page_number("http://example.com?invalid=abc") == 1

    @patch("requests.get")
    def test_scrape_category_single_page(self, mock_get, catalog_with_limit):
        """Test scraping a category with single page."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.text = """
        <dl>
            <dt>
                <b>Product 1</b> <a href="view_ad.php?counter=100">View</a>
                <dd>Description of product 1. $100 shipped.</dd>
                <dd>Listing #100 - Submitted on 01/01/24 by Callsign W1TEST - IP: test.com</dd>
                <dd><a href="contact.php?counter=100">Contact</a></dd>

                <b>Product 2</b> <a href="view_ad.php?counter=200">View</a>
                <dd>Another item for sale. $200 firm.</dd>
                <dd>Listing #200 - Submitted on 01/02/24 by Callsign K2TEST - IP: test.com</dd>
                <dd><a href="contact.php?counter=200">Contact</a></dd>
            </dt>
        </dl>
        """
        mock_get.return_value = mock_response

        with patch.object(catalog_with_limit, "_get_next_page_url", return_value=None):
            products = catalog_with_limit._scrape_category(
                "http://test.com", "Test Category"
            )

        assert len(products) == 2
        mock_get.assert_called_once_with("http://test.com")

    @patch("requests.get")
    def test_scrape_category_with_limit(self, mock_get, catalog_with_limit):
        """Test scraping a category with product limit enforcement."""

        # Create mock responses with many products
        def create_mock_response(product_count):
            items = []
            for i in range(product_count):
                items.append(f"""
                <b>Product {i + 1}</b> <a href="view_ad.php?counter={i + 100}">View</a>
                <dd>Test product {i + 1} description. ${100 + i} shipped.</dd>
                <dd>Listing #{i + 100} - Submitted on 01/0{i + 1}/24 by Callsign W{i}TEST - IP: test.com</dd>
                <dd><a href="contact.php?counter={i + 100}">Contact</a></dd>
                """)
            return f"<dl><dt>{''.join(items)}</dt></dl>"

        mock_response1 = Mock()
        mock_response1.raise_for_status.return_value = None
        mock_response1.text = create_mock_response(3)

        mock_response2 = Mock()
        mock_response2.raise_for_status.return_value = None
        mock_response2.text = create_mock_response(4)

        mock_get.side_effect = [mock_response1, mock_response2]

        # Mock next page URL for first page only
        def mock_next_url(html, current_url):
            if "page=2" not in current_url:
                return "http://test.com?page=2"
            return None

        with patch.object(
            catalog_with_limit, "_get_next_page_url", side_effect=mock_next_url
        ):
            products = catalog_with_limit._scrape_category(
                "http://test.com", "Test Category"
            )

        # Should stop at limit of 5 products
        assert len(products) == 5

    @patch("requests.get")
    def test_scrape_category_network_error(self, mock_get, catalog):
        """Test scraping category with network error."""
        mock_get.side_effect = requests.RequestException("Network error")

        products = catalog._scrape_category("http://test.com", "Test Category")

        assert products == []

    def test_get_items_valid_category(self, catalog):
        """Test get_items with valid category."""
        # Mock the categories cache
        catalog._categories_cache = {"Test Category": "http://test.com/category.php"}

        with patch.object(catalog, "_scrape_category", return_value=[]) as mock_scrape:
            result = catalog.get_items("Test Category")
            mock_scrape.assert_called_once_with(
                "http://test.com/category.php", "Test Category", None
            )
            assert result == []

    def test_get_items_invalid_category(self, catalog):
        """Test get_items with invalid category."""
        catalog._categories_cache = {"Valid Category": "http://test.com"}

        with pytest.raises(ValueError, match="Unknown category: Invalid Category"):
            catalog.get_items("Invalid Category")

    def test_get_items_discovers_categories_if_needed(self, catalog):
        """Test that get_items discovers categories if cache is empty."""
        # Start with empty cache
        assert catalog._categories_cache is None

        def mock_get_categories():
            # Simulate the side effect of get_categories populating the cache
            catalog._categories_cache = {"Test Category": "http://test.com"}
            return ["Test Category"]

        with patch.object(
            catalog, "get_categories", side_effect=mock_get_categories
        ) as mock_get_cats:
            with patch.object(catalog, "_scrape_category", return_value=[]):
                catalog.get_items("Test Category")

            # Should call get_categories to populate cache
            mock_get_cats.assert_called_once()

    @patch("requests.get")
    def test_scrape_category_unlimited_products(self, mock_get, catalog_unlimited):
        """Test scraping with unlimited products (max_products=0)."""
        # Create a large mock response
        items = []
        for i in range(150):  # More than default limit
            items.append(f"""
            <b>Product {i + 1}</b> <a href="view_ad.php?counter={i + 1000}">View</a>
            <dd>Test product {i + 1} description. ${100 + i} firm.</dd>
            <dd>Listing #{i + 1000} - Submitted on 01/01/24 by Callsign W{i}TEST - IP: test.com</dd>
            <dd><a href="contact.php?counter={i + 1000}">Contact</a></dd>
            """)

        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.text = f"<dl><dt>{''.join(items)}</dt></dl>"
        mock_get.return_value = mock_response

        with patch.object(catalog_unlimited, "_get_next_page_url", return_value=None):
            products = catalog_unlimited._scrape_category(
                "http://test.com", "Test Category"
            )

        # Should get all 150 products since limit is 0 (unlimited)
        assert len(products) == 150

    def test_product_extraction_with_free_items(self, catalog):
        """Test product extraction with free items."""
        html_content = """
        <dl>
            <dt>
                <b>Old radio parts</b> <a href="view_ad.php?counter=999">View</a>
                <dd>Free to good home - various old radio parts and components.</dd>
                <dd>Listing #999 - Submitted on 01/01/24 by Callsign W1FREE - IP: test.com</dd>
                <dd><a href="contact.php?counter=999">Contact</a></dd>
            </dt>
        </dl>
        """

        products = catalog._extract_products_from_html(html_content)

        assert len(products) == 1
        product = products[0]
        assert product.price is None
        assert "good home" in product.description
        assert product.author == "W1FREE"
        assert product.location is None  # Location no longer used for callsign
