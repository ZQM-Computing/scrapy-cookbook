-- Migration 002: add first-seen tracking to installations created before this field existed.
-- Safe to re-run; preserves existing catalog rows and populates the new field.
ALTER TABLE scraped_products
    ADD COLUMN IF NOT EXISTS first_seen_utc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP;
