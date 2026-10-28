-- 006_market_card_sales_daily.sql
-- One row per card per day: PokeTrace's lifetime NM sale count as the nightly sweep saw it.
-- "Sold in the last 30 days" = today's count - the count 30 days ago (the Trending page's "Most sold").
-- PokeTrace only gives lifetime totals, so this is the only honest way to get a 30-day number.
-- Run with:  ~/pokemarket/db/migrate.sh db/migrations/006_market_card_sales_daily.sql   (backs up first)
-- Size: ~43,000 rows a night; the sweep deletes rows older than 40 days (~1.7M rows, roughly 100 MB).
CREATE TABLE IF NOT EXISTS market_card_sales_daily (
  poketrace_id VARCHAR(64) NOT NULL,
  day DATE NOT NULL,
  sale_count INT NOT NULL,
  PRIMARY KEY (poketrace_id, day),
  KEY idx_day (day)
);
-- Undo:  DROP TABLE market_card_sales_daily;
