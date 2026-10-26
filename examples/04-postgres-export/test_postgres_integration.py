"""Live PostgreSQL integration tests; run only with an explicit test DSN."""
import os
import unittest
from datetime import datetime, timezone

from scrapy.exceptions import DropItem

from postgres_pipeline import PostgresExportPipeline


DSN = os.environ.get("SCRAPY_POSTGRES_DSN")


@unittest.skipUnless(DSN, "set SCRAPY_POSTGRES_DSN to run live PostgreSQL integration tests")
class PostgresExportIntegrationTests(unittest.TestCase):
    def setUp(self):
        import psycopg
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
        import psycopg
        self.pipeline.close_spider(self.spider)
        with psycopg.connect(DSN) as connection:
            connection.execute("DROP TABLE IF EXISTS scraped_products")

    def test_least_privilege_role_can_insert_without_schema_ddl(self):
        import psycopg
        from psycopg import sql
        from psycopg.conninfo import make_conninfo

        role = "scrapy_crawler_test"
        role_identifier = sql.Identifier(role)

        def remove_test_role(admin):
            # DROP ROLE refuses while grants remain. DROP OWNED revokes the
            # test role's grants on the disposable database before removal.
            exists = admin.execute(
                "SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)
            ).fetchone()
            if exists:
                admin.execute(sql.SQL("DROP OWNED BY {}").format(role_identifier))
                admin.execute(sql.SQL("DROP ROLE {}").format(role_identifier))

        # This test runs only against the explicitly configured disposable DB.
        # Clean stale state first, and keep setup inside the try so a partial
        # setup failure cannot leak a role into a reused test database.
        with psycopg.connect(DSN, autocommit=True) as admin:
            remove_test_role(admin)

        try:
            with psycopg.connect(DSN, autocommit=True) as admin:
                admin.execute(
                    sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                        role_identifier, sql.Literal("crawler_test_password")
                    )
                )
                admin.execute(
                    sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                        sql.Identifier(admin.info.dbname), role_identifier
                    )
                )
                admin.execute(
                    sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(role_identifier)
                )
                admin.execute(
                    sql.SQL("REVOKE CREATE ON SCHEMA public FROM {}").format(role_identifier)
                )
                admin.execute(
                    sql.SQL(
                        "GRANT INSERT (url, title, price_text, source_url, extracted_at_utc, spider_name), "
                        "SELECT (url) ON scraped_products TO {}"
                    ).format(role_identifier)
                )

            crawler_dsn = make_conninfo(DSN, user=role, password="crawler_test_password")
            with psycopg.connect(crawler_dsn, autocommit=True) as crawler_connection:
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    crawler_connection.execute("CREATE TABLE should_not_be_created (id integer)")

            least_privilege_pipeline = PostgresExportPipeline(
                crawler_dsn, auto_create_table=False
            )
            least_privilege_pipeline.open_spider(self.spider)
            try:
                least_privilege_pipeline.process_item(self.item, self.spider)
            finally:
                least_privilege_pipeline.close_spider(self.spider)

            with psycopg.connect(DSN) as admin:
                row = admin.execute(
                    "SELECT title FROM scraped_products WHERE url = %s",
                    ("https://example.test/products/1",),
                ).fetchone()
            self.assertEqual(row, ("Integration test product",))
        finally:
            with psycopg.connect(DSN, autocommit=True) as admin:
                remove_test_role(admin)

    def test_insert_persists_normalized_values_and_duplicate_is_idempotent(self):
        import psycopg
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
