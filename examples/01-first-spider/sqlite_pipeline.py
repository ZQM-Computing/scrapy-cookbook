"""Persistent, single-host deduplication using Python's standard-library SQLite.

Enable this pipeline instead of ProductValidationPipeline's in-memory duplicate
filter when records must remain deduplicated across crawler restarts. Keep
ProductValidationPipeline enabled first for schema/URL validation.
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from itemadapter import ItemAdapter
from scrapy.exceptions import DropItem

from pipeline import ProductValidationPipeline


class SQLiteDeduplicationPipeline:
    """Persist canonical product URLs in a SQLite database."""

    def __init__(self, database_path):
        if not database_path:
            raise ValueError("SCRAPY_DEDUPE_DB must name a SQLite database file")
        self.database_path = str(database_path)
        self.connection = None

    @classmethod
    def from_crawler(cls, crawler):
        database_path = crawler.settings.get("SCRAPY_DEDUPE_DB")
        if not database_path:
            raise ValueError(
                "Set SCRAPY_DEDUPE_DB to a writable SQLite database path "
                "before enabling SQLiteDeduplicationPipeline"
            )
        return cls(database_path)

    def open_spider(self, spider):
        path = Path(self.database_path).expanduser()
        if path.exists() and path.is_dir():
            raise ValueError(f"Deduplication database path is a directory: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(path), timeout=10.0)
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS seen_products (
                canonical_url TEXT PRIMARY KEY,
                first_seen_utc TEXT NOT NULL,
                first_spider TEXT NOT NULL
            )
            """
        )
        self.connection.commit()

    def process_item(self, item, spider):
        if self.connection is None:
            raise RuntimeError("SQLiteDeduplicationPipeline is not open")
        adapter = ItemAdapter(item)
        raw_url = adapter.get("url")
        canonical_url = ProductValidationPipeline._canonical_http_url(raw_url, "url")
        cursor = self.connection.execute(
            """
            INSERT OR IGNORE INTO seen_products
                (canonical_url, first_seen_utc, first_spider)
            VALUES (?, ?, ?)
            """,
            (
                canonical_url,
                datetime.now(timezone.utc).isoformat(),
                spider.name,
            ),
        )
        self.connection.commit()
        if cursor.rowcount == 0:
            raise DropItem(f"duplicate product URL already persisted: {canonical_url}")
        return item

    def close_spider(self, spider):
        if self.connection is not None:
            self.connection.close()
            self.connection = None
