import datetime
import itertools
import re
import requests
import logging

from typing import override
from urllib.parse import urljoin

from .base import BaseDriver
from .. import models

LOG = logging.getLogger(__name__)


class QTHDriver(BaseDriver):
    entries_per_category = 20
    base_url = "https://swap.qth.com"
    category_listing_url = "index.php"
    search_url = "search-results.php"
    re_entry_metadata = re.compile(
        r"Listing #(?P<listingid>\d+) +- +Submitted on (?P<date_created>\d\d/\d\d/\d\d) "
        r"by Callsign (?P<callsign>[^ ,]+),? "
        r"(Modified on (?P<date_modified>\d\d/\d\d/\d\d),? )?"
        r"(Web Site: (?P<website>[^ ]+ ))?"
        r"(.*)"
    )

    _channels: dict[str, models.Channel]

    def __init__(self, session: requests.Session):
        super().__init__(session)
        self._channels = {}

    @override
    def refresh(self):
        soup = self.get_soup(urljoin(self.base_url, self.category_listing_url))

        row = soup.find(
            "td", string=lambda text: "VIEW BY CATEGORY" in text if text else None
        ).parent

        while True:
            row = row.findNextSibling()
            if row is None:
                break
            if row.find(
                "td", string=lambda text: "QUICK SEARCH" in text if text else None
            ):
                break
            links = row.findAll("a")
            self._channels.update(
                {
                    link.text.strip(): models.Channel(
                        link=urljoin(self.base_url, link["href"]),
                        title=link.text.strip(),
                        updated=datetime.datetime.now(datetime.UTC),
                    )
                    for link in links
                }
            )

    @override
    def channels(self) -> list[models.Channel]:
        return list(self._channels.values())

    @override
    def channel(self, channel_name: str) -> models.Channel:
        return self._channels[channel_name]

    @override
    def items(self, channel_name: str) -> list[models.Item]:
        items: list[models.Item] = []
        channel = self.channel(channel_name)

        page = itertools.count(start=1)
        while len(items) < self.entries_per_category:
            batch = self._items_page(channel, page=next(page))
            if not batch:
                break
            items.extend(batch)

        return items

    def _items_page(self, channel: models.Channel, page: int = 1) -> list[models.Item]:
        soup = self.get_soup(channel.link, params={"page": page})
        dl = soup.select(".qth-content-wrap dl")
        if not dl:
            return []

        return self._items_from_dl(dl)

    def _items_from_dl(self, dl) -> list[models.Item]:
        items: list[models.Item] = []
        item = {"links": {}}
        for child in dl[0].findChildren(recursive=False):
            if child.name == "dt":
                item["title"] = child.text.strip()
            elif child.name == "dd":
                description = child.text.splitlines()[:2]
                mo = self.re_entry_metadata.search("\n".join(description))
                if not mo:
                    LOG.error("unable to parse (%s)", title)
                    continue

                item["published"] = datetime.datetime.now(datetime.UTC)
                item["updated"] = datetime.datetime.now(datetime.UTC)

                d_created = mo.group("date_created")
                if d_created:
                    item["published"] = datetime.datetime.strptime(
                        d_created, "%m/%d/%y"
                    ).replace(tzinfo=datetime.UTC)

                d_modified = mo.group("date_modified")
                if d_modified:
                    item["updated"] = datetime.datetime.strptime(
                        d_modified, "%m/%d/%y"
                    ).replace(tzinfo=datetime.UTC)

                item["id"] = mo.group("listingid")

                if website := mo.group("website"):
                    item["links"]["website"] = f'<a href="{website}"{website}</a>'

                if contact_url := child.find("a", string="Click to Contact"):
                    item["links"]["contact"] = contact_url["href"]

                if photo_url := child.find("a", string="Click Here to View Picture"):
                    item["links"]["photo"] = photo_url["href"]

                item["description"] = "\n".join(description)

                items.append(models.Item.model_validate(item))

        return items
