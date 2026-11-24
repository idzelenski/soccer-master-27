-- Rebalance player condition once for saves affected by the legacy club-wide condition update.
-- The exact legacy signature disappears after this update, so this remains idempotent on every startup.
WITH affected_saves AS (
    SELECT DISTINCT game_state_id
    FROM players
    WHERE form = 100 AND morale = 100 AND sharpness = 20 AND fatigue = 100
),
club_fixtures AS (
    SELECT
        f.game_state_id,
        f.home_club_id AS club_id,
        f.id AS fixture_id,
        row_number() OVER (
            PARTITION BY f.game_state_id, f.home_club_id
            ORDER BY f.match_date DESC, f.id DESC
        ) AS rn
    FROM fixtures f
    JOIN affected_saves a ON a.game_state_id = f.game_state_id
    WHERE f.status = 'completed'
    UNION ALL
    SELECT
        f.game_state_id,
        f.away_club_id AS club_id,
        f.id AS fixture_id,
        row_number() OVER (
            PARTITION BY f.game_state_id, f.away_club_id
            ORDER BY f.match_date DESC, f.id DESC
        ) AS rn
    FROM fixtures f
    JOIN affected_saves a ON a.game_state_id = f.game_state_id
    WHERE f.status = 'completed'
),
recent_minutes AS (
    SELECT
        p.id,
        count(cf.fixture_id)::int AS team_matches,
        coalesce(sum(coalesce(s.minutes_played, 0)), 0)::numeric AS minutes_played
    FROM players p
    JOIN affected_saves a ON a.game_state_id = p.game_state_id
    LEFT JOIN club_fixtures cf
      ON cf.game_state_id = p.game_state_id
     AND cf.club_id = p.club_id
     AND cf.rn <= 6
    LEFT JOIN fixture_player_stats s
      ON s.game_state_id = p.game_state_id
     AND s.fixture_id = cf.fixture_id
     AND s.player_id = p.id
    GROUP BY p.id
)
UPDATE players p
SET
    sharpness = least(100, greatest(25,
        35 + round(65.0 * least(1.0, rm.minutes_played / nullif(rm.team_matches * 90.0, 0)))::int
    )),
    morale = least(100, greatest(30,
        40 + round(60.0 * least(1.0, rm.minutes_played / nullif(rm.team_matches * 90.0, 0)))::int
    )),
    form = least(100, greatest(30,
        40 + round(60.0 * least(1.0, rm.minutes_played / nullif(rm.team_matches * 90.0, 0)))::int
    )),
    fatigue = least(75, greatest(0,
        round(45.0 * least(1.0, rm.minutes_played / nullif(rm.team_matches * 90.0, 0)))::int
    )),
    updated_at = now()
FROM recent_minutes rm
WHERE p.id = rm.id
  AND rm.team_matches > 0;
