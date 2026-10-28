-- 004_price_paid_unknown.sql
-- Lets collection.price_paid say "unknown" (NULL) separately from "really paid $0".
-- Run with:  ~/pokemarket/db/migrate.sh db/migrations/004_price_paid_unknown.sql   (it backs up first)
--
-- Why both steps are together: until now, a blank "price paid" box was saved as 0, so every
-- stored 0 might be a blank. The app currently treats 0 as unknown for exactly that reason.
-- Once the column allows NULL, the app reads 0 as "really $0", so the old zeros must become
-- NULL in the same step, or blanks would suddenly count as free cards again.
-- Cards that really were free can be set to $0 again from Collection → "Add price" → 0.

-- 1. Allow NULL, keeping the column's exact current type (read from MySQL, not guessed).
SELECT COLUMN_TYPE INTO @paid_type FROM information_schema.COLUMNS
 WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'collection' AND COLUMN_NAME = 'price_paid';
SET @sql = CONCAT('ALTER TABLE collection MODIFY price_paid ', @paid_type, ' NULL DEFAULT NULL');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 2. Old zeros become "unknown".
UPDATE collection SET price_paid = NULL WHERE price_paid = 0;

-- Check:  SELECT IS_NULLABLE, COLUMN_TYPE FROM information_schema.COLUMNS
--          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'collection' AND COLUMN_NAME = 'price_paid';
--         SELECT COUNT(*) FROM collection WHERE price_paid IS NULL;
-- Undo (puts the zeros back; the NOT NULL part only if it was NOT NULL before):
--   UPDATE collection SET price_paid = 0 WHERE price_paid IS NULL;
--   ALTER TABLE collection MODIFY price_paid <type from the check above> NOT NULL DEFAULT 0;
