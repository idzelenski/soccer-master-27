-- FC 27 rating catalog and trainable secondary positions.
CREATE TABLE IF NOT EXISTS fc27_player_catalog (
    ea_player_id BIGINT PRIMARY KEY,
    display_name TEXT NOT NULL,
    name_key TEXT NOT NULL,
    first_name TEXT,
    last_name TEXT,
    position TEXT,
    alternate_positions TEXT[] NOT NULL DEFAULT ARRAY[]::text[],
    nationality TEXT,
    nationality_code TEXT,
    club_name TEXT,
    league_name TEXT,
    overall SMALLINT NOT NULL,
    potential SMALLINT,
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_url TEXT,
    source_snapshot DATE NOT NULL DEFAULT DATE '2026-09-10',
    raw_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS fc27_import_state (
    import_key TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    attempted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_fc27_player_name_key ON fc27_player_catalog(name_key);
CREATE INDEX IF NOT EXISTS idx_fc27_player_nationality ON fc27_player_catalog(nationality_code,name_key);
CREATE INDEX IF NOT EXISTS idx_fc27_player_overall ON fc27_player_catalog(overall DESC);
ALTER TABLE players ADD COLUMN IF NOT EXISTS fc27_player_id BIGINT;
ALTER TABLE players ADD COLUMN IF NOT EXISTS position_training_target TEXT;
ALTER TABLE players ADD COLUMN IF NOT EXISTS position_training_progress SMALLINT NOT NULL DEFAULT 0;
ALTER TABLE players ADD COLUMN IF NOT EXISTS market_value_source TEXT NOT NULL DEFAULT 'SM27 estimate';
ALTER TABLE world_player_catalog ADD COLUMN IF NOT EXISTS fc27_player_id BIGINT;
CREATE INDEX IF NOT EXISTS idx_players_fc27_id ON players(fc27_player_id);
CREATE INDEX IF NOT EXISTS idx_world_player_fc27_id ON world_player_catalog(fc27_player_id);
