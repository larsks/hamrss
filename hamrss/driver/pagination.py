"""Shared pagination utilities for drivers."""

import re
from abc import ABC, abstractmethod
from bs4 import BeautifulSoup


class PaginationHandler(ABC):
    """Base class for handling pagination patterns."""

    @abstractmethod
    def get_total_pages(self, html_content: str) -> int:
        """Extract total page count from HTML."""
        pass

    @abstractmethod
    def build_page_url(self, base_url: str, page_num: int) -> str:
        """Build URL for specific page number."""
        pass


class MTCPaginationHandler(PaginationHandler):
    """Pagination handler for MTC Radio style pagination."""

    def get_total_pages(self, html_content: str) -> int:
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            # Look for pagination list
            paging_list = soup.select_one(".CategoryPagination .PagingList")
            if paging_list:
                # Get all page links
                page_links = paging_list.find_all("li")
                max_page = 1

                for li in page_links:
                    link = li.find("a")
                    if link:
                        href = link.get("href")
                        if href and "page=" in href:
                            # Extract page number from URL
                            page_match = re.search(r"page=(\d+)", href)
                            if page_match:
                                page_num = int(page_match.group(1))
                                max_page = max(max_page, page_num)

                return max_page

        except Exception as e:
            print(f"Error getting total pages: {e}")

        return 1

    def build_page_url(self, base_url: str, page_num: int) -> str:
        """Build URL for MTC pagination."""
        if page_num == 1:
            return base_url
        return f"{base_url}?page={page_num}"


class HROPaginationHandler(PaginationHandler):
    """Pagination handler for Ham Radio Outlet style pagination."""

    def get_total_pages(self, page_obj) -> int:
        """Extract total page count from HRO page (using Playwright Page object)."""
        try:
            # Look for text like "of 6" after the select element
            page_info = page_obj.query_selector('select[name="jumpPage"] + span')
            if page_info:
                text = page_info.inner_text().strip()
                # Extract number from text like " of 6"
                match = re.search(r"of (\d+)", text)
                if match:
                    return int(match.group(1))
        except Exception as e:
            print(f"Error getting total pages: {e}")

        return 1

    def build_page_url(self, base_url: str, page_num: int) -> str:
        """HRO uses JavaScript pagination, so this isn't used."""
        return base_url