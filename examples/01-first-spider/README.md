# 01 — First Scrapy spider

A small, bounded product-catalog spider using the educational [Books to Scrape](https://books.toscrape.com/) target. It demonstrates CSS selectors, URL resolution, pagination, incomplete-record handling, and conservative crawl settings.

## Requirements

- Python 3.11 or newer
- Install the pinned dependency from this directory:

```sh
python -m pip install -r requirements.txt
```

## Run the example

From the repository root:

```sh
scrapy runspider examples/01-first-spider/spider.py -O products.json
```

The spider respects `robots.txt`, identifies itself with a descriptive user agent, waits at least one second between requests to the same domain, limits per-domain concurrency to one, enables AutoThrottle, and stops after five pages. A page cap is a safety bound, not permission to scrape a target. Verify the site's current terms and robots policy before each real use.

Output contains `title`, `price_text` (kept as source text rather than incorrectly assuming a currency format), `url`, and `source_url`. The example does not normalize currency, guarantee stable selectors, or establish a legal right to collect or republish content.

## Test without network access

The tests parse synthetic HTML fixtures and make no HTTP requests:

```sh
python -m unittest discover -s examples/01-first-spider -p 'test_*.py' -v
```

## Limits

- The target markup may change; monitor missing fields and selector failures.
- Robots directives and terms must be rechecked for the actual target and crawl date.
- Do not bypass authentication, access controls, CAPTCHAs, paywalls, or rate limits.
- Do not collect sensitive personal data without a lawful basis and appropriate safeguards.
- For production ingestion, add an explicit schema, deduplication, provenance, retention, retry, and failure-reporting policy.
