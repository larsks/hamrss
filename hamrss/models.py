import datetime

from typing import override
from pydantic import BaseModel


class Item(BaseModel):
    id: str
    title: str
    published: datetime.datetime
    updated: datetime.datetime | None
    description: str
    links: dict[str, str] = {}


class Channel(BaseModel):
    title: str
    link: str
    updated: datetime.datetime | None

    @override
    def __str__(self):
        return self.title


class Endpoint(BaseModel):
    prefix: str
    driver: str
    config: dict[str, str] = {}


class HamRssConfig(BaseModel):
    feeds: list[Endpoint]


class ConfigFile(BaseModel):
    hamrss: HamRssConfig | None = None
