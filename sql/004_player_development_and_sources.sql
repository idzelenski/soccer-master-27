-- SM27 player data provenance, player development and positional training.
ALTER TABLE players ADD COLUMN IF NOT EXISTS rating_source TEXT NOT NULL DEFAULT 'SM27 estimate';
ALTER TABLE players ADD COLUMN IF NOT EXISTS market_value_source TEXT NOT NULL DEFAULT 'SM27 estimate';
ALTER TABLE players ADD COLUMN IF NOT EXISTS market_value_as_of DATE;
ALTER TABLE players ADD COLUMN IF NOT EXISTS wage_source TEXT NOT NULL DEFAULT 'SM27 estimate';
ALTER TABLE players ADD COLUMN IF NOT EXISTS sofascore_player_id BIGINT;
ALTER TABLE players ADD COLUMN IF NOT EXISTS position_training_target TEXT;
ALTER TABLE players ADD COLUMN IF NOT EXISTS position_training_weeks SMALLINT NOT NULL DEFAULT 0;
ALTER TABLE players ADD COLUMN IF NOT EXISTS source_sync_attempted_at TIMESTAMPTZ;

-- Remove automatically assigned secondary positions from existing saves; they must be earned through training.
UPDATE players SET secondary_positions=ARRAY[]::text[]
WHERE cardinality(coalesce(secondary_positions,ARRAY[]::text[])) > 0;

-- Legacy market values came from a different source. Hide them until SofaScore confirms a current value.
UPDATE players SET market_value=0,market_value_source='SM27 estimate — waiting for Sofascore'
WHERE market_value_source='SM27 estimate' AND market_value>0;
UPDATE players SET rating_source='SM27 estimate — awaiting FC 27 data'
WHERE rating_source='SM27 estimate';

-- Replace implausibly low legacy wages with an OVR- and club-strength-based estimate.
UPDATE players p SET
  weekly_wage=GREATEST(400,ROUND((CASE
    WHEN p.overall>=92 THEN 350000 WHEN p.overall>=89 THEN 220000 WHEN p.overall>=86 THEN 145000
    WHEN p.overall>=83 THEN 78000 WHEN p.overall>=80 THEN 45000 WHEN p.overall>=77 THEN 24000
    WHEN p.overall>=74 THEN 13000 WHEN p.overall>=70 THEN 7000 WHEN p.overall>=66 THEN 3800
    WHEN p.overall>=62 THEN 2000 WHEN p.overall>=58 THEN 1000 ELSE 500 END)
    * GREATEST(0.55,LEAST(1.45,coalesce(c.reputation,60)/70.0))
    * CASE WHEN p.age>=38 THEN 0.78 WHEN p.age>=34 THEN 0.90 ELSE 1.0 END / 100.0)*100)::bigint,
  wage_source='SM27 estimate by OVR and club strength'
FROM clubs c
WHERE c.id=p.club_id AND p.wage_source='SM27 estimate';
