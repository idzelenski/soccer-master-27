-- SM27 match center, transfer valuation, tournament badges and player discipline.
-- Every change is additive/idempotent. Historical scores and fixture dates are never rewritten.

ALTER TABLE public.tournaments
    ADD COLUMN IF NOT EXISTS logo_url text;

ALTER TABLE public.players
    ADD COLUMN IF NOT EXISTS suspension_matches smallint NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS public.fixture_player_stats (
    game_state_id uuid NOT NULL REFERENCES public.game_states(id) ON DELETE CASCADE,
    fixture_id uuid NOT NULL REFERENCES public.fixtures(id) ON DELETE CASCADE,
    tournament_id uuid REFERENCES public.tournaments(id) ON DELETE SET NULL,
    club_id uuid NOT NULL REFERENCES public.clubs(id) ON DELETE CASCADE,
    player_id uuid NOT NULL REFERENCES public.players(id) ON DELETE CASCADE,
    minutes_played smallint NOT NULL DEFAULT 0 CHECK (minutes_played BETWEEN 0 AND 130),
    rating numeric(3,1) NOT NULL CHECK (rating BETWEEN 0 AND 10),
    goals smallint NOT NULL DEFAULT 0,
    assists smallint NOT NULL DEFAULT 0,
    shots smallint NOT NULL DEFAULT 0,
    shots_on_target smallint NOT NULL DEFAULT 0,
    passes smallint NOT NULL DEFAULT 0,
    accurate_passes smallint NOT NULL DEFAULT 0,
    tackles smallint NOT NULL DEFAULT 0,
    interceptions smallint NOT NULL DEFAULT 0,
    key_passes smallint NOT NULL DEFAULT 0,
    yellow_cards smallint NOT NULL DEFAULT 0,
    red_cards smallint NOT NULL DEFAULT 0,
    saves smallint NOT NULL DEFAULT 0,
    clean_sheet boolean NOT NULL DEFAULT false,
    is_mvp boolean NOT NULL DEFAULT false,
    is_estimate boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (fixture_id, player_id)
);

CREATE INDEX IF NOT EXISTS fixture_player_stats_competition_idx
    ON public.fixture_player_stats (game_state_id, tournament_id, player_id);
CREATE INDEX IF NOT EXISTS fixture_player_stats_team_idx
    ON public.fixture_player_stats (fixture_id, club_id);
CREATE INDEX IF NOT EXISTS fixture_player_stats_mvp_idx
    ON public.fixture_player_stats (game_state_id, tournament_id, is_mvp)
    WHERE is_mvp = true;

CREATE TABLE IF NOT EXISTS public.player_competition_discipline (
    game_state_id uuid NOT NULL REFERENCES public.game_states(id) ON DELETE CASCADE,
    tournament_id uuid NOT NULL REFERENCES public.tournaments(id) ON DELETE CASCADE,
    season text NOT NULL,
    player_id uuid NOT NULL REFERENCES public.players(id) ON DELETE CASCADE,
    yellow_cards smallint NOT NULL DEFAULT 0,
    red_cards smallint NOT NULL DEFAULT 0,
    suspension_matches smallint NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (game_state_id, tournament_id, season, player_id)
);

CREATE INDEX IF NOT EXISTS player_competition_discipline_player_idx
    ON public.player_competition_discipline (game_state_id, player_id, season);

