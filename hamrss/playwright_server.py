"""Playwright browser connection management."""

import time
import socket
import logging
from contextlib import contextmanager
from typing import Generator
from playwright.sync_api import sync_playwright, Browser


class PlaywrightServer:
    """Manages browser connections to a Playwright server."""

    def __init__(self, ws_url: str = "ws://127.0.0.1:3000/"):
        self.ws_url = ws_url
        self.logger = logging.getLogger(__name__)

    def _wait_for_server(self, timeout: int = 30) -> None:
        """Wait for the Playwright server to be ready.

        Args:
            timeout: Maximum time to wait in seconds

        Raises:
            RuntimeError: If the server doesn't become ready within timeout
        """
        # Extract host and port from WebSocket URL
        # ws://127.0.0.1:3000/ -> 127.0.0.1, 3000
        url_parts = self.ws_url.replace("ws://", "").replace("/", "").split(":")
        host = url_parts[0]
        port = int(url_parts[1]) if len(url_parts) > 1 else 3000

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                with socket.create_connection((host, port), timeout=1):
                    # Give the Playwright service extra time to fully initialize
                    time.sleep(3)
                    self.logger.info("Playwright server is ready")
                    return
            except (socket.error, ConnectionRefusedError):
                time.sleep(1)

        raise RuntimeError(
            f"Playwright server at {self.ws_url} did not become ready within {timeout} seconds"
        )

    @contextmanager
    def get_browser(self) -> Generator[Browser, None, None]:
        """Get a browser instance connected to the Playwright server.

        This method will wait for the server to be available,
        create a browser connection, and ensure proper cleanup.

        Yields:
            Browser: A connected browser instance

        Example:
            with server.get_browser() as browser:
                page = browser.new_page()
                # use page...
        """
        # Wait for server to be ready
        self._wait_for_server()

        with sync_playwright() as p:
            browser = p.chromium.connect(self.ws_url)
            try:
                self.logger.info(
                    f"Browser connected to Playwright server at {self.ws_url}"
                )
                yield browser
            finally:
                browser.close()
                self.logger.info("Browser connection closed")
