import sqlite3
import tempfile
import unittest
from pathlib import Path

from scrapy.exceptions import DropItem

from sqlite_pipeline import SQLiteDeduplicationPipeline


class FakeSpider:
    name = "test-spider"


class SQLiteDeduplicationPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "state" / "seen.sqlite3"
        self.spider = FakeSpider()
        self.item = {
            "title": "A Sample Book",
            "price_text": "£12.34",
            "url": "https://books.toscrape.com/catalogue/sample.html",
            "source_url": "https://books.toscrape.com/catalogue/category/books_1/index.html",
        }
        self.pipeline = SQLiteDeduplicationPipeline(self.database_path)
        self.pipeline.open_spider(self.spider)

    def tearDown(self):
        if self.pipeline.connection is not None:
            self.pipeline.close_spider(self.spider)
        self.temp_dir.cleanup()

    def test_accepts_first_item_and_persists_canonical_url(self):
        self.assertIs(self.pipeline.process_item(self.item, self.spider), self.item)
        row = self.pipeline.connection.execute(
            "SELECT canonical_url, first_spider FROM seen_products"
        ).fetchone()
        self.assertEqual(
            row,
            ("https://books.toscrape.com/catalogue/sample.html", "test-spider"),
        )

    def test_rejects_duplicate_in_same_run(self):
        self.pipeline.process_item(self.item, self.spider)
        with self.assertRaisesRegex(DropItem, "already persisted"):
            self.pipeline.process_item(
                {**self.item, "url": self.item["url"] + "#fragment"}, self.spider
            )

    def test_rejects_duplicate_after_pipeline_restart(self):
        self.pipeline.process_item(self.item, self.spider)
        self.pipeline.close_spider(self.spider)

        restarted = SQLiteDeduplicationPipeline(self.database_path)
        restarted.open_spider(self.spider)
        try:
            with self.assertRaisesRegex(DropItem, "already persisted"):
                restarted.process_item(
                    {
                        **self.item,
                        "url": "HTTPS://BOOKS.TOSCRAPE.COM/catalogue/sample.html",
                    },
                    self.spider,
                )
        finally:
            restarted.close_spider(self.spider)

    def test_query_strings_remain_distinct(self):
        self.pipeline.process_item(self.item, self.spider)
        second = {
            **self.item,
            "url": self.item["url"] + "?edition=2",
        }
        self.assertIs(self.pipeline.process_item(second, self.spider), second)

    def test_refuses_directory_as_database_path(self):
        pipeline = SQLiteDeduplicationPipeline(self.temp_dir.name)
        with self.assertRaisesRegex(ValueError, "is a directory"):
            pipeline.open_spider(self.spider)

    def test_database_can_be_reopened_and_records_survive(self):
        self.pipeline.process_item(self.item, self.spider)
        self.pipeline.close_spider(self.spider)
        with sqlite3.connect(self.database_path) as connection:
            count = connection.execute("SELECT COUNT(*) FROM seen_products").fetchone()[0]
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