-- Real competition images. Wikimedia Commons Special:FilePath redirects to the original asset.
UPDATE public.tournaments
SET logo_url = CASE
    WHEN lower(name) LIKE '%russian premier%' OR lower(code) LIKE '%rus%' THEN
      'https://fc-ural.ru/uploads/main/01d/a5b552980d57e977e8e3ab4d4c175d7f672e1ac8822ad6cc2892ff7a2f25f387/mir_rpl_01.png'
    WHEN lower(name) LIKE '%premier league%' AND (lower(country) LIKE '%royaume%' OR lower(country) LIKE '%kingdom%' OR lower(code) LIKE '%eng%') THEN
      'https://commons.wikimedia.org/wiki/Special:FilePath/Pl-logo-light.svg'
    WHEN lower(name) LIKE '%la liga%' OR lower(name) LIKE '%laliga%' THEN
      'https://commons.wikimedia.org/wiki/Special:FilePath/LaLiga%20logo%202023.svg'
    WHEN lower(name) LIKE '%saudi pro%' THEN
      'https://commons.wikimedia.org/wiki/Special:FilePath/Saudi%20Pro%20League%20Logo.svg'
    WHEN lower(name) LIKE '%champions league%' THEN
      'https://commons.wikimedia.org/wiki/Special:FilePath/UEFA%20Champions%20League%20logo.svg'
    WHEN lower(name) LIKE '%conference league%' THEN
      'https://commons.wikimedia.org/wiki/Special:FilePath/UEFA%20Conference%20League%20logo.svg'
    WHEN lower(name) LIKE '%europa league%' THEN
      'https://commons.wikimedia.org/wiki/Special:FilePath/Europa%20League%202021.svg'
    WHEN lower(name) LIKE '%bundesliga%' THEN
      'https://commons.wikimedia.org/wiki/Special:FilePath/Bundesliga%20logo.svg'
    WHEN lower(name) LIKE '%serie a%' THEN
      'https://commons.wikimedia.org/wiki/Special:FilePath/Serie%20A%20logo%202022.svg'
    WHEN lower(name) LIKE '%ligue 1%' THEN
      'https://commons.wikimedia.org/wiki/Special:FilePath/Ligue%201%20McDonald%27s%20logo.svg'
    WHEN lower(name) LIKE '%eredivisie%' THEN
      'https://commons.wikimedia.org/wiki/Special:FilePath/Eredivisie%20nieuw%20logo%202017-.svg'
    WHEN lower(name) LIKE '%primeira liga%' OR lower(name) LIKE '%liga portugal%' THEN
      'https://commons.wikimedia.org/wiki/Special:FilePath/Liga%20Portugal%20Betclic%20logo.svg'
    WHEN lower(name) LIKE '%major league soccer%' OR lower(name) = 'mls' THEN
      'https://commons.wikimedia.org/wiki/Special:FilePath/Major%20League%20Soccer%20Crest%20Logo%20Black%20Transparent%202024.svg'
    WHEN lower(name) LIKE '%campeonato brasileiro%' OR lower(name) LIKE '%série a%' THEN
      'https://commons.wikimedia.org/wiki/Special:FilePath/Campeonato_Brasileiro_S%C3%A9rie_A_logo_%282026%29.svg'
    WHEN lower(name) LIKE '%liga profesional%' OR lower(name) LIKE '%primera división%' THEN
      'https://commons.wikimedia.org/wiki/Special:FilePath/Liga_Profesional_de_F%C3%BAtbol_%28Argentina%29_wordmark.svg'
    WHEN lower(name) LIKE '%championship%' THEN
      'https://commons.wikimedia.org/wiki/Special:FilePath/EFL_Championship_Wordmark.svg'
    WHEN lower(name) LIKE '%j1 league%' OR lower(name) LIKE '%j league%' THEN
      'https://commons.wikimedia.org/wiki/Special:FilePath/J1_league_logo_2026.svg'
    ELSE logo_url
END
WHERE logo_url IS NULL OR logo_url = '';

