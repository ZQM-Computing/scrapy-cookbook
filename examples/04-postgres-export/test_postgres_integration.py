"""Live PostgreSQL integration tests; run only with an explicit test DSN."""
import os
from pathlib import Path
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

    def test_initial_migration_creates_schema_and_is_idempotent(self):
        import psycopg

        migration = Path(__file__).with_name("001_create_scraped_products.sql").read_text()
        with psycopg.connect(DSN) as connection:
            # Exercise the checked-in migration from a clean state, then apply
            # it again to verify its documented initial-migration idempotency.
            connection.execute("DROP TABLE IF EXISTS scraped_products")
            connection.execute(migration)
            connection.execute(migration)
            columns = connection.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'scraped_products' "
                "ORDER BY ordinal_position"
            ).fetchall()

        self.assertEqual(
            columns,
            [
                ("url",),
                ("title",),
                ("price_text",),
                ("source_url",),
                ("extracted_at_utc",),
                ("spider_name",),
                ("first_seen_utc",),
            ],
        )

    def test_versioned_migration_preserves_legacy_rows_and_is_idempotent(self):
        import psycopg

        # Model an installation created by the original schema, before
        # first_seen_utc was introduced. Preserve a real row across the upgrade.
        with psycopg.connect(DSN) as connection:
            connection.execute("DROP TABLE IF EXISTS scraped_products")
            connection.execute("""
                CREATE TABLE scraped_products (
                    url TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    price_text TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    extracted_at_utc TIMESTAMPTZ NOT NULL,
                    spider_name TEXT NOT NULL
                )
            """)
            connection.execute(
                "INSERT INTO scraped_products "
                "(url, title, price_text, source_url, extracted_at_utc, spider_name) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    "https://example.test/products/legacy",
                    "Legacy product",
                    "$7.50",
                    "https://example.test/products/",
                    datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc),
                    "legacy-spider",
                ),
            )

        migration = Path(__file__).with_name("002_add_first_seen_utc.sql").read_text()
        with psycopg.connect(DSN) as connection:
            connection.execute(migration)
            connection.execute(migration)
            row = connection.execute(
                "SELECT title, first_seen_utc FROM scraped_products "
                "WHERE url = %s",
                ("https://example.test/products/legacy",),
            ).fetchone()
            nullable = connection.execute(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'scraped_products' "
                "AND column_name = 'first_seen_utc'"
            ).fetchone()

        self.assertEqual(row[0], "Legacy product")
        self.assertIsInstance(row[1], datetime)
        self.assertEqual(row[1].utcoffset(), timezone.utc.utcoffset(row[1]))
        self.assertEqual(nullable, ("NO",))

    def test_versioned_migration_repairs_nullable_first_seen_column(self):
        import psycopg

        # A partially/manual-upgraded schema may already have the column but
        # leave it nullable and without a default. IF NOT EXISTS alone would
        # silently preserve that incompatible contract.
        with psycopg.connect(DSN) as connection:
            connection.execute("DROP TABLE IF EXISTS scraped_products")
            connection.execute("""
                CREATE TABLE scraped_products (
                    url TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    price_text TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    extracted_at_utc TIMESTAMPTZ NOT NULL,
                    spider_name TEXT NOT NULL,
                    first_seen_utc TIMESTAMPTZ NULL
                )
            """)
            connection.execute(
                "INSERT INTO scraped_products "
                "(url, title, price_text, source_url, extracted_at_utc, spider_name, first_seen_utc) "
                "VALUES (%s, %s, %s, %s, %s, %s, NULL)",
                (
                    "https://example.test/products/partial-migration",
                    "Partial migration row",
                    "$3.00",
                    "https://example.test/products/",
                    datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc),
                    "migration-test",
                ),
            )

        migration = Path(__file__).with_name("002_add_first_seen_utc.sql").read_text()
        with psycopg.connect(DSN) as connection:
            connection.execute(migration)
            connection.execute(migration)
            row = connection.execute(
                "SELECT first_seen_utc FROM scraped_products WHERE url = %s",
                ("https://example.test/products/partial-migration",),
            ).fetchone()
            metadata = connection.execute(
                "SELECT is_nullable, column_default, data_type "
                "FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'scraped_products' "
                "AND column_name = 'first_seen_utc'"
            ).fetchone()

        self.assertIsInstance(row[0], datetime)
        self.assertEqual(row[0].utcoffset(), timezone.utc.utcoffset(row[0]))
        self.assertEqual(metadata[0], "NO")
        self.assertIn("CURRENT_TIMESTAMP", metadata[1])
        self.assertEqual(metadata[2], "timestamp with time zone")

    def test_failed_insert_rolls_back_and_pipeline_can_continue(self):
        import psycopg

        # Force a database-side constraint violation after item validation so
        # this exercises PostgreSQL transaction rollback, not DropItem checks.
        with psycopg.connect(DSN) as connection:
            connection.execute(
                "ALTER TABLE scraped_products "
                "ADD CONSTRAINT reject_forced_failure CHECK (title <> 'force-database-error')"
            )

        failed_item = {
            **self.item,
            "title": "force-database-error",
            "url": "https://example.test/products/failed",
        }
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.pipeline.process_item(failed_item, self.spider)

        # A valid write immediately afterward proves rollback restored a usable
        # transaction on the same connection.
        valid_item = {
            **self.item,
            "url": "https://example.test/products/after-failure",
        }
        self.pipeline.process_item(valid_item, self.spider)

        with psycopg.connect(DSN) as connection:
            rows = connection.execute(
                "SELECT url FROM scraped_products ORDER BY url"
            ).fetchall()
        self.assertEqual(rows, [("https://example.test/products/after-failure",)])

    def test_terminated_backend_discards_broken_connection_and_new_pipeline_recovers(self):
        import psycopg

        # Terminate this pipeline's server session from a separate connection.
        # This is a deterministic integration test of a lost PostgreSQL session,
        # not a simulation of every possible network partition or lost COMMIT ACK.
        backend_pid = self.pipeline.connection.info.backend_pid
        with psycopg.connect(DSN, autocommit=True) as admin:
            terminated = admin.execute(
                "SELECT pg_terminate_backend(%s)", (backend_pid,)
            ).fetchone()[0]
        self.assertTrue(terminated)

        interrupted_item = {
            **self.item,
            "url": "https://example.test/products/connection-terminated",
        }
        with self.assertRaises(psycopg.Error):
            self.pipeline.process_item(interrupted_item, self.spider)

        # A failed rollback after backend termination must detach the dead
        # connection. The pipeline must not continue using it or retry the item.
        self.assertIsNone(self.pipeline.connection)

        with psycopg.connect(DSN) as connection:
            count = connection.execute(
                "SELECT count(*) FROM scraped_products WHERE url = %s",
                (interrupted_item["url"],),
            ).fetchone()[0]
        self.assertEqual(count, 0)

        # Recovery is explicit: construct a new pipeline/connection and submit
        # a distinct item. No automatic retry of the interrupted item occurs.
        recovered_pipeline = PostgresExportPipeline(DSN)
        recovered_spider = type("RecoverySpider", (), {"name": "recovery-test"})()
        recovered_pipeline.open_spider(recovered_spider)
        recovered_item = {
            **self.item,
            "url": "https://example.test/products/after-session-recovery",
            "spider_name": recovered_spider.name,
        }
        try:
            self.assertIs(
                recovered_pipeline.process_item(recovered_item, recovered_spider),
                recovered_item,
            )
        finally:
            recovered_pipeline.close_spider(recovered_spider)

        with psycopg.connect(DSN) as connection:
            row = connection.execute(
                "SELECT title, spider_name FROM scraped_products WHERE url = %s",
                (recovered_item["url"],),
            ).fetchone()
        self.assertEqual(row, ("Integration test product", "recovery-test"))

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


    def test_failed_versioned_migration_rolls_back_and_can_be_retried(self):
        import psycopg

        # Model a transient migration failure after the migration has begun
        # modifying the schema: a trigger rejects the backfill UPDATE. The
        # whole migration must roll back, leaving the pre-migration schema and
        # row intact so an operator can correct the cause and retry safely.
        legacy_url = "https://example.test/products/migration-retry"
        with psycopg.connect(DSN) as connection:
            connection.execute("DROP TABLE IF EXISTS scraped_products")
            connection.execute("DROP FUNCTION IF EXISTS reject_first_seen_backfill() CASCADE")
            connection.execute("""
                CREATE TABLE scraped_products (
                    url TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    price_text TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    extracted_at_utc TIMESTAMPTZ NOT NULL,
                    spider_name TEXT NOT NULL,
                    first_seen_utc TIMESTAMPTZ NULL
                )
            """)
            connection.execute(
                "INSERT INTO scraped_products "
                "(url, title, price_text, source_url, extracted_at_utc, spider_name, first_seen_utc) "
                "VALUES (%s, %s, %s, %s, %s, %s, NULL)",
                (
                    legacy_url,
                    "Migration retry row",
                    "$4.00",
                    "https://example.test/products/",
                    datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc),
                    "migration-retry-test",
                ),
            )
            connection.execute("""
                CREATE FUNCTION reject_first_seen_backfill() RETURNS trigger
                LANGUAGE plpgsql AS $$
                BEGIN
                    RAISE EXCEPTION 'simulated temporary backfill failure';
                END;
                $$
            """)
            connection.execute("""
                CREATE TRIGGER reject_first_seen_backfill
                BEFORE UPDATE OF first_seen_utc ON scraped_products
                FOR EACH ROW EXECUTE FUNCTION reject_first_seen_backfill()
            """)

        migration = Path(__file__).with_name("002_add_first_seen_utc.sql").read_text()
        with psycopg.connect(DSN) as connection:
            with self.assertRaisesRegex(psycopg.Error, "simulated temporary backfill failure"):
                connection.execute(migration)
            connection.rollback()

        # The failed migration must not leave a partially enforced schema.
        with psycopg.connect(DSN) as connection:
            metadata = connection.execute(
                "SELECT is_nullable, column_default FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'scraped_products' "
                "AND column_name = 'first_seen_utc'"
            ).fetchone()
            row = connection.execute(
                "SELECT first_seen_utc FROM scraped_products WHERE url = %s",
                (legacy_url,),
            ).fetchone()
            self.assertEqual(metadata[0], "YES")
            self.assertIsNone(metadata[1])
            self.assertEqual(row, (None,))
            connection.execute("DROP TRIGGER reject_first_seen_backfill ON scraped_products")
            connection.execute("DROP FUNCTION reject_first_seen_backfill()")

        # After removing the transient failure, retry twice and verify the
        # migration converges to its intended schema without losing the row.
        with psycopg.connect(DSN) as connection:
            connection.execute(migration)
            connection.execute(migration)
            metadata = connection.execute(
                "SELECT is_nullable, column_default FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'scraped_products' "
                "AND column_name = 'first_seen_utc'"
            ).fetchone()
            row = connection.execute(
                "SELECT title, first_seen_utc FROM scraped_products WHERE url = %s",
                (legacy_url,),
            ).fetchone()

        self.assertEqual(metadata[0], "NO")
        self.assertIn("CURRENT_TIMESTAMP", metadata[1])
        self.assertEqual(row[0], "Migration retry row")
        self.assertIsInstance(row[1], datetime)
        self.assertEqual(row[1].utcoffset(), timezone.utc.utcoffset(row[1]))


if __name__ == "__main__":
    unittest.main()
