-- Migration 001: idempotent catalog sink.
-- Apply with a migration role; the crawler role should receive minimum required privileges.
CREATE TABLE IF NOT EXISTS scraped_products (
    url TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    price_text TEXT NOT NULL,
    source_url TEXT NOT NULL,
    extracted_at_utc TIMESTAMPTZ NOT NULL,
    spider_name TEXT NOT NULL,
    first_seen_utc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