-- Backfill zero/unknown transfer fees. Existing SofaScore/Transfermarkt values are untouched.
WITH values_to_set AS (
    SELECT
        p.id,
        c.league,
        c.country,
        p.age,
        p.overall,
        p.potential,
        CASE
          WHEN p.position = 'GK' THEN (
            SELECT avg((v.value #>> '{}')::numeric)
            FROM jsonb_each(coalesce(p.attributes, '{}'::jsonb)) v
            WHERE v.key = ANY(ARRAY['DIV','HAN','REF','POS','KIC','SPE'])
              AND (v.value #>> '{}') ~ '^[0-9]+([.][0-9]+)?$'
          )
          ELSE (
            SELECT avg((v.value #>> '{}')::numeric)
            FROM jsonb_each(coalesce(p.attributes, '{}'::jsonb)) v
            WHERE v.key = ANY(ARRAY['PAC','SHO','PAS','DRI','DEF','PHY'])
              AND (v.value #>> '{}') ~ '^[0-9]+([.][0-9]+)?$'
          )
        END AS trait_average
    FROM public.players p
    JOIN public.clubs c ON c.id = p.club_id
    WHERE p.market_value = 0
),
estimated AS (
    SELECT id,
        round(
          greatest(10000, least(200000000,
            25000 * exp((greatest(35, least(99, overall)) - 45) * 0.16)
            * CASE
                WHEN lower(coalesce(league,'')) LIKE '%premier league%' AND
                     (lower(coalesce(country,'')) LIKE '%royaume%' OR lower(coalesce(country,'')) LIKE '%kingdom%') THEN 1.40
                WHEN lower(coalesce(league,'')) LIKE '%la liga%' OR lower(coalesce(league,'')) LIKE '%laliga%' THEN 1.23
                WHEN lower(coalesce(league,'')) LIKE '%bundesliga%' THEN 1.20
                WHEN lower(coalesce(league,'')) LIKE '%serie a%' THEN 1.16
                WHEN lower(coalesce(league,'')) LIKE '%ligue 1%' THEN 1.12
                WHEN lower(coalesce(league,'')) LIKE '%russian premier%' THEN 0.78
                WHEN lower(coalesce(league,'')) LIKE '%saudi%' THEN 0.92
                WHEN lower(coalesce(league,'')) LIKE '%championship%' THEN 0.72
                ELSE 0.86
              END
            * CASE
                WHEN coalesce(age,24) <= 19 THEN 1.58
                WHEN coalesce(age,24) <= 21 THEN 1.45
                WHEN coalesce(age,24) <= 23 THEN 1.28
                WHEN coalesce(age,24) <= 25 THEN 1.12
                WHEN coalesce(age,24) <= 29 THEN 1.00
                WHEN coalesce(age,24) = 30 THEN 0.88
                WHEN coalesce(age,24) = 31 THEN 0.76
                WHEN coalesce(age,24) = 32 THEN 0.64
                WHEN coalesce(age,24) = 33 THEN 0.52
                WHEN coalesce(age,24) <= 35 THEN 0.40
                ELSE 0.28
              END
            * (1 + greatest(0, coalesce(potential,overall)-coalesce(overall,60)) *
               CASE WHEN coalesce(age,24) >= 27 THEN 0.018 ELSE 0.026 END)
            * greatest(0.82, least(1.16, 0.78 + coalesce(trait_average,overall,60) / 280))
          )) / 10000) * 10000 AS market_value
    FROM values_to_set
)
UPDATE public.players p
SET market_value = e.market_value::bigint,
    market_value_source = 'SM27 estimate',
    original_data = coalesce(p.original_data, '{}'::jsonb) ||
      jsonb_build_object(
        'market_value_source', 'SM27 estimate',
        'market_value_model', 'league-age-ovr-potential-attributes-v1'
      ),
    updated_at = now()
FROM estimated e
WHERE p.id = e.id AND p.market_value = 0;

-- Legacy games predate player ratings and detailed team stats. Reconstruct estimates,
-- explicitly marked as estimates, without changing a score, fixture date or match event.
WITH participants AS (
    SELECT
        f.id AS fixture_id,
        f.game_state_id,
        f.tournament_id,
        f.home_club_id,
        f.away_club_id,
        f.home_score,
        f.away_score,
        p.club_id,
        p.id AS player_id,
        p.position,
        p.overall,
        row_number() OVER (
          PARTITION BY f.id, p.club_id
          ORDER BY CASE WHEN p.id = ANY(coalesce(t.starting_xi, ARRAY[]::uuid[])) THEN 0 ELSE 1 END,
                   p.overall DESC, p.id
        ) AS squad_rank
    FROM public.fixtures f
    JOIN public.players p
      ON p.game_state_id = f.game_state_id
     AND p.club_id IN (f.home_club_id, f.away_club_id)
    LEFT JOIN public.tactics t
      ON t.game_state_id = p.game_state_id AND t.club_id = p.club_id
    WHERE f.status = 'completed'
      AND NOT EXISTS (
        SELECT 1 FROM public.fixture_player_stats existing
        WHERE existing.fixture_id=f.id
      )
),
event_stats AS (
    SELECT fixture_id, player_id,
           count(*) FILTER (WHERE event_type IN ('goal','penalty_goal'))::smallint AS goals,
           count(*) FILTER (WHERE event_type = 'yellow_card')::smallint AS yellow_cards,
           count(*) FILTER (WHERE event_type = 'red_card')::smallint AS red_cards
    FROM public.match_events
    GROUP BY fixture_id, player_id
),
assist_stats AS (
    SELECT fixture_id, assist_player_id AS player_id, count(*)::smallint AS assists
    FROM public.match_events
    WHERE assist_player_id IS NOT NULL
    GROUP BY fixture_id, assist_player_id
),
base AS (
    SELECT
        x.*,
        coalesce(e.goals,0)::smallint AS goals,
        coalesce(a.assists,0)::smallint AS assists,
        coalesce(e.yellow_cards,0)::smallint AS yellow_cards,
        coalesce(e.red_cards,0)::smallint AS red_cards,
        CASE
          WHEN x.position = 'GK' THEN 30 + abs(hashtext(x.fixture_id::text || x.player_id::text)) % 14
          WHEN x.position IN ('CB','LB','RB','LWB','RWB') THEN 46 + abs(hashtext(x.fixture_id::text || x.player_id::text)) % 26
          WHEN x.position IN ('CDM','CM','CAM','LM','RM') THEN 48 + abs(hashtext(x.fixture_id::text || x.player_id::text)) % 35
          ELSE 24 + abs(hashtext(x.fixture_id::text || x.player_id::text)) % 24
        END::smallint AS passes,
        (1 + abs(hashtext(x.fixture_id::text || x.player_id::text)) % 4)::smallint AS base_shots
    FROM participants x
    LEFT JOIN event_stats e ON e.fixture_id = x.fixture_id AND e.player_id = x.player_id
    LEFT JOIN assist_stats a ON a.fixture_id = x.fixture_id AND a.player_id = x.player_id
    WHERE x.squad_rank <= 11
),
rated AS (
    SELECT
        b.*,
        greatest(4.5, least(9.8,
          6.1 + (coalesce(overall,60)-65) * 0.035 + goals * 0.72 + assists * 0.38
          + CASE WHEN position = 'GK' AND
              ((club_id = home_club_id AND away_score = 0) OR (club_id = away_club_id AND home_score = 0))
            THEN 0.35 ELSE 0 END
          - yellow_cards * 0.18 - red_cards * 0.9
          + ((abs(hashtext(fixture_id::text || player_id::text || 'rating')) % 41) - 20) / 100.0
        ))::numeric(3,1) AS rating
    FROM base b
),
ranked AS (
    SELECT r.*,
           row_number() OVER (PARTITION BY fixture_id ORDER BY rating DESC, player_id) AS mvp_rank
    FROM rated r
)
INSERT INTO public.fixture_player_stats (
    game_state_id, fixture_id, tournament_id, club_id, player_id, minutes_played,
    rating, goals, assists, shots, shots_on_target, passes, accurate_passes,
    tackles, interceptions, key_passes, yellow_cards, red_cards, saves,
    clean_sheet, is_mvp, is_estimate
)
SELECT
    r.game_state_id, r.fixture_id, r.tournament_id, r.club_id, r.player_id, 90,
    r.rating, r.goals, r.assists,
    greatest(r.goals, r.base_shots)::smallint,
    least(greatest(r.goals,r.base_shots), r.goals + abs(hashtext(r.fixture_id::text || r.player_id::text || 'sot')) % 3)::smallint,
    r.passes,
    round(r.passes * (0.76 + (abs(hashtext(r.fixture_id::text || r.player_id::text || 'acc')) % 15) / 100.0))::smallint,
    (abs(hashtext(r.fixture_id::text || r.player_id::text || 'tackle')) % 5)::smallint,
    (abs(hashtext(r.fixture_id::text || r.player_id::text || 'intercept')) % 4)::smallint,
    (abs(hashtext(r.fixture_id::text || r.player_id::text || 'key')) % 3)::smallint,
    r.yellow_cards, r.red_cards,
    CASE WHEN r.position='GK' THEN
      greatest(0, (CASE WHEN r.club_id = r.home_club_id THEN r.away_score ELSE r.home_score END) + 1
        + abs(hashtext(r.fixture_id::text || r.player_id::text || 'save')) % 5)
      ELSE 0 END::smallint,
    (r.position='GK' AND ((r.club_id=r.home_club_id AND r.away_score=0) OR
      (r.club_id=r.away_club_id AND r.home_score=0))),
    (r.mvp_rank=1),
    true
FROM ranked r
ON CONFLICT (fixture_id, player_id) DO NOTHING;

UPDATE public.fixtures f
SET notes = coalesce(f.notes, '{}'::jsonb) || jsonb_build_object(
  'match', jsonb_build_object(
    'version', 1,
    'historical_estimate', true,
    'mvp_player_id', (
      SELECT s.player_id::text FROM public.fixture_player_stats s
      WHERE s.fixture_id=f.id AND s.is_mvp=true LIMIT 1
    ),
    'home', jsonb_build_object(
      'shots', coalesce(f.home_shots,0),
      'shots_on_target', coalesce(f.home_shots_on_target,0),
      'passes', 340 + abs(hashtext(f.id::text || 'homepass')) % 180,
      'pass_accuracy', round((79 + abs(hashtext(f.id::text || 'homeacc')) % 13)::numeric,1),
      'yellow_cards', (SELECT count(*) FROM public.match_events e WHERE e.fixture_id=f.id AND e.club_id=f.home_club_id AND e.event_type='yellow_card'),
      'red_cards', (SELECT count(*) FROM public.match_events e WHERE e.fixture_id=f.id AND e.club_id=f.home_club_id AND e.event_type='red_card'),
      'offsides', abs(hashtext(f.id::text || 'homeoff')) % 5,
      'corners', 2 + abs(hashtext(f.id::text || 'homecorner')) % 8,
      'fouls', 7 + abs(hashtext(f.id::text || 'homefoul')) % 13
    ),
    'away', jsonb_build_object(
      'shots', coalesce(f.away_shots,0),
      'shots_on_target', coalesce(f.away_shots_on_target,0),
      'passes', 340 + abs(hashtext(f.id::text || 'awaypass')) % 180,
      'pass_accuracy', round((79 + abs(hashtext(f.id::text || 'awayacc')) % 13)::numeric,1),
      'yellow_cards', (SELECT count(*) FROM public.match_events e WHERE e.fixture_id=f.id AND e.club_id=f.away_club_id AND e.event_type='yellow_card'),
      'red_cards', (SELECT count(*) FROM public.match_events e WHERE e.fixture_id=f.id AND e.club_id=f.away_club_id AND e.event_type='red_card'),
      'offsides', abs(hashtext(f.id::text || 'awayoff')) % 5,
      'corners', 2 + abs(hashtext(f.id::text || 'awaycorner')) % 8,
      'fouls', 7 + abs(hashtext(f.id::text || 'awayfoul')) % 13
    )
  )
)
WHERE f.status='completed' AND NOT (coalesce(f.notes, '{}'::jsonb) ? 'match');
