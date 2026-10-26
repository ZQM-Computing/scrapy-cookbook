import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

from scrapy.exceptions import DropItem

from postgres_pipeline import PostgresExportPipeline


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.result = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        normalized = " ".join(query.split())
        self.connection.queries.append((normalized, params))
        if normalized.startswith("CREATE TABLE"):
            if self.connection.fail_create_table:
                raise RuntimeError("simulated schema creation failure")
            return
        if self.connection.fail_insert:
            raise RuntimeError("simulated database failure")
        url = params[0]
        if url in self.connection.committed_urls or url in self.connection.pending_urls:
            self.result = None
        else:
            self.connection.pending_urls.add(url)
            self.result = (url,)

    def fetchone(self):
        return self.result


class FakeConnection:
    def __init__(self):
        self.queries = []
        self.committed_urls = set()
        self.pending_urls = set()
        self.fail_insert = False
        self.fail_create_table = False
        self.fail_rollback = False
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.committed_urls.update(self.pending_urls)
        self.pending_urls.clear()
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1
        if self.fail_rollback:
            raise RuntimeError("simulated rollback failure")
        self.pending_urls.clear()

    def close(self):
        self.closed = True


class FakeSpider:
    name = "catalog"


class PostgresExportPipelineTests(unittest.TestCase):
    def setUp(self):
        self.connection = FakeConnection()
        self.connector = Mock(return_value=self.connection)
        self.pipeline = PostgresExportPipeline("postgresql://example/test", self.connector)
        self.spider = FakeSpider()
        self.item = {
            "title": "Sample Book",
            "price_text": "£12.34",
            "url": "HTTPS://Books.Example/catalogue/sample.html#details",
            "source_url": "https://books.example/catalogue/",
            "extracted_at_utc": "2026-10-26T12:30:00Z",
            "spider_name": "catalog",
            "extra_field": "must not be inserted",
        }
        self.pipeline.open_spider(self.spider)

    def tearDown(self):
        self.pipeline.close_spider(self.spider)

    def test_connection_uses_bounded_timeout(self):
        self.connector.assert_called_once_with(
            "postgresql://example/test",
            connect_timeout=10,
        )

    def test_custom_connection_timeout_is_passed_to_connector(self):
        connection = FakeConnection()
        connector = Mock(return_value=connection)
        pipeline = PostgresExportPipeline(
            "postgresql://example/test",
            connect_factory=connector,
            auto_create_table=False,
            connect_timeout=3,
        )
        pipeline.open_spider(self.spider)
        try:
            connector.assert_called_once_with(
                "postgresql://example/test",
                connect_timeout=3,
            )
        finally:
            pipeline.close_spider(self.spider)

    def test_connection_timeout_must_be_positive_integer(self):
        for value in (0, -1, 1.5, True, "10"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "POSTGRES_CONNECT_TIMEOUT"):
                    PostgresExportPipeline(
                        "postgresql://example/test",
                        connect_timeout=value,
                    )

    def test_bootstraps_schema_and_uses_parameterized_idempotent_insert(self):
        self.pipeline.process_item(self.item, self.spider)
        insert_query, params = self.connection.queries[-1]
        self.assertIn("ON CONFLICT (url) DO NOTHING RETURNING url", insert_query)
        self.assertEqual(params[0], "https://books.example/catalogue/sample.html")
        self.assertEqual(params[1], "Sample Book")
        self.assertIsInstance(params[4], datetime)
        self.assertEqual(params[4].utcoffset(), timezone.utc.utcoffset(params[4]))
        self.assertEqual(len(params), 6)
        self.assertEqual(self.connection.commits, 2)  # schema + item
        self.assertIn(params[0], self.connection.committed_urls)

    def test_least_privilege_mode_skips_schema_ddl(self):
        connection = FakeConnection()
        pipeline = PostgresExportPipeline(
            "postgresql://example/test",
            connect_factory=Mock(return_value=connection),
            auto_create_table=False,
        )
        pipeline.open_spider(self.spider)
        try:
            self.assertFalse(any(query.startswith("CREATE TABLE") for query, _ in connection.queries))
            pipeline.process_item(self.item, self.spider)
            self.assertEqual(connection.commits, 1)
            self.assertTrue(any(query.startswith("INSERT INTO scraped_products") for query, _ in connection.queries))
        finally:
            pipeline.close_spider(self.spider)
        self.assertTrue(connection.closed)

    def test_duplicate_raises_dropitem_without_second_insert(self):
        self.pipeline.process_item(self.item, self.spider)
        with self.assertRaisesRegex(DropItem, "duplicate product URL"):
            self.pipeline.process_item({**self.item, "url": self.item["url"].split("#")[0]}, self.spider)
        self.assertEqual(self.connection.commits, 3)  # schema + first insert + duplicate no-op

    def test_database_failure_rolls_back_and_propagates(self):
        self.connection.fail_insert = True
        with self.assertRaisesRegex(RuntimeError, "simulated database failure"):
            self.pipeline.process_item(self.item, self.spider)
        self.assertEqual(self.connection.rollbacks, 1)
        self.assertEqual(self.connection.committed_urls, set())

    def test_rollback_failure_preserves_insert_error_and_discards_connection(self):
        self.connection.fail_insert = True
        self.connection.fail_rollback = True
        with self.assertRaisesRegex(RuntimeError, "simulated database failure"):
            self.pipeline.process_item(self.item, self.spider)
        self.assertTrue(self.connection.closed)
        self.assertIsNone(self.pipeline.connection)

    def test_schema_failure_with_rollback_failure_still_closes_connection(self):
        connection = FakeConnection()
        connection.fail_create_table = True
        connection.fail_rollback = True
        pipeline = PostgresExportPipeline(
            "postgresql://example/test",
            connect_factory=Mock(return_value=connection),
        )
        with self.assertRaisesRegex(RuntimeError, "simulated schema creation failure"):
            pipeline.open_spider(self.spider)
        self.assertTrue(connection.closed)
        self.assertIsNone(pipeline.connection)

    def test_invalid_record_is_rejected_before_database_write(self):
        before = len(self.connection.queries)
        with self.assertRaisesRegex(DropItem, "must include a UTC timezone"):
            self.pipeline.process_item({**self.item, "extracted_at_utc": "2026-10-26T12:30:00"}, self.spider)
        self.assertEqual(len(self.connection.queries), before)

    def test_close_releases_connection(self):
        self.pipeline.close_spider(self.spider)
        self.assertTrue(self.connection.closed)
        self.assertIsNone(self.pipeline.connection)

    def test_missing_dsn_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "SCRAPY_POSTGRES_DSN"):
            PostgresExportPipeline("")


if __name__ == "__main__":
    unittest.main()
