import importlib
import requests_cache
import jinja2

from flask import Flask, Response

from .driver.base import BaseDriver


class Feed:
    driver: BaseDriver
    session: requests_cache.CachedSession
    driver_name: str
    env: jinja2.Environment
    prefix: str

    def __init__(
        self, session: requests_cache.CachedSession, prefix: str, driver_name: str
    ):
        self.session = session
        self.prefix = prefix
        self.driver_name = driver_name
        self.env = jinja2.Environment(
            loader=jinja2.PackageLoader(__name__.split(".")[0])
        )

        module_name, class_name = driver_name.rsplit(".", 1)
        module = importlib.import_module(module_name)
        driver_class = getattr(module, class_name)
        self.driver = driver_class(session)

    def channels(self) -> Response:
        template = self.env.get_template("channels.html")
        channels = self.driver.channels()
        content = template.render(prefix=self.prefix, channels=channels)
        breakpoint()
        return Response(content, mimetype="text/html")
