-- 002_users_last_seen.sql: remember when each user was last active, so the daily ops report
-- can count "active users". Run with db/migrate.sh (it backs up first).
--
-- app.py (touch_last_seen) fills it in at most once every 5 minutes per logged-in session,
-- and only once this column exists (each API worker notices it within 10 minutes; no restart needed).

ALTER TABLE users ADD COLUMN last_seen DATETIME NULL;
CREATE INDEX idx_users_last_seen ON users (last_seen);   -- "active in the last 24h" stays fast

-- Check:  SHOW COLUMNS FROM users LIKE 'last_seen';
-- Undo:   DROP INDEX idx_users_last_seen ON users;  ALTER TABLE users DROP COLUMN last_seen;
