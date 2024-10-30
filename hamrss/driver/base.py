import requests
import bs4

from typing import Any
from abc import ABC
from abc import abstractmethod

from .. import models


class BaseDriver(ABC):
    requires_auth = False

    def __init__(self, session: requests.Session):
        self.session = session

    def get_soup(self, url: str, **kwargs: dict[str, Any]):
        res = self.session.get(url, **kwargs)
        res.raise_for_status()
        return bs4.BeautifulSoup(res.text, "lxml")

    @abstractmethod
    def channels(self) -> list[models.Channel]: ...
    @abstractmethod
    def channel(self, channel_name: str) -> models.Channel: ...
    @abstractmethod
    def items(self, channel_name: str) -> list[models.Item]: ...
    @abstractmethod
    def refresh(self) -> None: ...

    def search(self, query: str) -> list[models.Item]:
        return []

    def authenticate(self, username: str, password: str) -> None: ...
