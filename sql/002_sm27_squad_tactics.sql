-- SM27 v0.2: player profile provenance, club ratings and tactical indexes.
ALTER TABLE players ADD COLUMN IF NOT EXISTS form SMALLINT NOT NULL DEFAULT 50;
ALTER TABLE players ADD COLUMN IF NOT EXISTS morale SMALLINT NOT NULL DEFAULT 70;
ALTER TABLE players ADD COLUMN IF NOT EXISTS sharpness SMALLINT NOT NULL DEFAULT 85;
ALTER TABLE players ADD COLUMN IF NOT EXISTS nationality_flag TEXT;
ALTER TABLE players ADD COLUMN IF NOT EXISTS profile_source TEXT NOT NULL DEFAULT 'SM27 estimate';
ALTER TABLE sm27_club_pool ADD COLUMN IF NOT EXISTS fifa_stars NUMERIC(2,1) NOT NULL DEFAULT 3.0;
ALTER TABLE sm27_club_pool ADD COLUMN IF NOT EXISTS team_strength SMALLINT NOT NULL DEFAULT 65;
ALTER TABLE sm27_club_pool ADD COLUMN IF NOT EXISTS rating_basis TEXT NOT NULL DEFAULT 'SM27 estimate';
CREATE INDEX IF NOT EXISTS idx_players_game_club_rating ON players(game_state_id,club_id,overall DESC);
CREATE INDEX IF NOT EXISTS idx_club_pool_fifa_stars ON sm27_club_pool(fifa_stars DESC,team_strength DESC);
CREATE INDEX IF NOT EXISTS idx_fixtures_game_month ON fixtures(game_state_id,match_date);
