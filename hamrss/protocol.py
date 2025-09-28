from typing import runtime_checkable, Protocol

from .model import Product


@runtime_checkable
class Catalog(Protocol):
    def get_categories(self) -> list[str]: ...
    def get_items(self, category_name: str, max_items: int | None = None) -> list[Product]: ...
