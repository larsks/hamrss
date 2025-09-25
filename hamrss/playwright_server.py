"""Playwright server management using Podman containers."""

import subprocess
import time
import logging
from typing import Optional


class PlaywrightServer:
    """Manages a Playwright server running in a Podman container."""

    def __init__(self, port: int = 3000):
        self.port = port
        self.container_id: Optional[str] = None
        self.logger = logging.getLogger(__name__)

    def start(self) -> str:
        """Start the Playwright server container.

        Returns:
            str: Container ID of the started container

        Raises:
            RuntimeError: If the container fails to start
        """
        if self.container_id:
            self.logger.warning("Server is already running")
            return self.container_id

        cmd = [
            "podman",
            "run",
            "-p",
            f"127.0.0.1:{self.port}:3000",
            "--rm",
            "--init",
            "-d",
            "--workdir",
            "/home/pwuser",
            "--user",
            "pwuser",
            "mcr.microsoft.com/playwright:v1.54.0-noble",
            "/bin/sh",
            "-c",
            f"npx -y playwright@1.54.0 run-server --port 3000 --host 0.0.0.0",
        ]

        try:
            self.logger.info("Starting Playwright server container...")
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            self.container_id = result.stdout.strip()

            # Wait for the server to be ready
            self._wait_for_server()

            self.logger.info(
                f"Playwright server started with container ID: {self.container_id}"
            )
            return self.container_id

        except subprocess.CalledProcessError as e:
            error_msg = f"Failed to start Playwright server: {e.stderr}"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def stop(self) -> None:
        """Stop the Playwright server container."""
        if not self.container_id:
            self.logger.warning("No server is running")
            return

        try:
            self.logger.info(
                f"Stopping Playwright server container: {self.container_id}"
            )
            subprocess.run(
                ["podman", "stop", self.container_id],
                capture_output=True,
                text=True,
                check=True,
            )
            self.logger.info("Playwright server stopped successfully")

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to stop container: {e.stderr}")

        finally:
            self.container_id = None

    def _wait_for_server(self, timeout: int = 30) -> None:
        """Wait for the Playwright server to be ready.

        Args:
            timeout: Maximum time to wait in seconds

        Raises:
            RuntimeError: If the server doesn't become ready within timeout
        """
        import socket

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=1):
                    # Give the Playwright service extra time to fully initialize
                    time.sleep(3)
                    self.logger.info("Playwright server is ready")
                    return
            except (socket.error, ConnectionRefusedError):
                time.sleep(1)

        raise RuntimeError(
            f"Playwright server did not become ready within {timeout} seconds"
        )

    def is_running(self) -> bool:
        """Check if the Playwright server container is running.

        Returns:
            bool: True if the server is running, False otherwise
        """
        if not self.container_id:
            return False

        try:
            result = subprocess.run(
                ["podman", "ps", "-q", "--filter", f"id={self.container_id}"],
                capture_output=True,
                text=True,
                check=True,
            )
            return bool(result.stdout.strip())

        except subprocess.CalledProcessError:
            return False

    def get_ws_url(self) -> str:
        """Get the WebSocket URL for connecting to the Playwright server.

        Returns:
            str: WebSocket URL
        """
        return f"ws://127.0.0.1:{self.port}/"

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        self.stop()

    def __del__(self):
        """Cleanup when object is garbage collected."""
        if self.container_id:
            self.stop()
