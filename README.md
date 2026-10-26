# Scrapy Cookbook

<!-- ZQM-START -->
<!-- markdownlint-disable MD033 -->
<p align="center">
  <strong>ZQM Computing — Geospatial Engineering & Scientific Computing</strong><br>
  <a href="https://github.com/ZQM-Computing">ZQM Computing</a>
</p>
<!-- markdownlint-enable MD033 -->
<!-- ZQM-END -->

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

A **Scrapy cookbook** for polite web scraping spiders, validation pipelines, and exports. The first example uses Scrapy 2.19.0 and Python 3.11+ against the educational Books to Scrape target. Scrape only sources you are allowed to scrape, and respect robots.txt. It is intended for data engineers who collect public web data into structured datasets. Validate each pattern against your own data, software versions, and operating environment before adopting it.

## Repository role and status

**Status:** Active, public — bounded spider, provenance enrichment, validation/deduplication pipelines, optional SQLite persistence, optional JSON crawl summary, optional idempotent SQLite-backed JSONL export, and offline unit tests implemented. CI covers the configured offline tests; live target compatibility, long-running crawl behavior, and downstream production ingestion remain unverified.

**What this repository is:** Scrapy patterns — see the table below.

**What it contributes:** Part of the ZQM Computing geospatial portfolio. The umbrella index for the series is [geospatial-cookbooks](https://github.com/ZQM-Computing/geospatial-cookbooks).

**Standing:** This repository is maintained independently. Automated checks cover only the paths and environments configured in its workflows; they do not establish production readiness or operational certification.

## Who this is for

Data engineers who collect public web data into structured datasets.

## Prerequisites

- Python 3.11+
- Scrapy 2.19.0 (pinned in the first example)
- A robots-respecting demo target for the first spider

## Patterns

| # | Example | Status | What it demonstrates |
|---|---------|--------|----------------------|
| 01 | [`01-first-spider`](examples/01-first-spider/README.md) | Implemented; offline tests cover provenance, validation/deduplication, and summary output | CSS selectors, pagination, UTC provenance, schema/URL validation, per-run or persistent deduplication, crawl-quality summaries, and restart-safe JSONL export |
| 02 | `02-robots-delay` | Planned | Robots compliance, delays, and polite crawling settings |
| 03 | `03-pipelines` | Partially covered by pattern 01 | Required-field/URL validation, in-memory duplicate filtering, and optional SQLite persistence across restarts |
| 04 | `04-postgres-export` | Planned | Exporting items into Postgres for analysis |

## Quick start

Requires Python 3.11 or newer. Install the pinned Scrapy dependency and run the example from the repository root:

```sh
python -m pip install -r examples/01-first-spider/requirements.txt
scrapy runspider examples/01-first-spider/spider.py -O products.json
```

The spider respects `robots.txt`, identifies itself, uses a one-second per-domain delay, limits per-domain concurrency to one, enables AutoThrottle, and stops after five pages. By default, the enabled pipelines attach UTC extraction provenance and reject malformed/incomplete records and duplicates within a single run. Persistent SQLite deduplication, JSON crawl summaries, and the SQLite-backed JSONL snapshot exporter are opt-in. The exporter uses a fixed allowlisted schema and preserves the previous snapshot if replacement fails. Tests run against synthetic HTML/items and temporary SQLite databases without contacting the target site:

```sh
python -m unittest discover -s examples/01-first-spider -p 'test_*.py' -v
```

## Repository layout

```text
scrapy-cookbook/
├── .github/workflows/examples.yml
├── examples/01-first-spider/
│   ├── README.md
│   ├── requirements.txt
│   ├── pipeline.py
│   ├── sqlite_pipeline.py
│   ├── jsonl_export_pipeline.py
│   ├── spider.py
│   ├── test_pipeline.py
│   ├── test_spider.py
│   ├── test_sqlite_pipeline.py
│   └── test_jsonl_export_pipeline.py
├── README.md
└── LICENSE
```

## Roadmap

- Next: add a dedicated Postgres export pattern (04), with supported-version policy, schema migrations, transaction boundaries, connection-secret handling, and integration-test strategy.

## Contributing

A contributing guide lands with the first pattern pass. Report security issues to <zqmcomputing@gmail.com> — please do not open a public issue for those.

## More from this series

- [theharvester-cookbook](https://github.com/ZQM-Computing/theharvester-cookbook) — Passive reconnaissance: domains, emails, and hosts from public sources
- [spiderfoot-cookbook](https://github.com/ZQM-Computing/spiderfoot-cookbook) — Passive OSINT automation as a service
- [duckdb-spatial-cookbook](https://github.com/ZQM-Computing/duckdb-spatial-cookbook) — Analytical geospatial SQL with DuckDB Spatial
