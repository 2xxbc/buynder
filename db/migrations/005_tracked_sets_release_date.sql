-- 005_tracked_sets_release_date.sql
-- Lets the home page's "New set" section pick the newest set by its real release date.
-- load_all_sets.py --apply fills it from PokeTrace's set list (if PokeTrace sends a release date;
-- scripts/check_sets.py prints the fields PokeTrace's sets have).
-- Run with:  ~/pokemarket/db/migrate.sh db/migrations/005_tracked_sets_release_date.sql   (backs up first)
ALTER TABLE tracked_sets ADD COLUMN release_date DATE NULL;
-- Undo:  ALTER TABLE tracked_sets DROP COLUMN release_date;
