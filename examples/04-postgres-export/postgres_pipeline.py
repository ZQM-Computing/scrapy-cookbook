"""Optional PostgreSQL sink for validated Scrapy catalog items."""
from datetime import datetime, timezone
import os
from urllib.parse import urlsplit, urlunsplit

from itemadapter import ItemAdapter
from scrapy.exceptions import DropItem


class PostgresExportPipeline:
    """Insert catalog records with per-item transactions and URL idempotency."""

    def __init__(self, dsn, connect_factory=None, auto_create_table=True, connect_timeout=10):
        if not isinstance(dsn, str) or not dsn.strip():
            raise ValueError("SCRAPY_POSTGRES_DSN must be configured")
        if isinstance(connect_timeout, bool) or not isinstance(connect_timeout, int) or connect_timeout < 1:
            raise ValueError("POSTGRES_CONNECT_TIMEOUT must be a positive integer number of seconds")
        self.dsn = dsn
        self.connect_factory = connect_factory
        self.auto_create_table = auto_create_table
        self.connect_timeout = connect_timeout
        self.connection = None

    @classmethod
    def from_crawler(cls, crawler):
        dsn = crawler.settings.get("SCRAPY_POSTGRES_DSN") or os.environ.get("SCRAPY_POSTGRES_DSN")
        if not dsn:
            raise ValueError("Set SCRAPY_POSTGRES_DSN in Scrapy settings or the environment")
        return cls(
            dsn,
            auto_create_table=crawler.settings.getbool("POSTGRES_AUTO_CREATE_TABLE", True),
            connect_timeout=crawler.settings.getint("POSTGRES_CONNECT_TIMEOUT", 10),
        )

    def open_spider(self, spider):
        connect = self.connect_factory
        if connect is None:
            try:
                import psycopg
            except ImportError as exc:
                raise RuntimeError("PostgreSQL export requires psycopg 3; install examples/04-postgres-export/requirements.txt") from exc
            connect = psycopg.connect
        # Bound startup waits when the database host is unreachable. Psycopg
        # accepts connect_timeout as a connection parameter in seconds.
        self.connection = connect(self.dsn, connect_timeout=self.connect_timeout)
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
                # Preserve the schema/bootstrap error even if rollback or close
                # also fails because the database connection is broken.
                try:
                    self.connection.rollback()
                except Exception:
                    pass
                self._close_connection()
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
        commit_started = False
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
            commit_started = True
            self.connection.commit()
        except Exception:
            try:
                self.connection.rollback()
            except Exception:
                # A failed rollback leaves transaction state unknown. Discard
                # the connection and preserve the original database exception.
                self._close_connection()
            else:
                if commit_started:
                    # A commit error can mean the server committed but its
                    # acknowledgement was lost. Never reuse this connection;
                    # do not retry automatically because commit outcome is unknown.
                    self._close_connection()
            raise
        if inserted is None:
            raise DropItem(f"duplicate product URL already stored: {record['url']}")
        return item

    def _close_connection(self):
        """Detach and close the connection without masking an active failure."""
        connection, self.connection = self.connection, None
        if connection is not None:
            try:
                connection.close()
            except Exception:
                # Cleanup is best-effort when handling an earlier database error.
                pass

    def close_spider(self, spider):
        connection, self.connection = self.connection, None
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                # Rollback is the primary shutdown failure. Attempt to close
                # the connection, but never let a secondary close error mask it.
                try:
                    connection.close()
                except Exception:
                    pass
                raise
            else:
                # With no earlier failure, surface a close error to the caller.
                connection.close()
