# 01 — First Scrapy spider

A small, bounded product-catalog spider using the educational [Books to Scrape](https://books.toscrape.com/) target. It demonstrates CSS selectors, URL resolution, pagination, incomplete-record handling, conservative crawl settings, and data-quality pipelines.

## Requirements

- Python 3.11 or newer
- Install the pinned dependency from this directory:

```sh
python -m pip install -r examples/01-first-spider/requirements.txt
```

## Run the example

From the repository root:

```sh
scrapy runspider examples/01-first-spider/spider.py -O products.json
```

The spider respects `robots.txt`, identifies itself with a descriptive user agent, waits at least one second between requests to the same domain, limits per-domain concurrency to one, enables AutoThrottle, and stops after five pages. A page cap is a safety bound, not permission to scrape a target. Verify the site's current terms and robots policy before each real use.

Output contains `title`, `price_text` (kept as source text rather than incorrectly assuming a currency format), `url`, and `source_url`. The enabled `ProductValidationPipeline` rejects missing/blank required fields, non-HTTP(S) or malformed URLs, embedded URL credentials, and duplicate product URLs. URL deduplication lowercases scheme/host and removes fragments while preserving path and query parameters.

## Optional persistent deduplication (SQLite)

The default in-memory pipeline is lightweight and requires no database, but forgets seen URLs when the crawler process ends. For a single-host workflow that needs deduplication across restarts, the optional `SQLiteDeduplicationPipeline` stores canonical URLs in a local SQLite database using a primary key and parameterized SQL. SQLite is included with Python; no additional package is required.

1. Keep the validation pipeline enabled.
2. Set a writable database path and replace the in-memory pipeline entry in `CatalogSpider.custom_settings`:

```python
"SCRAPY_DEDUPE_DB": "./var/catalog-dedupe.sqlite3",
"ITEM_PIPELINES": {
    "pipeline.ProductValidationPipeline": 300,
    "sqlite_pipeline.SQLiteDeduplicationPipeline": 400,
},
```

The persistent pipeline is deliberately optional and is not enabled by default. Do not enable both duplicate filters simultaneously: the in-memory pipeline would drop duplicates before SQLite sees them, obscuring which layer performed the deduplication. To use SQLite, instead configure validation plus SQLite as shown above (omit `pipeline.ProductValidationPipeline`'s duplicate behavior only if you split validation and in-memory deduplication into separate components; this current combined class does both). For the current implementation, the simplest practical configuration is to disable the in-memory duplicate check via a separate validation-only class or change the pipeline to a validation-only mode before enabling SQLite. The SQLite pipeline still enforces uniqueness in its own database.

SQLite is appropriate for a single machine or a small sequential ingestion job, not a shared distributed crawler. It is not a multi-host coordination service, and concurrent writers may contend on file locks. Back up the database, define its retention policy, and treat the canonicalization key as a data contract. URL normalization here only lowercases scheme/host and strips fragments; it intentionally preserves path and query strings.

## Test without network access

The tests parse synthetic HTML and synthetic item dictionaries; they make no HTTP requests:

```sh
python -m unittest discover -s examples/01-first-spider -p 'test_*.py' -v
```

Coverage includes selector extraction, relative URL resolution, pagination, incomplete records, polite/bounded settings, required-field validation, URL validation, conservative URL canonicalization, duplicate rejection, query-string preservation, per-instance duplicate state, SQLite persistence, and restart behavior.

## Limits

- The target markup may change; monitor missing fields and selector failures.
- Robots directives and terms must be rechecked for the actual target and crawl date.
- Do not bypass authentication, access controls, CAPTCHAs, paywalls, or rate limits.
- Do not collect sensitive personal data without a lawful basis and appropriate safeguards.
- Persistent deduplication is not a substitute for schema validation, transactional downstream writes, observability, or recovery procedures.
