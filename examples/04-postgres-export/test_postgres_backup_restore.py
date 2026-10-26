"""Automated PostgreSQL dump/restore smoke test for a disposable test server.

Requires SCRAPY_POSTGRES_DSN, pg_dump, pg_restore, and permission to create/drop
temporary databases on that test server. Never point this test at production.
"""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import uuid

DSN = os.environ.get("SCRAPY_POSTGRES_DSN")


@unittest.skipUnless(DSN, "set SCRAPY_POSTGRES_DSN to a disposable PostgreSQL test database")
class PostgresBackupRestoreTests(unittest.TestCase):
    def test_custom_dump_restores_data_schema_constraints_and_indexes(self):
        import psycopg
        from psycopg import sql
        from psycopg.conninfo import conninfo_to_dict, make_conninfo

        for executable in ("pg_dump", "pg_restore"):
            if shutil.which(executable) is None:
                self.fail(f"{executable} is required for the backup/restore smoke test")

        settings = conninfo_to_dict(DSN)
        source_db = "scrapy_backup_src_" + uuid.uuid4().hex[:12]
        target_db = "scrapy_backup_dst_" + uuid.uuid4().hex[:12]
        admin_dsn = make_conninfo(DSN, dbname="postgres")
        source_dsn = make_conninfo(DSN, dbname=source_db)
        target_dsn = make_conninfo(DSN, dbname=target_db)

        # Keep credentials out of subprocess arguments. libpq utilities read
        # connection settings from their environment, like psycopg does.
        pg_env = os.environ.copy()
        env_map = {
            "host": "PGHOST",
            "port": "PGPORT",
            "user": "PGUSER",
            "password": "PGPASSWORD",
            "sslmode": "PGSSLMODE",
            "sslrootcert": "PGSSLROOTCERT",
            "sslcert": "PGSSLCERT",
            "sslkey": "PGSSLKEY",
            "sslcrl": "PGSSLCRL",
            "sslcrldir": "PGSSLCRLDIR",
            "application_name": "PGAPPNAME",
        }
        for key, env_key in env_map.items():
            if settings.get(key):
                pg_env[env_key] = settings[key]

        created_databases = []
        try:
            with psycopg.connect(admin_dsn, autocommit=True) as admin:
                admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(source_db)))
                created_databases.append(source_db)
                admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target_db)))
                created_databases.append(target_db)

            with psycopg.connect(source_dsn) as source:
                source.execute("""
                    CREATE TABLE public.scraped_products (
                        url TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        price_text TEXT NOT NULL,
                        source_url TEXT NOT NULL,
                        extracted_at_utc TIMESTAMPTZ NOT NULL,
                        spider_name TEXT NOT NULL,
                        first_seen_utc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                source.execute(
                    "CREATE INDEX scraped_products_spider_name_idx "
                    "ON public.scraped_products (spider_name)"
                )
                source.executemany(
                    "INSERT INTO public.scraped_products "
                    "(url, title, price_text, source_url, extracted_at_utc, spider_name, first_seen_utc) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    [
                        (
                            "https://example.test/products/1",
                            "Product One",
                            "$12.50",
                            "https://example.test/catalogue/",
                            "2026-10-20T12:30:00Z",
                            "books-spider",
                            "2026-10-19T08:00:00Z",
                        ),
                        (
                            "https://example.test/products/2",
                            "Product Two",
                            "$5.00",
                            "https://example.test/catalogue/",
                            "2026-10-21T15:45:00Z",
                            "books-spider",
                            "2026-10-21T15:00:00Z",
                        ),
                    ],
                )

            with tempfile.TemporaryDirectory(prefix="scrapy-pg-restore-") as tmp:
                dump_path = Path(tmp) / "catalog.dump"
                digest_path = Path(tmp) / "catalog.dump.sha256"
                subprocess.run(
                    [
                        "pg_dump", "--format=custom", "--no-owner", "--no-acl",
                        f"--file={dump_path}", f"--dbname={source_db}",
                    ],
                    env=pg_env,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                self.assertTrue(dump_path.is_file())
                self.assertGreater(dump_path.stat().st_size, 0)

                digest = hashlib.sha256(dump_path.read_bytes()).hexdigest()
                digest_path.write_text(f"{digest}  {dump_path.name}\n", encoding="ascii")
                self.assertEqual(
                    digest,
                    hashlib.sha256(dump_path.read_bytes()).hexdigest(),
                )
                subprocess.run(
                    ["pg_restore", "--list", str(dump_path)],
                    env=pg_env,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                subprocess.run(
                    [
                        "pg_restore", "--exit-on-error", "--no-owner", "--no-acl",
                        f"--dbname={target_db}", str(dump_path),
                    ],
                    env=pg_env,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )

            with psycopg.connect(source_dsn) as source, psycopg.connect(target_dsn) as restored:
                expected_rows = source.execute(
                    "SELECT url, title, price_text, source_url, extracted_at_utc, "
                    "spider_name, first_seen_utc FROM public.scraped_products ORDER BY url"
                ).fetchall()
                actual_rows = restored.execute(
                    "SELECT url, title, price_text, source_url, extracted_at_utc, "
                    "spider_name, first_seen_utc FROM public.scraped_products ORDER BY url"
                ).fetchall()
                self.assertEqual(actual_rows, expected_rows)

                restored_columns = restored.execute(
                    "SELECT column_name, is_nullable FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'scraped_products' "
                    "ORDER BY ordinal_position"
                ).fetchall()
                self.assertEqual(
                    restored_columns,
                    [
                        ("url", "NO"),
                        ("title", "NO"),
                        ("price_text", "NO"),
                        ("source_url", "NO"),
                        ("extracted_at_utc", "NO"),
                        ("spider_name", "NO"),
                        ("first_seen_utc", "NO"),
                    ],
                )
                primary_key = restored.execute(
                    "SELECT count(*) FROM pg_constraint c "
                    "JOIN pg_class t ON t.oid = c.conrelid "
                    "JOIN pg_namespace n ON n.oid = t.relnamespace "
                    "WHERE n.nspname = 'public' AND t.relname = 'scraped_products' "
                    "AND c.contype = 'p'"
                ).fetchone()[0]
                self.assertEqual(primary_key, 1)
                index_exists = restored.execute(
                    "SELECT to_regclass('public.scraped_products_spider_name_idx')"
                ).fetchone()[0]
                self.assertEqual(index_exists, "scraped_products_spider_name_idx")
        finally:
            with psycopg.connect(admin_dsn, autocommit=True) as admin:
                for database in reversed(created_databases):
                    admin.execute(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = %s AND pid <> pg_backend_pid()",
                        (database,),
                    )
                    admin.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(database)))
