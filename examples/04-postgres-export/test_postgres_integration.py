"""Live PostgreSQL integration tests; run only with an explicit test DSN."""
import os
import unittest
from datetime import datetime, timezone

import psycopg
from scrapy.exceptions import DropItem

from postgres_pipeline import PostgresExportPipeline


DSN = os.environ.get("SCRAPY_POSTGRES_DSN")


@unittest.skipUnless(DSN, "set SCRAPY_POSTGRES_DSN to run live PostgreSQL integration tests")
class PostgresExportIntegrationTests(unittest.TestCase):
    def setUp(self):
        # CI provides a disposable PostgreSQL service dedicated to this job.
        with psycopg.connect(DSN) as connection:
            connection.execute("DROP TABLE IF EXISTS scraped_products")
        self.pipeline = PostgresExportPipeline(DSN)
        self.spider = type("Spider", (), {"name": "integration-test"})()
        self.pipeline.open_spider(self.spider)
        self.item = {
            "title": "Integration test product",
            "price_text": "$19.95",
            "url": "HTTPS://Example.Test/products/1#details",
            "source_url": "https://example.test/products/",
            "extracted_at_utc": "2026-10-26T12:30:00Z",
            "spider_name": "integration-test",
        }

    def tearDown(self):
        self.pipeline.close_spider(self.spider)
        with psycopg.connect(DSN) as connection:
            connection.execute("DROP TABLE IF EXISTS scraped_products")

    def test_insert_persists_normalized_values_and_duplicate_is_idempotent(self):
        self.pipeline.process_item(self.item, self.spider)
        with self.assertRaisesRegex(DropItem, "duplicate product URL"):
            self.pipeline.process_item(
                {**self.item, "url": "https://example.test/products/1"},
                self.spider,
            )

        with psycopg.connect(DSN) as connection:
            row = connection.execute(
                "SELECT url, title, price_text, source_url, extracted_at_utc, spider_name "
                "FROM scraped_products"
            ).fetchone()
            count = connection.execute(
                "SELECT count(*) FROM scraped_products"
            ).fetchone()[0]

        self.assertEqual(count, 1)
        self.assertEqual(row[0], "https://example.test/products/1")
        self.assertEqual(row[1:4], (
            "Integration test product",
            "$19.95",
            "https://example.test/products/",
        ))
        self.assertIsInstance(row[4], datetime)
        self.assertEqual(row[4].utcoffset(), timezone.utc.utcoffset(row[4]))
        self.assertEqual(row[5], "integration-test")


if __name__ == "__main__":
    unittest.main()
