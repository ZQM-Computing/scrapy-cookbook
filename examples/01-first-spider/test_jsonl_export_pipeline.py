import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scrapy.exceptions import DropItem

import jsonl_export_pipeline
from jsonl_export_pipeline import SQLiteJsonlExportPipeline


class FakeSpider:
    name = "test-spider"


class SQLiteJsonlExportPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.database_path = root / "state" / "items.sqlite3"
        self.output_path = root / "exports" / "items.jsonl"
        self.spider = FakeSpider()
        self.item = {
            "title": "A Sample Book",
            "price_text": "£12.34",
            "url": "https://books.toscrape.com/catalogue/sample.html#details",
            "source_url": "https://books.toscrape.com/catalogue/category/books_1/index.html",
            "extracted_at_utc": "2026-10-26T12:30:00+00:00",
            "spider_name": "catalog",
            "unexpected_sensitive_field": "must not be exported",
        }
        self.pipeline = SQLiteJsonlExportPipeline(self.database_path, self.output_path)
        self.pipeline.open_spider(self.spider)

    def tearDown(self):
        if self.pipeline.connection is not None:
            self.pipeline.close_spider(self.spider)
        self.temp_dir.cleanup()

    def test_exports_allowlisted_schema_and_deterministic_jsonl_snapshot(self):
        self.pipeline.process_item(self.item, self.spider)
        self.pipeline.process_item({
            **self.item,
            "title": "Another Book",
            "url": "https://books.toscrape.com/catalogue/another.html",
        }, self.spider)
        self.pipeline.close_spider(self.spider)

        lines = self.output_path.read_text(encoding="utf-8").splitlines()
        records = [json.loads(line) for line in lines]
        self.assertEqual(len(records), 2)
        self.assertEqual([r["url"] for r in records], sorted(r["url"] for r in records))
        self.assertEqual(records[0]["schema_version"], 1)
        self.assertEqual(set(records[0]), {
            "schema_version", "title", "price_text", "url", "source_url",
            "extracted_at_utc", "spider_name",
        })
        self.assertNotIn("unexpected_sensitive_field", records[0])
        self.assertEqual(records[1]["url"], self.item["url"])

    def test_duplicate_is_idempotently_rejected_after_restart(self):
        self.pipeline.process_item(self.item, self.spider)
        self.pipeline.close_spider(self.spider)
        restarted = SQLiteJsonlExportPipeline(self.database_path, self.output_path)
        restarted.open_spider(self.spider)
        try:
            with self.assertRaisesRegex(DropItem, "duplicate product URL already exported"):
                restarted.process_item({**self.item, "url": self.item["url"].split("#")[0]}, self.spider)
            restarted.close_spider(self.spider)
        finally:
            if restarted.connection is not None:
                restarted.close_spider(self.spider)
        self.assertEqual(len(self.output_path.read_text(encoding="utf-8").splitlines()), 1)

    def test_rejects_missing_or_non_utc_timestamp_before_database_write(self):
        with self.assertRaisesRegex(DropItem, "must include a UTC timezone"):
            self.pipeline.process_item(
                {**self.item, "extracted_at_utc": "2026-10-26T12:30:00"},
                self.spider,
            )
        count = self.pipeline.connection.execute(
            "SELECT COUNT(*) FROM export_items"
        ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_snapshot_failure_preserves_previous_output_and_cleans_temp_file(self):
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text('{"previous":"snapshot"}\n', encoding="utf-8")
        self.pipeline.process_item(self.item, self.spider)
        with patch.object(jsonl_export_pipeline.os, "replace", side_effect=OSError("simulated replace failure")):
            with self.assertRaisesRegex(OSError, "simulated replace failure"):
                self.pipeline.close_spider(self.spider)
        self.assertEqual(
            self.output_path.read_text(encoding="utf-8"),
            '{"previous":"snapshot"}\n',
        )
        self.assertEqual(list(self.output_path.parent.glob("*.tmp")), [])
        # The committed staging record remains available for a later retry.
        connection = sqlite3.connect(self.database_path)
        try:
            count = connection.execute("SELECT COUNT(*) FROM export_items").fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
