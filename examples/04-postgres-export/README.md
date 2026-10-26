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

Set `SCRAPY_POSTGRES_DSN` in the process environment or Scrapy settings. Prefer a secret manager or deployment environment injection; do not commit DSNs, passwords, certificates, or production credentials. Use TLS with certificate verification for remote databases and a least-privilege role.

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
export SCRAPY_POSTGRES_DSN='postgresql://crawler:REDACTED@localhost:5432/catalog'
```

Use a dedicated migration role to apply `001_create_scraped_products.sql` in controlled environments. This is the initial schema migration: it is safe to apply repeatedly when the table is absent or already matches this schema, but `CREATE TABLE IF NOT EXISTS` does **not** upgrade an existing table whose columns or constraints differ. For existing installations, inspect the live schema and write/test a new versioned `ALTER TABLE` migration before deploying code that depends on changed fields. For a quick demo, `POSTGRES_AUTO_CREATE_TABLE` defaults to `True` and the pipeline runs compatible `CREATE TABLE IF NOT EXISTS` bootstrap DDL. For production or any least-privilege runtime, apply the SQL migration separately and set `POSTGRES_AUTO_CREATE_TABLE = False` in Scrapy settings. This disables all schema DDL in the crawler process so the runtime role can be limited to the required table privileges. Keep schema changes in an explicit migration workflow.

## Data and transaction contract

- URL is the primary key. Canonicalization normalizes scheme/host casing and strips fragments while preserving path and query semantics.
- Values are passed as SQL parameters; item values are never interpolated into SQL text.
- Each item is one transaction. Successful inserts commit independently; an item failure rolls back and propagates to Scrapy.
- `ON CONFLICT (url) DO NOTHING RETURNING url` makes repeated inserts idempotent. Duplicates are surfaced as `DropItem`, not counted as newly inserted records.
- Required fields are validated, and `extracted_at_utc` must be ISO-8601 with an explicit UTC offset.
- Existing rows are not updated on conflict. If refresh/upsert semantics are needed, define freshness ordering and update policy explicitly.
- The table stores first-seen time separately from source extraction time.

## Tests and integration validation

The unit tests use a deterministic fake connection and never open a network connection. They cover schema bootstrap, parameterized inserts, duplicate behavior, rollback on database failure, invalid records, and connection cleanup:

```sh
python -m unittest discover -s examples/04-postgres-export -p 'test_*.py' -v
```

The GitHub Actions workflow runs both the fake-connection contract suite and a live integration test against an ephemeral PostgreSQL 15 service. The integration tests verify table bootstrap, URL canonicalization, persisted values, UTC timestamp handling, duplicate idempotency, and a restricted crawler role that can insert records but cannot create schema objects. The least-privilege test provisions and removes a dedicated test role, so it must only run against a disposable test database. Role DDL uses psycopg SQL composition for identifiers and literals rather than parameter placeholders in utility statements. Run it locally only against a disposable test database by setting `SCRAPY_POSTGRES_DSN` and installing this pattern's requirements:

```sh
python -m unittest discover -s examples/04-postgres-export -p 'test_postgres_integration.py' -v
```

The integration test drops and recreates `scraped_products`; **never point it at a database containing data you need**. CI service credentials are test-only. This coverage does not establish production TLS, least-privilege permissions, reconnect behavior, migration compatibility with pre-existing schemas, or backup/restore. No live crawl or production deployment is performed.
