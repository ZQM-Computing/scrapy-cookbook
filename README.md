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

**Status:** Active, public — seeding. Pattern passes land in follow-up work from fleet-verified setups; the tables below list what is planned, not what is already written.

**What this repository is:** Scrapy patterns — see the table below.

**What it contributes:** Part of the ZQM Computing geospatial portfolio. The umbrella index for the series is [geospatial-cookbooks](https://github.com/ZQM-Computing/geospatial-cookbooks).

**Standing:** This repository is maintained independently. Automated checks cover only the paths and environments configured in its workflows; they do not establish production readiness or operational certification.

## Who this is for

Data engineers who collect public web data into structured datasets.

## Prerequisites

- Scrapy 2.19.0
- Python 3.11+
- A robots-respecting demo target for the first spider

## Patterns (planned)

| # | Example | What it will demonstrate |
|---|---------|--------------------------|
| 01 | `01-first-spider` | A first spider: items, selectors, and pagination |
| 02 | `02-robots-delay` | Robots compliance, delays, and polite crawling settings |
| 03 | `03-pipelines` | Item pipelines for cleaning and validation |
| 04 | `04-postgres-export` | Exporting items into Postgres for analysis |

## Repository layout

```text
scrapy-cookbook/
├── examples/          # pattern passes, landing in follow-up work
├── README.md
└── LICENSE
```

## Roadmap

- First pattern pass: the first two table rows
- Second pass: the remaining rows, from fleet-verified setups

## Contributing

A contributing guide lands with the first pattern pass. Report security issues to <zqmcomputing@gmail.com> — please do not open a public issue for those.

## More from this series

- [theharvester-cookbook](https://github.com/ZQM-Computing/theharvester-cookbook) — Passive reconnaissance: domains, emails, and hosts from public sources
- [spiderfoot-cookbook](https://github.com/ZQM-Computing/spiderfoot-cookbook) — Passive OSINT automation as a service
- [duckdb-spatial-cookbook](https://github.com/ZQM-Computing/duckdb-spatial-cookbook) — Analytical geospatial SQL with DuckDB Spatial
