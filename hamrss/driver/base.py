"""Base driver classes for catalog scrapers."""

from abc import ABC, abstractmethod
from typing import Any
import logging
import re
from urllib.parse import urljoin

from ..model import Product
from ..playwright_server import PlaywrightServer

logger = logging.getLogger(__name__)


class BaseCatalog(ABC):
    """Base class for all catalog drivers."""

    playwright_server: PlaywrightServer | None
    logger: logging.Logger

    def __init__(self, playwright_server: PlaywrightServer | None = None):
        self.playwright_server = playwright_server
        self.logger = logging.getLogger(self.__module__)

    def get_categories(self) -> list[str]:
        """Get available categories. Override in subclass."""
        raise NotImplementedError("get_categories must be implemented by subclass")

    @abstractmethod
    def get_items(
        self, category_name: str, max_items: int | None = None
    ) -> list[Product]:
        """Get items from specified category."""
        pass

    def _normalize_url(self, href: str, base_url: str) -> str:
        """Normalize relative URLs to fully qualified URLs."""
        if href and not href.startswith("http"):
            return urljoin(base_url, href)
        return href

    def _extract_manufacturer_model_from_title(
        self, title: str
    ) -> tuple[str | None, str | None]:
        """Extract manufacturer and model from product title."""
        if not title:
            return None, None

        # Remove common prefixes
        title_cleaned = re.sub(
            r"^(U\d+\s+Used\s+|Certified Pre-Loved\s+|Used\s+|FS:\s+|FOR\s+|SALE\s+|NEW\s+)",
            "",
            title,
            flags=re.IGNORECASE,
        )

        parts = title_cleaned.split()
        if len(parts) >= 2:
            manufacturer = parts[0]
            # For longer titles, take more words for the model to preserve more context
            model_end_idx = min(len(parts), 4) if len(parts) > 3 else len(parts)
            model = " ".join(parts[1:model_end_idx])
            return manufacturer, model

        return None, None

    def _extract_price(self, price_text: str) -> str | None:
        """Extract and validate price text."""
        if price_text and price_text.strip().startswith("$"):
            return price_text.strip()
        return None

    def _safe_extract_product(
        self, extractor_func: Any, context: str = "product"
    ) -> Product | None:
        """Safely extract product with consistent error handling."""
        try:
            return extractor_func()
        except Exception as e:
            self.logger.error(f"Error extracting {context}: {e}")
            return None


class EnumCatalogMixin:
    """Mixin for catalogs that use Enum-based categories."""

    def get_categories(self) -> list[str]:
        """Get available categories from Category enum."""
        if hasattr(self, "Category") and self.Category:
            return [x.value for x in self.Category]
        raise NotImplementedError("Category enum not defined")
