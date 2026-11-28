-- Immutable starting-data catalog for new careers.
-- Existing captured baseline fields are never overwritten by catalog refreshes.

UPDATE world_player_catalog wp
SET fc27_player_id=fc.ea_player_id
FROM world_club_catalog wc
JOIN fc27_player_catalog fc
  ON fc.ea_player_id=239053
 AND fc.name_key='federicovalverde'
 AND fc.nationality_code='URY'
WHERE wp.source_id='Q19509544'
  AND wp.name='Fede Valverde'
  AND wp.fc27_player_id IS NULL
  AND wc.source_id=wp.club_source_id
  AND wc.name='Real Madrid CF';

CREATE TABLE IF NOT EXISTS sm27_player_baseline_catalog (
    source_id TEXT PRIMARY KEY,
    club_source_id TEXT,
    name TEXT NOT NULL,
    date_of_birth DATE,
    nationality TEXT,
    source_position TEXT,
    market_value_eur BIGINT NOT NULL DEFAULT 0 CHECK (market_value_eur >= 0),
    market_value_as_of DATE,
    source_name TEXT,
    source_url TEXT,
    raw_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    fc27_player_id BIGINT,
    fc27_position TEXT,
    fc27_overall SMALLINT,
    fc27_potential SMALLINT,
    fc27_attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    baseline_age SMALLINT,
    baseline_position TEXT,
    baseline_overall SMALLINT,
    baseline_potential SMALLINT,
    baseline_market_value BIGINT,
    baseline_market_value_as_of DATE,
    baseline_market_value_source TEXT,
    baseline_weekly_wage BIGINT,
    baseline_contract_end DATE,
    baseline_attributes JSONB,
    baseline_profile_source TEXT,
    baseline_source_name TEXT,
    baseline_source_url TEXT,
    baseline_research JSONB,
    baseline_wage_source TEXT,
    baseline_model_version TEXT,
    baseline_captured_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT sm27_player_baseline_overall_check
        CHECK (baseline_overall IS NULL OR baseline_overall BETWEEN 1 AND 99),
    CONSTRAINT sm27_player_baseline_potential_check
        CHECK (baseline_potential IS NULL OR baseline_potential BETWEEN 1 AND 99),
    CONSTRAINT sm27_player_baseline_value_check
        CHECK (baseline_market_value IS NULL OR baseline_market_value >= 0),
    CONSTRAINT sm27_player_baseline_wage_check
        CHECK (baseline_weekly_wage IS NULL OR baseline_weekly_wage >= 0)
);

CREATE INDEX IF NOT EXISTS idx_sm27_player_baseline_club
    ON sm27_player_baseline_catalog(club_source_id);

INSERT INTO sm27_player_baseline_catalog (
    source_id,club_source_id,name,date_of_birth,nationality,source_position,
    market_value_eur,market_value_as_of,source_name,source_url,raw_data,
    fc27_player_id,fc27_position,fc27_overall,fc27_potential,fc27_attributes
)
SELECT wp.source_id,wp.club_source_id,wp.name,wp.date_of_birth,wp.nationality,wp.position,
       wp.market_value_eur,wp.market_value_as_of,wp.source_name,wp.source_url,wp.raw_data,
       wp.fc27_player_id,fc.position,fc.overall,fc.potential,coalesce(fc.attributes,'{}'::jsonb)
FROM world_player_catalog wp
LEFT JOIN fc27_player_catalog fc ON fc.ea_player_id=wp.fc27_player_id
ON CONFLICT (source_id) DO NOTHING;

-- This exact alias was missing from the source-to-EA matcher and previously generated 68 OVR.
UPDATE sm27_player_baseline_catalog
SET fc27_player_id=239053,
    fc27_position='CM',
    fc27_overall=87,
    fc27_potential=coalesce(fc27_potential,90),
    fc27_attributes='{"DEF":81,"DRI":81,"PAC":90,"PAS":83,"PHY":85,"SHO":84}'::jsonb,
    baseline_age=coalesce(baseline_age,extract(year FROM age(DATE '2026-07-01',date_of_birth))::smallint),
    baseline_position='CM',
    baseline_overall=87,
    baseline_potential=90,
    baseline_market_value=120000000,
    baseline_market_value_source='SM27 estimate',
    baseline_attributes='{"DEF":81,"DRI":81,"PAC":90,"PAS":83,"PHY":85,"SHO":84}'::jsonb,
    baseline_profile_source='EA SPORTS FC 27 official ratings database',
    baseline_source_name='EA FC 27',
    baseline_source_url='https://www.ea.com/games/ea-sports-fc/ratings/player-ratings/federico-valverde/239053',
    baseline_model_version='sm27-curated-valverde-baseline-v1',
    baseline_captured_at=coalesce(baseline_captured_at,now())
WHERE source_id='Q19509544';

-- Repair only the known incorrect fresh-career seed; never reset progressed saves.
UPDATE players p
SET overall=87,
    potential=90,
    position='CM',
    market_value=120000000,
    attributes='{"DEF":81,"DRI":81,"PAC":90,"PAS":83,"PHY":85,"SHO":84}'::jsonb,
    fc27_player_id=239053,
    source_name='EA FC 27',
    source_url='https://www.ea.com/games/ea-sports-fc/ratings/player-ratings/federico-valverde/239053',
    profile_source='EA SPORTS FC 27 official ratings database',
    market_value_source='SM27 estimate',
    original_data=coalesce(p.original_data,'{}'::jsonb) || jsonb_build_object(
        'sm27_baseline',jsonb_build_object(
            'overall',87,
            'potential',90,
            'market_value',120000000,
            'attributes','{"DEF":81,"DRI":81,"PAC":90,"PAS":83,"PHY":85,"SHO":84}'::jsonb,
            'captured_at_creation',true,
            'restored_from','EA FC 27 + SM27 player baseline catalog'
        ),
        'rating_source','EA SPORTS FC 27',
        'rating_is_official',true,
        'market_value_source','SM27 estimate'
    ),
    updated_at=now()
FROM game_states gs
WHERE gs.id=p.game_state_id
  AND gs.status='active'
  AND p.external_id='Q19509544'
  AND p.overall=68
  AND p.potential=70
  AND p.fc27_player_id IS NULL;
