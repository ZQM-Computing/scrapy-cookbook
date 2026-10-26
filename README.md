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

A **Scrapy cookbook** for polite web scraping spiders, pipelines, and exports. Patterns are drawn from the ZQM fleet's Scrapy 2.19.0 installs and its demo spider (10 items, robots-obeying, 1s delay, identical on Node-3 and Node-4). Scrape only sources you are allowed to scrape, and respect robots.txt. It is intended for Data engineers who collect public web data into structured datasets. Validate each pattern against your own data, software versions, and operating environment before adopting it.

## Repository role and status

**Status:** Active, public — first runnable spider and offline unit tests implemented. The first pattern is covered by CI; live target compatibility, long-running crawl behavior, and downstream production ingestion remain unverified.

**What this repository is:** Scrapy patterns — see the table below.

**What it contributes:** Part of the ZQM Computing geospatial portfolio. The umbrella index for the series is [geospatial-cookbooks](https://github.com/ZQM-Computing/geospatial-cookbooks).

**Standing:** This repository is maintained independently. Automated checks cover only the paths and environments configured in its workflows; they do not establish production readiness or operational certification.

## Who this is for

Data engineers who collect public web data into structured datasets.

## Prerequisites

- Scrapy 2.19.0
- Python 3.11+
- A robots-respecting demo target for the first spider

## Patterns

| # | Example | Status | What it demonstrates |
|---|---------|--------|----------------------|
| 01 | [`01-first-spider`](examples/01-first-spider/README.md) | Implemented; CI pending | CSS selectors, pagination, URL resolution, incomplete-record handling, and bounded polite settings; tests use offline HTML fixtures |
| 02 | `02-robots-delay` | Planned | Robots compliance, delays, and polite crawling settings |
| 03 | `03-pipelines` | Planned | Item pipelines for cleaning and validation |
| 04 | `04-postgres-export` | Planned | Exporting items into Postgres for analysis |

## Quick start

Requires Python 3.11 or newer. Install the pinned Scrapy dependency and run the example from the repository root:

```sh
python -m pip install -r examples/01-first-spider/requirements.txt
scrapy runspider examples/01-first-spider/spider.py -O products.json
```

The spider respects `robots.txt`, identifies itself, uses a one-second per-domain delay, limits per-domain concurrency to one, enables AutoThrottle, and stops after five pages. Tests run against synthetic HTML and do not contact the target site:

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
│   ├── spider.py
│   └── test_spider.py
├── README.md
└── LICENSE
```

## Roadmap

- Next: add explicit pipeline validation and deterministic duplicate handling (03).
- Then: demonstrate a database export only after defining schema, idempotency, and failure behavior (04).

## Contributing

A contributing guide lands with the first pattern pass. Report security issues to <zqmcomputing@gmail.com> — please do not open a public issue for those.

## More from this series

- [theharvester-cookbook](https://github.com/ZQM-Computing/theharvester-cookbook) — Passive reconnaissance: domains, emails, and hosts from public sources
- [spiderfoot-cookbook](https://github.com/ZQM-Computing/spiderfoot-cookbook) — Passive OSINT automation as a service
- [duckdb-spatial-cookbook](https://github.com/ZQM-Computing/duckdb-spatial-cookbook) — Analytical geospatial SQL with DuckDB Spatial
