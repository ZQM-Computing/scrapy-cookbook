-- Migration 002: add first-seen tracking to installations created before this field existed.
-- Safe to re-run; backfills NULL values and enforces the documented column contract.
ALTER TABLE scraped_products
    ADD COLUMN IF NOT EXISTS first_seen_utc TIMESTAMPTZ;

UPDATE scraped_products
SET first_seen_utc = CURRENT_TIMESTAMP
WHERE first_seen_utc IS NULL;

ALTER TABLE scraped_products
    ALTER COLUMN first_seen_utc SET DEFAULT CURRENT_TIMESTAMP,
    ALTER COLUMN first_seen_utc SET NOT NULL;
