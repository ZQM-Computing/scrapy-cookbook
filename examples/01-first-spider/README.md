# 01 — First Scrapy spider

A small, bounded product-catalog spider using the educational [Books to Scrape](https://books.toscrape.com/) target. It demonstrates CSS selectors, URL resolution, pagination, incomplete-record handling, conservative crawl settings, and a validation/deduplication item pipeline.

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

Deduplication is in-memory and scoped to a single pipeline instance. It does not guarantee uniqueness across restarts, distributed workers, or separate jobs. The example does not normalize currency, guarantee stable selectors, or establish a legal right to collect or republish content.

## Test without network access

The tests parse synthetic HTML and synthetic item dictionaries; they make no HTTP requests:

```sh
python -m unittest discover -s examples/01-first-spider -p 'test_*.py' -v
```

Coverage includes selector extraction, relative URL resolution, pagination, incomplete records, polite/bounded settings, required-field validation, URL validation, conservative URL canonicalization, duplicate rejection, query-string preservation, and per-instance duplicate state.

## Limits

- The target markup may change; monitor missing fields and selector failures.
- Robots directives and terms must be rechecked for the actual target and crawl date.
- Do not bypass authentication, access controls, CAPTCHAs, paywalls, or rate limits.
- Do not collect sensitive personal data without a lawful basis and appropriate safeguards.
- For production ingestion, use persistent/idempotent deduplication appropriate to the deployment, define schema and retention rules, and add observability, retry, and failure-reporting policies.
