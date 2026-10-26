"""Validate scraped catalog items and drop duplicate product URLs.

This in-memory example is intentionally scoped to one spider run. It is not
persistent deduplication across restarts or distributed crawler workers.
"""
from urllib.parse import urlsplit, urlunsplit

from scrapy.exceptions import DropItem


class ProductValidationPipeline:
    """Fail closed on missing fields, malformed URLs, and duplicate products."""

    required_text_fields = ("title", "price_text", "url", "source_url")

    def __init__(self, deduplicate=True):
        self.deduplicate = deduplicate
        self.seen_urls = set()

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            deduplicate=crawler.settings.getbool("PRODUCT_DEDUPE_IN_MEMORY", True)
        )

    @staticmethod
    def _canonical_http_url(value, field_name):
        if not isinstance(value, str) or not value or value != value.strip():
            raise DropItem(f"{field_name} must be a non-empty URL string")
        if any(character.isspace() for character in value):
            raise DropItem(f"{field_name} must not contain whitespace")

        try:
            parsed = urlsplit(value)
            # Accessing .port validates malformed/out-of-range port values.
            port = parsed.port
        except ValueError as exc:
            raise DropItem(f"{field_name} is malformed: {exc}") from exc

        if parsed.scheme.lower() not in ("http", "https"):
            raise DropItem(f"{field_name} must use HTTP or HTTPS")
        if not parsed.hostname or not parsed.netloc:
            raise DropItem(f"{field_name} must include a hostname")
        if parsed.username is not None or parsed.password is not None:
            raise DropItem(f"{field_name} must not contain embedded credentials")
        if port is not None and not (1 <= port <= 65535):
            raise DropItem(f"{field_name} contains an invalid port")

        # Normalize only URL components that are safely equivalent here:
        # scheme/host casing and fragments. Preserve path and query semantics.
        netloc = parsed.netloc.lower()
        path = parsed.path or "/"
        return urlunsplit((parsed.scheme.lower(), netloc, path, parsed.query, ""))

    def process_item(self, item, spider):
        for field in self.required_text_fields:
            value = item.get(field)
            if not isinstance(value, str) or not value.strip():
                raise DropItem(f"missing or blank required field: {field}")

        product_url = self._canonical_http_url(item["url"], "url")
        self._canonical_http_url(item["source_url"], "source_url")

        if self.deduplicate:
            if product_url in self.seen_urls:
                raise DropItem(f"duplicate product URL: {product_url}")
            self.seen_urls.add(product_url)
        return item
