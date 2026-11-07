-- Gather World: additive Food & Travel search/discovery schema upgrade.
-- This migration preserves existing directory records.
ALTER TABLE gw_directory_entries ADD COLUMN IF NOT EXISTS contact_phone VARCHAR(40) NOT NULL DEFAULT '';
ALTER TABLE gw_directory_entries ADD COLUMN IF NOT EXISTS info_source_url TEXT NOT NULL DEFAULT '';
ALTER TABLE gw_directory_entries ADD COLUMN IF NOT EXISTS food_cuisine VARCHAR(120) NOT NULL DEFAULT '';
ALTER TABLE gw_directory_entries ADD COLUMN IF NOT EXISTS food_opening_hours TEXT NOT NULL DEFAULT '';
ALTER TABLE gw_directory_entries ADD COLUMN IF NOT EXISTS food_menu_highlights TEXT NOT NULL DEFAULT '';
ALTER TABLE gw_directory_entries ADD COLUMN IF NOT EXISTS food_good_for TEXT NOT NULL DEFAULT '';
ALTER TABLE gw_directory_entries ADD COLUMN IF NOT EXISTS food_dietary_notes TEXT NOT NULL DEFAULT '';
ALTER TABLE gw_directory_entries ADD COLUMN IF NOT EXISTS food_average_cost VARCHAR(120) NOT NULL DEFAULT '';
ALTER TABLE gw_directory_entries ADD COLUMN IF NOT EXISTS travel_best_season VARCHAR(160) NOT NULL DEFAULT '';
ALTER TABLE gw_directory_entries ADD COLUMN IF NOT EXISTS travel_how_to_get_there TEXT NOT NULL DEFAULT '';
ALTER TABLE gw_directory_entries ADD COLUMN IF NOT EXISTS travel_attractions TEXT NOT NULL DEFAULT '';
ALTER TABLE gw_directory_entries ADD COLUMN IF NOT EXISTS travel_daily_budget_min INTEGER;
ALTER TABLE gw_directory_entries ADD COLUMN IF NOT EXISTS travel_daily_budget_max INTEGER;
ALTER TABLE gw_directory_entries ADD COLUMN IF NOT EXISTS travel_budget_currency VARCHAR(8) NOT NULL DEFAULT 'PKR';
ALTER TABLE gw_directory_entries ADD COLUMN IF NOT EXISTS travel_duration_days INTEGER;
ALTER TABLE gw_directory_entries ADD COLUMN IF NOT EXISTS travel_budget_breakdown TEXT NOT NULL DEFAULT '';
ALTER TABLE gw_directory_entries ADD COLUMN IF NOT EXISTS travel_sample_itinerary TEXT NOT NULL DEFAULT '';
ALTER TABLE gw_directory_entries ADD COLUMN IF NOT EXISTS travel_local_tips TEXT NOT NULL DEFAULT '';
ALTER TABLE gw_directory_entries ADD COLUMN IF NOT EXISTS travel_safety_notes TEXT NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS gw_directory_reviews (
    id BIGSERIAL PRIMARY KEY,
    entry_id BIGINT NOT NULL REFERENCES gw_directory_entries(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES gw_users(id) ON DELETE CASCADE,
    rating SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    headline VARCHAR(120) NOT NULL DEFAULT '',
    review_text VARCHAR(2000) NOT NULL,
    status VARCHAR(12) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(entry_id,user_id)
);
CREATE INDEX IF NOT EXISTS gw_directory_reviews_public_idx ON gw_directory_reviews(entry_id,status,created_at DESC);
CREATE INDEX IF NOT EXISTS gw_directory_reviews_moderation_idx ON gw_directory_reviews(status,created_at DESC);
