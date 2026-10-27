# Pattern 04 — PostgreSQL export

An optional database sink for the catalog spider. It is separate from the default offline example and does not require a database for the normal unit-test suite.

## Prerequisites

- Python 3.11+
- PostgreSQL 15+
- psycopg 3, pinned in this pattern's requirements file
- A database and role provisioned outside the crawler

Install dependencies:

```sh
python -m pip install -r examples/04-postgres-export/requirements.txt
```

Set `SCRAPY_POSTGRES_DSN` in the process environment or Scrapy settings. Prefer a secret manager or deployment environment injection; do not commit DSNs, passwords, certificates, or production credentials. Connection establishment is bounded to 10 seconds by default; configure `POSTGRES_CONNECT_TIMEOUT` as a positive integer number of seconds when a different startup limit is appropriate. Use TLS with certificate verification for remote databases and a least-privilege role. For example, set `sslmode=verify-full` in the DSN and configure the trusted root certificate through `sslrootcert` or your deployment's libpq-compatible environment.

## Configure the spider

The example spider imports `pipeline.py` from its own directory. Run the example with the PostgreSQL pattern directory on Python's import path, or copy the pipeline module into the project package. In a project package, configure the pipeline alongside provenance and validation:

```python
"ITEM_PIPELINES": {
    "provenance_pipeline.ProvenancePipeline": 100,
    "pipeline.ProductValidationPipeline": 300,
    "postgres_pipeline.PostgresExportPipeline": 500,
},
"PRODUCT_DEDUPE_IN_MEMORY": False,
"POSTGRES_AUTO_CREATE_TABLE": False,
```

Ensure `postgres_pipeline.py` is importable by the Scrapy process. Configure the DSN through the runtime environment, for example:

```sh
export SCRAPY_POSTGRES_DSN='postgresql://crawler:REDACTED@db.example.net:5432/catalog?sslmode=verify-full&sslrootcert=/run/secrets/postgres-ca.pem'
export POSTGRES_CONNECT_TIMEOUT=10
```

Use a dedicated migration role to apply the versioned SQL migrations in controlled environments. `001_create_scraped_products.sql` establishes the initial schema but does **not** upgrade an existing table whose columns or constraints differ. `002_add_first_seen_utc.sql` demonstrates a tested upgrade for installations missing `first_seen_utc`: it preserves existing rows, backfills null timestamps, enforces `NOT NULL` and a timestamp default even if the column already exists in a partially upgraded nullable state, and is safe to apply repeatedly. For future schema changes, inspect the live schema and add a new versioned migration rather than assuming `CREATE TABLE IF NOT EXISTS` upgrades existing objects. For a quick demo, `POSTGRES_AUTO_CREATE_TABLE` defaults to `True` and the pipeline runs compatible `CREATE TABLE IF NOT EXISTS` bootstrap DDL. For production or any least-privilege runtime, apply the SQL migration separately and set `POSTGRES_AUTO_CREATE_TABLE = False` in Scrapy settings. This disables all schema DDL in the crawler process so the runtime role can be limited to the required table privileges. Keep schema changes in an explicit migration workflow.

## Data and transaction contract

- URL is the primary key. Canonicalization normalizes scheme/host casing and strips fragments while preserving path and query semantics.
- Values are passed as SQL parameters; item values are never interpolated into SQL text.
- Each item is one transaction. Successful inserts commit independently; a statement failure attempts rollback and propagates to Scrapy. If `commit()` raises, the commit outcome may be unknown (for example, the server committed but the acknowledgement was lost): the pipeline attempts cleanup, discards the connection, and propagates the original error. It does not automatically retry an uncertain commit.
- `ON CONFLICT (url) DO NOTHING RETURNING url` makes repeated inserts idempotent. Duplicates are surfaced as `DropItem`, not counted as newly inserted records.
- Required fields are validated, and `extracted_at_utc` must be ISO-8601 with an explicit UTC offset.
- Existing rows are not updated on conflict. If Scrapy retries an item after an uncertain commit, the URL primary key and `ON CONFLICT DO NOTHING` prevent a second row, but the retry may be reported as a duplicate rather than a confirmed success. Reconcile the stored row before deciding whether to replay or mark the item complete.
- The pipeline does not reconnect or automatically retry after a commit error; a new pipeline instance is required after the connection is discarded.
- The table stores first-seen time separately from source extraction time.

## Backup and restore

See [OPERATIONS.md](OPERATIONS.md) for a full-database `pg_dump`/`pg_restore` runbook, checksum verification, isolated restore steps, and post-restore validation queries. The runbook is documented guidance only; a deployment is not backup-ready until operators have successfully rehearsed restoration and recorded evidence against its RPO/RTO.

## Tests and integration validation

The unit tests use a deterministic fake connection and never open a network connection. They cover schema bootstrap, parameterized inserts, duplicate behavior, rollback on statement failure, uncertain commit handling, bounded connection startup failure, shutdown cleanup when rollback fails, invalid records, and connection cleanup:

```sh
python -m unittest discover -s examples/04-postgres-export -p 'test_*.py' -v
```

The GitHub Actions workflow runs the fake-connection contract suite, live integration tests against an ephemeral PostgreSQL 15 service, and a backup/restore smoke test using `pg_dump` and `pg_restore` against two temporary databases on that same disposable service. The integration tests verify table bootstrap, URL canonicalization, persisted values, UTC timestamp handling, duplicate idempotency, a restricted crawler role that can insert records but cannot create schema objects, rollback recovery after a database-side failure, and a versioned migration that preserves legacy rows and is idempotent. The least-privilege test provisions and removes a dedicated test role, so it must only run against a disposable test database. Role DDL uses psycopg SQL composition for identifiers and literals rather than parameter placeholders in utility statements. Run it locally only against a disposable test database by setting `SCRAPY_POSTGRES_DSN` and installing this pattern's requirements:

```sh
python -m unittest discover -s examples/04-postgres-export -p 'test_postgres_integration.py' -v
```

The integration tests drop and recreate `scraped_products`, and the backup/restore test creates and drops temporary databases; **never point either test at a database or server containing data you need**. CI service credentials are test-only. The automated backup/restore smoke test verifies data, required columns, primary-key constraint, and a representative index on a disposable database; it does not establish production backup retention, off-host storage, permissions/roles recovery, TLS, reconnect behavior, live network interruption behavior, or compatibility with every possible legacy schema; the versioned migration test covers the specific documented pre-`first_seen_utc` schema. No live crawl or production deployment is performed.
