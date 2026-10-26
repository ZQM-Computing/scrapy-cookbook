"""Optional PostgreSQL sink for validated Scrapy catalog items."""
from datetime import datetime, timezone
import os
from urllib.parse import urlsplit, urlunsplit

from itemadapter import ItemAdapter
from scrapy.exceptions import DropItem


class PostgresExportPipeline:
    """Insert catalog records with per-item transactions and URL idempotency."""

    def __init__(self, dsn, connect_factory=None, auto_create_table=True):
        if not isinstance(dsn, str) or not dsn.strip():
            raise ValueError("SCRAPY_POSTGRES_DSN must be configured")
        self.dsn = dsn
        self.connect_factory = connect_factory
        self.auto_create_table = auto_create_table
        self.connection = None

    @classmethod
    def from_crawler(cls, crawler):
        dsn = crawler.settings.get("SCRAPY_POSTGRES_DSN") or os.environ.get("SCRAPY_POSTGRES_DSN")
        if not dsn:
            raise ValueError("Set SCRAPY_POSTGRES_DSN in Scrapy settings or the environment")
        return cls(dsn, auto_create_table=crawler.settings.getbool("POSTGRES_AUTO_CREATE_TABLE", True))

    def open_spider(self, spider):
        connect = self.connect_factory
        if connect is None:
            try:
                import psycopg
            except ImportError as exc:
                raise RuntimeError("PostgreSQL export requires psycopg 3; install examples/04-postgres-export/requirements.txt") from exc
            connect = psycopg.connect
        self.connection = connect(self.dsn)
        if self.auto_create_table:
            try:
                with self.connection.cursor() as cursor:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS scraped_products (
                            url TEXT PRIMARY KEY,
                            title TEXT NOT NULL,
                            price_text TEXT NOT NULL,
                            source_url TEXT NOT NULL,
                            extracted_at_utc TIMESTAMPTZ NOT NULL,
                            spider_name TEXT NOT NULL,
                            first_seen_utc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                self.connection.commit()
            except Exception:
                self.connection.rollback()
                self.connection.close()
                self.connection = None
                raise

    @staticmethod
    def _canonical_http_url(value, field_name):
        if not isinstance(value, str) or not value or value != value.strip():
            raise DropItem(f"{field_name} must be a non-empty URL string")
        if any(character.isspace() for character in value):
            raise DropItem(f"{field_name} must not contain whitespace")
        try:
            parsed = urlsplit(value)
            port = parsed.port
        except ValueError as exc:
            raise DropItem(f"{field_name} is malformed: {exc}") from exc
        if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname or not parsed.netloc:
            raise DropItem(f"{field_name} must be an absolute HTTP(S) URL")
        if parsed.username is not None or parsed.password is not None:
            raise DropItem(f"{field_name} must not contain embedded credentials")
        if port is not None and not (1 <= port <= 65535):
            raise DropItem(f"{field_name} contains an invalid port")
        return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", parsed.query, ""))

    @staticmethod
    def _record(item):
        adapter = ItemAdapter(item)
        required = ("title", "price_text", "url", "source_url", "extracted_at_utc", "spider_name")
        record = {}
        for field in required:
            value = adapter.get(field)
            if not isinstance(value, str) or not value.strip():
                raise DropItem(f"missing or blank required PostgreSQL field: {field}")
            record[field] = value
        record["url"] = PostgresExportPipeline._canonical_http_url(record["url"], "url")
        record["source_url"] = PostgresExportPipeline._canonical_http_url(record["source_url"], "source_url")
        try:
            timestamp = datetime.fromisoformat(record["extracted_at_utc"].replace("Z", "+00:00"))
        except ValueError as exc:
            raise DropItem("extracted_at_utc must be a valid ISO-8601 timestamp") from exc
        if timestamp.tzinfo is None or timestamp.utcoffset() != timezone.utc.utcoffset(timestamp):
            raise DropItem("extracted_at_utc must include a UTC timezone")
        record["extracted_at_utc"] = timestamp
        return record

    def process_item(self, item, spider):
        if self.connection is None:
            raise RuntimeError("PostgresExportPipeline is not open")
        record = self._record(item)
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO scraped_products
                        (url, title, price_text, source_url, extracted_at_utc, spider_name)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (url) DO NOTHING
                    RETURNING url
                """, (
                    record["url"], record["title"], record["price_text"],
                    record["source_url"], record["extracted_at_utc"], record["spider_name"],
                ))
                inserted = cursor.fetchone()
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        if inserted is None:
            raise DropItem(f"duplicate product URL already stored: {record['url']}")
        return item

    def close_spider(self, spider):
        if self.connection is not None:
            try:
                self.connection.rollback()
            finally:
                self.connection.close()
                self.connection = None
