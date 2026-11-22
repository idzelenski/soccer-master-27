-- Additive, idempotent SM27 migration. Existing game tables are preserved.
ALTER TABLE managers ADD COLUMN IF NOT EXISTS password_hash TEXT;
ALTER TABLE managers ADD COLUMN IF NOT EXISTS session_token_hash TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS managers_session_token_hash_key
  ON managers(session_token_hash) WHERE session_token_hash IS NOT NULL;

ALTER TABLE game_states ADD COLUMN IF NOT EXISTS managed_club_id UUID REFERENCES clubs(id) ON DELETE SET NULL;
ALTER TABLE game_states ADD COLUMN IF NOT EXISTS game_settings JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE game_states ADD COLUMN IF NOT EXISTS save_name TEXT NOT NULL DEFAULT 'Моя карьера';
CREATE INDEX IF NOT EXISTS idx_game_states_managed_club ON game_states(managed_club_id);

CREATE TABLE IF NOT EXISTS sm27_club_pool (
  source_id TEXT PRIMARY KEY REFERENCES world_club_catalog(source_id) ON DELETE CASCADE,
  club_name TEXT NOT NULL,
  country TEXT,
  country_iso CHAR(2),
  continent TEXT NOT NULL DEFAULT 'UEFA',
  league_name TEXT,
  league_code TEXT NOT NULL,
  league_level SMALLINT NOT NULL DEFAULT 1,
  division SMALLINT,
  city TEXT,
  stadium TEXT,
  stadium_capacity INTEGER,
  founded TEXT,
  colors_hex TEXT,
  logo_url TEXT,
  logo_license TEXT,
  logo_commons_url TEXT,
  wikipedia_url TEXT,
  has_squad BOOLEAN NOT NULL DEFAULT FALSE,
  squad_count INTEGER NOT NULL DEFAULT 0,
  source_release TEXT NOT NULL,
  source_snapshot DATE NOT NULL,
  sort_rank INTEGER NOT NULL DEFAULT 999999,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sm27_club_pool_league ON sm27_club_pool(league_code, sort_rank);
CREATE INDEX IF NOT EXISTS idx_sm27_club_pool_search ON sm27_club_pool USING gin (to_tsvector('simple', club_name || ' ' || COALESCE(country, '')));
CREATE INDEX IF NOT EXISTS idx_world_player_club_name ON world_player_catalog(club_source_id, name);
CREATE INDEX IF NOT EXISTS idx_world_players_value ON world_player_catalog(market_value_eur DESC);
CREATE INDEX IF NOT EXISTS idx_players_save_club ON players(game_state_id, club_id, position);
CREATE INDEX IF NOT EXISTS idx_fixtures_save_date_status ON fixtures(game_state_id, match_date, status);

CREATE UNIQUE INDEX IF NOT EXISTS tactics_game_state_club_key ON tactics(game_state_id, club_id);

ALTER TABLE sm27_club_pool ADD COLUMN IF NOT EXISTS continent TEXT NOT NULL DEFAULT 'UEFA';

