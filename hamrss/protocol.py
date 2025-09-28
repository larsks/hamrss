from typing import Protocol
from typing import runtime_checkable


@runtime_checkable
class Catalog(Protocol):
    def get_categories(self) -> list[str]: ...
    def get_items(self, category_name: str, max_items: int | None = None): ...
