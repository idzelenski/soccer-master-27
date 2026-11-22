-- SM27 player data provenance, player development and positional training.
ALTER TABLE players ADD COLUMN IF NOT EXISTS rating_source TEXT NOT NULL DEFAULT 'SM27 estimate';
ALTER TABLE players ADD COLUMN IF NOT EXISTS market_value_source TEXT NOT NULL DEFAULT 'SM27 estimate';
ALTER TABLE players ADD COLUMN IF NOT EXISTS market_value_as_of DATE;
ALTER TABLE players ADD COLUMN IF NOT EXISTS wage_source TEXT NOT NULL DEFAULT 'SM27 estimate';
ALTER TABLE players ADD COLUMN IF NOT EXISTS sofascore_player_id BIGINT;
ALTER TABLE players ADD COLUMN IF NOT EXISTS position_training_target TEXT;
ALTER TABLE players ADD COLUMN IF NOT EXISTS position_training_weeks SMALLINT NOT NULL DEFAULT 0;

-- Remove automatically assigned secondary positions from existing saves; they must be earned through training.
UPDATE players SET secondary_positions=ARRAY[]::text[]
WHERE cardinality(coalesce(secondary_positions,ARRAY[]::text[])) > 0;

-- Existing market values came from Transfermarkt or the previous model and must not be presented as SofaScore values.
UPDATE players SET market_value_source='SM27 estimate — waiting for SofaScore import'
WHERE market_value_source='SM27 estimate' AND market_value>0;
UPDATE players SET rating_source=coalesce(nullif(profile_source,''),'SM27 estimate')
WHERE rating_source='SM27 estimate' AND profile_source IS NOT NULL AND profile_source <> '';
