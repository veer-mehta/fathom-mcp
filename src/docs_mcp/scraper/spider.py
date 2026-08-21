import re
from typing import Any, Iterable
from urllib.parse import urldefrag, urlparse, urlunparse

import scrapy
from scrapy.http import Response
from scrapy_playwright.page import PageMethod

NON_PAGE_EXTENSIONS = re.compile(
    r"\.(png|jpe?g|gif|svg|ico|css|js|mjs|map|pdf|zip|gz|tar|rar|7z|mp4|webm|mp3|wav|woff2?|ttf|eot|xml|json|txt|rss|atom)$",
    re.IGNORECASE,
)


def normalize_url(url: str) -> str:
    url, _ = urldefrag(url)
    parsed = urlparse(url)
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


class DocsSpider(scrapy.Spider):
    name = "docs"

    custom_settings = {
        "ROBOTSTXT_OBEY": True,
        "CONCURRENT_REQUESTS": 4,
        "DOWNLOAD_TIMEOUT": 45,
        "RETRY_TIMES": 1,
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
        "DOWNLOAD_HANDLERS": {
            "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
            "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
        },
        "PLAYWRIGHT_BROWSER_TYPE": "chromium",
        "PLAYWRIGHT_LAUNCH_OPTIONS": {"headless": True},
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 30_000,
        "REQUEST_FINGERPRINTER_IMPLEMENTATION": "2.7",
    }

    def __init__(
        self,
        base_url: str,
        max_depth: int = 2,
        max_pages: int = 30,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.base_url = normalize_url(base_url)
        parsed = urlparse(self.base_url)
        self.allowed_domains: set[str] = {parsed.netloc}
        self.base_path = ""
        self.max_depth = int(max_depth)
        self.max_pages = int(max_pages)
        self.seen: set[str] = set()
        self.emitted: set[str] = set()
        self._root_landed = False

    async def start(self) -> AsyncIterator[Any]:
        yield self._request(self.base_url)

    def _request(self, url: str) -> scrapy.Request:
        return scrapy.Request(
            url,
            callback=self.parse_page,
            errback=self.on_error,
            meta={
                "playwright": True,
                "playwright_page_methods": [
                    PageMethod("wait_for_load_state", "networkidle")
                ],
                "download_timeout": 45,
            },
        )

    def parse_page(self, response: Response) -> Iterable[Any]:
        url = normalize_url(response.url)
        parsed = urlparse(url)
        if not self._root_landed:
            self._root_landed = True
            self.allowed_domains.add(parsed.netloc)
            segments = [s for s in parsed.path.split("/") if s]
            if len(segments) > 1:
                self.base_path = "/" + "/".join(segments[:-1])

        if url not in self.emitted:
            self.emitted.add(url)
            title = response.css("title::text").get()
            yield {
                "url": url,
                "title": (title or "").strip() or None,
                "html": response.text,
            }

        if response.meta.get("depth", 0) >= self.max_depth:
            return
        for href in response.css("a::attr(href)").getall():
            if len(self.seen) >= self.max_pages:
                return
            candidate = normalize_url(response.urljoin(href))
            if candidate in self.seen or not self._should_follow(candidate):
                continue
            self.seen.add(candidate)
            yield self._request(candidate)

    def _should_follow(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        if parsed.netloc not in self.allowed_domains:
            return False
        if self.base_path and not (
            parsed.path == self.base_path
            or parsed.path.startswith(self.base_path + "/")
        ):
            return False
        if NON_PAGE_EXTENSIONS.search(parsed.path):
            return False
        return True

    def on_error(self, failure) -> None:
        self.logger.warning(
            "failed to fetch %s: %s", failure.request.url, failure.value
        )
