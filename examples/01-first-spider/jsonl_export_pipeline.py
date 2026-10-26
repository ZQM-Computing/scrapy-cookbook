"""Idempotent SQLite-backed JSONL snapshot export.

SQLite is the durable staging store. The JSONL file is rebuilt into a temporary
file and atomically replaced only after a complete successful write.
"""
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import tempfile

from itemadapter import ItemAdapter
from scrapy.exceptions import DropItem

from pipeline import ProductValidationPipeline


class SQLiteJsonlExportPipeline:
    """Validate a fixed item schema, deduplicate by canonical URL, export JSONL."""

    schema_version = 1
    exported_fields = (
        "title",
        "price_text",
        "url",
        "source_url",
        "extracted_at_utc",
        "spider_name",
    )

    def __init__(self, database_path, output_path):
        if not database_path or not output_path:
            raise ValueError(
                "SCRAPY_EXPORT_DB and SCRAPY_EXPORT_JSONL_PATH are both required"
            )
        self.database_path = Path(database_path).expanduser()
        self.output_path = Path(output_path).expanduser()
        self.connection = None

    @classmethod
    def from_crawler(cls, crawler):
        database_path = crawler.settings.get("SCRAPY_EXPORT_DB")
        output_path = crawler.settings.get("SCRAPY_EXPORT_JSONL_PATH")
        if not database_path or not output_path:
            raise ValueError(
                "Set SCRAPY_EXPORT_DB and SCRAPY_EXPORT_JSONL_PATH before "
                "enabling SQLiteJsonlExportPipeline"
            )
        return cls(database_path, output_path)

    def open_spider(self, spider):
        if self.database_path.resolve() == self.output_path.resolve():
            raise ValueError("SQLite database path and JSONL output path must differ")
        if self.database_path.exists() and self.database_path.is_dir():
            raise ValueError(f"Export database path is a directory: {self.database_path}")
        if self.output_path.exists() and self.output_path.is_dir():
            raise ValueError(f"JSONL output path is a directory: {self.output_path}")

        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.database_path), timeout=10.0)
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS export_items (
                canonical_url TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                first_seen_utc TEXT NOT NULL
            )
            """
        )
        self.connection.commit()

    @staticmethod
    def _validate_timestamp(value):
        if not isinstance(value, str) or not value.strip():
            raise DropItem("extracted_at_utc must be a non-empty ISO-8601 timestamp")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise DropItem("extracted_at_utc must be a valid ISO-8601 timestamp") from exc
        if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
            raise DropItem("extracted_at_utc must include a UTC timezone")
        return value

    def _record(self, item):
        adapter = ItemAdapter(item)
        record = {}
        for field in self.exported_fields:
            value = adapter.get(field)
            if not isinstance(value, str) or not value.strip():
                raise DropItem(f"missing or blank required export field: {field}")
            record[field] = value

        canonical_url = ProductValidationPipeline._canonical_http_url(
            record["url"], "url"
        )
        ProductValidationPipeline._canonical_http_url(record["source_url"], "source_url")
        self._validate_timestamp(record["extracted_at_utc"])
        return canonical_url, {"schema_version": self.schema_version, **record}

    def process_item(self, item, spider):
        if self.connection is None:
            raise RuntimeError("SQLiteJsonlExportPipeline is not open")
        canonical_url, record = self._record(item)
        payload = json.dumps(
            record, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        try:
            cursor = self.connection.execute(
                """
                INSERT OR IGNORE INTO export_items
                    (canonical_url, payload_json, first_seen_utc)
                VALUES (?, ?, ?)
                """,
                (canonical_url, payload, datetime.now(timezone.utc).isoformat()),
            )
            self.connection.commit()
        except sqlite3.Error:
            self.connection.rollback()
            raise

        if cursor.rowcount == 0:
            raise DropItem(f"duplicate product URL already exported: {canonical_url}")
        return item

    def _write_snapshot(self):
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=str(self.output_path.parent),
                prefix=f".{self.output_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                for (payload,) in self.connection.execute(
                    "SELECT payload_json FROM export_items ORDER BY canonical_url"
                ):
                    handle.write(payload)
                    handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.output_path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

    def close_spider(self, spider):
        if self.connection is None:
            return
        try:
            self._write_snapshot()
        finally:
            self.connection.close()
            self.connection = None
