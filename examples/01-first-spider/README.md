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

Output contains `title`, `price_text` (kept as source text rather than incorrectly assuming a currency format), `url`, `source_url`, `extracted_at_utc`, and `spider_name`. The provenance pipeline adds a UTC extraction timestamp and spider identity without changing source fields. `ProductValidationPipeline` rejects missing/blank required fields, non-HTTP(S) or malformed URLs, embedded URL credentials, and duplicate product URLs. URL deduplication lowercases scheme/host and removes fragments while preserving path and query parameters.

## Provenance and crawl-quality summary

The example enables an optional summary extension. To write a machine-readable report, pass a path at runtime:

```sh
scrapy runspider examples/01-first-spider/spider.py \\
  -s CRAWL_SUMMARY_PATH=./var/crawl-summary.json \\
  -O products.json
```

The extension writes the JSON summary when the spider closes, using a temporary file and atomic replacement. It includes spider identity, UTC start/close timestamps, close reason, selected Scrapy stats (including response status, downloader exception counts, and incomplete-record skip counts when present), the count of items that passed all pipelines, item-drop categories, pipeline/spider error counts by exception type, and scheduler-dropped request count. It does not store exception messages or scraped item contents in the summary. The report is an operational aid, not a complete audit log: other extraction failures that are logged directly by the spider and failures that Scrapy does not expose through the connected signals may not appear as a dedicated category. Protect and retain the report according to your data-governance requirements.

## Optional persistent deduplication (SQLite)

The default in-memory pipeline is lightweight and requires no database, but forgets seen URLs when the crawler process ends. For a single-host workflow that needs deduplication across restarts, the optional `SQLiteDeduplicationPipeline` stores canonical URLs in a local SQLite database using a primary key and parameterized SQL. SQLite is included with Python; no additional package is required.

1. Keep the validation pipeline enabled.
2. Set a writable database path and replace the in-memory pipeline entry in `CatalogSpider.custom_settings`:

```python
"SCRAPY_DEDUPE_DB": "./var/catalog-dedupe.sqlite3",
"PRODUCT_DEDUPE_IN_MEMORY": False,
"ITEM_PIPELINES": {
    "pipeline.ProductValidationPipeline": 300,
    "sqlite_pipeline.SQLiteDeduplicationPipeline": 400,
},
```

The persistent pipeline is deliberately optional and is not enabled by default. Set `PRODUCT_DEDUPE_IN_MEMORY=False` so the validation pipeline continues validating fields and URLs without doing in-memory duplicate filtering; the SQLite pipeline then owns duplicate detection. Keep validation ordered before SQLite so malformed items are rejected before database writes.

SQLite is appropriate for a single machine or a small sequential ingestion job, not a shared distributed crawler. It is not a multi-host coordination service, and concurrent writers may contend on file locks. Back up the database, define its retention policy, and treat the canonicalization key as a data contract. URL normalization here only lowercases scheme/host and strips fragments; it intentionally preserves path and query strings.

## Optional idempotent JSONL export

For a restart-safe local export, use `SQLiteJsonlExportPipeline`. It validates a fixed schema, stores records in SQLite under a canonical-URL primary key, and rebuilds a deterministic JSON Lines snapshot from the durable staging table. Each exported line contains only `schema_version`, `title`, `price_text`, `url`, `source_url`, `extracted_at_utc`, and `spider_name`; unexpected item fields are not copied into the export.

Configure this pipeline as an alternative to both the in-memory duplicate filter and `SQLiteDeduplicationPipeline` (do not enable both SQLite pipelines together):

```python
"PRODUCT_DEDUPE_IN_MEMORY": False,
"SCRAPY_EXPORT_DB": "./var/export-items.sqlite3",
"SCRAPY_EXPORT_JSONL_PATH": "./var/products.jsonl",
"ITEM_PIPELINES": {
    "provenance_pipeline.ProvenancePipeline": 100,
    "pipeline.ProductValidationPipeline": 300,
    "jsonl_export_pipeline.SQLiteJsonlExportPipeline": 500,
},
```

Add these entries to `CatalogSpider.custom_settings` or equivalent project settings, replacing its existing `ITEM_PIPELINES` mapping. Then run the spider as usual. The database is the durable staging source; the JSONL snapshot is regenerated at spider close. If snapshot replacement fails, the prior output remains intact and committed staging records remain available for a later retry. A rerun with already-seen canonical URLs does not duplicate exported rows.

This is a single-host pattern, not distributed coordination. Keep the SQLite database and exported data under appropriate access controls, back them up, and define retention. Atomic replacement protects the local snapshot from partial writes but does not guarantee durability against every filesystem or hardware failure. The JSONL snapshot is a full retained-data export, not just records from the latest run.

## Test without network access

The tests parse synthetic HTML and synthetic item dictionaries; they make no HTTP requests:

```sh
python -m unittest discover -s examples/01-first-spider -p 'test_*.py' -v
```

Coverage includes selector extraction, relative URL resolution, pagination, incomplete-record metrics, polite/bounded settings, required-field and URL validation, URL canonicalization, in-memory and SQLite deduplication, JSONL schema enforcement, restart idempotency, deterministic snapshots, and preservation of the previous export when atomic replacement fails.

## Limits

- The target markup may change; monitor missing fields and selector failures.
- Robots directives and terms must be rechecked for the actual target and crawl date.
- Do not bypass authentication, access controls, CAPTCHAs, paywalls, or rate limits.
- Do not collect sensitive personal data without a lawful basis and appropriate safeguards.
- Persistent deduplication is not a substitute for schema validation, transactional downstream writes, observability, or recovery procedures.
