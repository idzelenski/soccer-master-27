-- Remove the legacy trigger that silently assigned secondary positions and emoji flags.
DROP TRIGGER IF EXISTS trg_sm27_enrich_player_profile ON players;
DROP FUNCTION IF EXISTS sm27_enrich_player_profile();

-- Persist one-time backfill state and the FC 27 import state used by the app lifespan.
CREATE TABLE IF NOT EXISTS sm27_migration_flags (
    migration_key TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS fc27_import_state (
    import_key TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'pending',
    attempted_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    error_message TEXT
);

WITH applied AS (
    INSERT INTO sm27_migration_flags (migration_key)
    VALUES ('005_disable_legacy_player_enrichment')
    ON CONFLICT (migration_key) DO NOTHING
    RETURNING 1
)
UPDATE players p
SET secondary_positions=ARRAY[]::text[],
    nationality_flag=NULL,
    market_value=CASE WHEN p.original_data->>'market_value_source'='SofaScore' THEN coalesce(p.market_value,0) ELSE 0 END,
    weekly_wage=CASE
        WHEN lower(trim(p.name))='cristiano ronaldo' THEN 53000
        WHEN lower(trim(p.name)) IN ('iñigo martínez','inigo martinez') THEN 245000
        WHEN p.original_data->>'generated'='true'
            THEN greatest(250,least(2500,round((p.overall*14+greatest(0,82-coalesce(p.age,24))*8)/50.0)*50))::bigint
        ELSE greatest(
            250,
            least(
                1500000,
                round((
                    600 * exp((greatest(35,least(95,p.overall))-60)::numeric*0.21)
                    * CASE
                        WHEN coalesce(p.age,24)<=22 THEN 0.55
                        WHEN coalesce(p.age,24)<=25 THEN 0.75
                        WHEN coalesce(p.age,24)<=29 THEN 1.0
                        WHEN coalesce(p.age,24)<=34 THEN 1.20
                        WHEN coalesce(p.age,24)<=37 THEN 1.45
                        WHEN coalesce(p.age,24)<=40 THEN 0.90
                        ELSE 0.25
                      END
                    * (0.70 + greatest(10,least(100,coalesce(c.reputation,50)))*0.0175)
                ) / 100.0) * 100
            )
        )::bigint
    END,
    position_training_target=NULL,
    position_training_progress=0,
    updated_at=now()
FROM clubs c
WHERE c.id=p.club_id
  AND EXISTS (SELECT 1 FROM applied);

-- Keep rating and value provenance correct after the legacy backfill runs.
UPDATE players p
SET profile_source=CASE
        WHEN p.original_data->>'generated'='true' THEN 'SM27 generated academy player — fictional'
        WHEN p.fc27_player_id IS NOT NULL THEN 'EA SPORTS FC 27 Ratings Database (snapshot 2026-09-10)'
        ELSE 'SM27 estimate — player not matched in FC 27 ratings database'
    END,
    market_value_source=CASE
        WHEN p.original_data->>'market_value_source'='SofaScore' THEN 'SofaScore'
        ELSE 'not_available'
    END,
    original_data=coalesce(p.original_data,'{}'::jsonb) || jsonb_build_object(
        'rating_source',CASE WHEN p.fc27_player_id IS NOT NULL THEN 'EA SPORTS FC 27' ELSE 'SM27 estimate' END,
        'rating_is_official',p.fc27_player_id IS NOT NULL,
        'market_value_source',CASE
            WHEN p.original_data->>'market_value_source'='SofaScore' THEN 'SofaScore'
            ELSE 'not_available'
        END
    ),
    updated_at=now()
WHERE p.profile_source IS DISTINCT FROM CASE
        WHEN p.original_data->>'generated'='true' THEN 'SM27 generated academy player — fictional'
        WHEN p.fc27_player_id IS NOT NULL THEN 'EA SPORTS FC 27 Ratings Database (snapshot 2026-09-10)'
        ELSE 'SM27 estimate — player not matched in FC 27 ratings database'
    END
   OR p.market_value_source IS DISTINCT FROM CASE
        WHEN p.original_data->>'market_value_source'='SofaScore' THEN 'SofaScore'
        ELSE 'not_available'
    END
   OR p.original_data->>'rating_source' IS DISTINCT FROM
        CASE WHEN p.fc27_player_id IS NOT NULL THEN 'EA SPORTS FC 27' ELSE 'SM27 estimate' END;
