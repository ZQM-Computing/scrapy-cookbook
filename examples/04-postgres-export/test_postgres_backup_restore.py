"""Automated PostgreSQL dump/restore smoke test for a disposable test server.

Requires SCRAPY_POSTGRES_DSN, pg_dump, pg_restore, and permission to create/drop
temporary databases on that test server. Never point this test at production.
"""
import hashlib
import os
from pathlib import Path
import shutil
import secrets
import subprocess
import tempfile
import unittest
import uuid

DSN = os.environ.get("SCRAPY_POSTGRES_DSN")


def sha256_file(path):
    """Return the SHA-256 digest of a file's bytes."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_matches(path, manifest_path):
    """Check a GNU sha256sum-style manifest entry against the named file."""
    fields = Path(manifest_path).read_text(encoding="ascii").split()
    if len(fields) != 2 or fields[1] != Path(path).name:
        return False
    expected = fields[0]
    if len(expected) != 64 or any(char not in "0123456789abcdefABCDEF" for char in expected):
        return False
    return expected.lower() == sha256_file(path)


class BackupManifestTests(unittest.TestCase):
    def test_manifest_accepts_original_and_rejects_corruption_or_wrong_filename(self):
        with tempfile.TemporaryDirectory(prefix="scrapy-manifest-test-") as tmp:
            root = Path(tmp)
            backup = root / "catalog.dump"
            manifest = root / "catalog.dump.sha256"
            backup.write_bytes(b"representative backup archive bytes")
            manifest.write_text(f"{sha256_file(backup)}  {backup.name}\n", encoding="ascii")
            self.assertTrue(manifest_matches(backup, manifest))

            corrupted_dir = root / "corrupted"
            corrupted_dir.mkdir()
            corrupted = corrupted_dir / backup.name
            original = backup.read_bytes()
            corrupted.write_bytes(original[:-1] + bytes([original[-1] ^ 0x01]))
            self.assertFalse(manifest_matches(corrupted, manifest))

            wrong_name_manifest = root / "wrong-name.sha256"
            wrong_name_manifest.write_text(
                f"{sha256_file(backup)}  another.dump\n", encoding="ascii"
            )
            self.assertFalse(manifest_matches(backup, wrong_name_manifest))


@unittest.skipUnless(DSN, "set SCRAPY_POSTGRES_DSN to a disposable PostgreSQL test database")
class PostgresBackupRestoreTests(unittest.TestCase):
    def test_custom_dump_restores_data_schema_constraints_and_indexes(self):
        import psycopg
        from psycopg import sql
        from psycopg.conninfo import conninfo_to_dict, make_conninfo

        versioned_client_dir = Path("/usr/lib/postgresql/15/bin")
        pg_dump = str(versioned_client_dir / "pg_dump") if (versioned_client_dir / "pg_dump").is_file() else shutil.which("pg_dump")
        pg_restore = str(versioned_client_dir / "pg_restore") if (versioned_client_dir / "pg_restore").is_file() else shutil.which("pg_restore")
        if pg_dump is None or pg_restore is None:
            self.fail("pg_dump and pg_restore are required for the backup/restore smoke test")

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
        runtime_role = None
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
                with source.cursor() as cursor:
                    cursor.executemany(
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
                        pg_dump, "--format=custom", "--no-owner", "--no-acl",
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

                digest_path.write_text(
                    f"{sha256_file(dump_path)}  {dump_path.name}\n", encoding="ascii"
                )
                self.assertTrue(manifest_matches(dump_path, digest_path))

                # Exercise archive-level rejection as well as checksum
                # detection: a truncated dump must not pass pg_restore's
                # archive-listing preflight. Do not attempt a restore from it.
                truncated_path = Path(tmp) / "truncated.dump"
                truncated_path.write_bytes(dump_path.read_bytes()[: max(1, dump_path.stat().st_size // 2)])
                truncated_check = subprocess.run(
                    [pg_restore, "--list", str(truncated_path)],
                    env=pg_env,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertNotEqual(
                    truncated_check.returncode,
                    0,
                    "pg_restore unexpectedly accepted a deliberately truncated archive",
                )

                # A trusted manifest detects accidental corruption; a sidecar
                # alone does not protect against both files being replaced.
                corrupted_dir = Path(tmp) / "corrupted"
                corrupted_dir.mkdir()
                corrupted_path = corrupted_dir / dump_path.name
                original_bytes = dump_path.read_bytes()
                corrupted_path.write_bytes(
                    original_bytes[:-1] + bytes([original_bytes[-1] ^ 0x01])
                )
                self.assertFalse(manifest_matches(corrupted_path, digest_path))
                subprocess.run(
                    [pg_restore, "--list", str(dump_path)],
                    env=pg_env,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                subprocess.run(
                    [
                        pg_restore, "--exit-on-error", "--no-owner", "--no-acl",
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

                # Ownership and ACLs are deliberately excluded from the dump.
                # Re-provision a least-privilege application role after restore
                # and prove it can write catalog rows but cannot perform DDL.
                runtime_role = "scrapy_restore_" + uuid.uuid4().hex[:10]
                runtime_password = secrets.token_urlsafe(24)
                with psycopg.connect(admin_dsn, autocommit=True) as admin:
                    admin.execute(
                        sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                            sql.Identifier(runtime_role), sql.Literal(runtime_password)
                        )
                    )
                    admin.execute(
                        sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                            sql.Identifier(target_db), sql.Identifier(runtime_role)
                        )
                    )
                with psycopg.connect(target_dsn, autocommit=True) as admin:
                    admin.execute(
                        sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(
                            sql.Identifier(runtime_role)
                        )
                    )
                    admin.execute(
                        sql.SQL("GRANT SELECT, INSERT ON public.scraped_products TO {}").format(
                            sql.Identifier(runtime_role)
                        )
                    )

                runtime_dsn = make_conninfo(
                    target_dsn, user=runtime_role, password=runtime_password
                )
                from scrapy.exceptions import DropItem
                from postgres_pipeline import PostgresExportPipeline

                with psycopg.connect(runtime_dsn, autocommit=True) as runtime:
                    with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                        runtime.execute(
                            "CREATE TABLE public.runtime_role_must_not_ddl (id integer)"
                        )

                # Exercise the real application pipeline, not only a raw SQL
                # insert. Auto-DDL stays disabled to match least-privilege
                # deployments where migrations are applied separately.
                pipeline = PostgresExportPipeline(
                    runtime_dsn, auto_create_table=False
                )
                spider = type(
                    "RestoreSmokeSpider", (), {"name": "restore-runtime-check"}
                )()
                item = {
                    "url": "HTTPS://Example.Test/products/runtime-check#fragment",
                    "title": "Runtime role verification",
                    "price_text": "$1.00",
                    "source_url": "https://example.test/catalogue/",
                    "extracted_at_utc": "2026-10-22T10:00:00Z",
                    "spider_name": spider.name,
                }
                pipeline.open_spider(spider)
                try:
                    self.assertIs(pipeline.process_item(item, spider), item)
                    with self.assertRaisesRegex(DropItem, "duplicate product URL"):
                        pipeline.process_item(
                            {**item, "url": "https://example.test/products/runtime-check"},
                            spider,
                        )
                finally:
                    pipeline.close_spider(spider)

                with psycopg.connect(target_dsn) as restored:
                    runtime_row = restored.execute(
                        "SELECT url, title, spider_name FROM public.scraped_products "
                        "WHERE url = %s",
                        ("https://example.test/products/runtime-check",),
                    ).fetchone()
                self.assertEqual(
                    runtime_row,
                    (
                        "https://example.test/products/runtime-check",
                        "Runtime role verification",
                        "restore-runtime-check",
                    ),
                )
        finally:
            # Remove the temporary role's object grants while its database
            # still exists, then drop databases and the cluster-level role.
            if runtime_role and target_db in created_databases:
                try:
                    with psycopg.connect(target_dsn, autocommit=True) as target_admin:
                        target_admin.execute(
                            sql.SQL("DROP OWNED BY {}").format(sql.Identifier(runtime_role))
                        )
                except Exception:
                    pass
            with psycopg.connect(admin_dsn, autocommit=True) as admin:
                # Database-level privileges must be revoked before the target
                # database is dropped; otherwise PostgreSQL raises
                # InvalidCatalogName and masks the test's actual outcome.
                if runtime_role and target_db in created_databases:
                    admin.execute(
                        sql.SQL("REVOKE CONNECT ON DATABASE {} FROM {}").format(
                            sql.Identifier(target_db), sql.Identifier(runtime_role)
                        )
                    )
                for database in reversed(created_databases):
                    admin.execute(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = %s AND pid <> pg_backend_pid()",
                        (database,),
                    )
                    admin.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(database)))
                if runtime_role:
                    admin.execute(
                        sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(runtime_role))
                    )
