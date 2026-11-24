-- SM27 migration 005: explainable player availability and current Italian crests.
ALTER TABLE players ADD COLUMN IF NOT EXISTS suspension_reason TEXT;
ALTER TABLE players ADD COLUMN IF NOT EXISTS suspension_return_date DATE;
ALTER TABLE player_competition_discipline ADD COLUMN IF NOT EXISTS suspension_reason TEXT;
ALTER TABLE player_competition_discipline ADD COLUMN IF NOT EXISTS suspension_return_date DATE;

UPDATE player_competition_discipline
SET suspension_reason = CASE
    WHEN suspension_matches > 0 AND red_cards > 0 THEN 'Красная карточка'
    WHEN suspension_matches > 0 AND yellow_cards >= 5 THEN 'Пятая жёлтая карточка в турнире'
    ELSE suspension_reason
END
WHERE suspension_matches > 0 AND suspension_reason IS NULL;

UPDATE players p
SET suspension_reason = d.suspension_reason
FROM player_competition_discipline d
WHERE d.game_state_id=p.game_state_id AND d.player_id=p.id
  AND d.suspension_matches>0 AND p.suspension_matches>0
  AND p.suspension_reason IS NULL;

-- Backfill the next eligible date for existing bans using the affected competition's fixture list.
UPDATE player_competition_discipline d
SET suspension_return_date = (
    SELECT f.match_date::date
    FROM fixtures f
    JOIN players p ON p.id=d.player_id
    JOIN game_states gs ON gs.id=d.game_state_id
    WHERE f.game_state_id=d.game_state_id
      AND f.tournament_id=d.tournament_id
      AND f.season=d.season
      AND f.status='scheduled'
      AND f.match_date::date>gs.game_date::date
      AND (f.home_club_id=p.club_id OR f.away_club_id=p.club_id)
    ORDER BY f.match_date
    OFFSET d.suspension_matches
    LIMIT 1
)
WHERE d.suspension_matches>0 AND d.suspension_return_date IS NULL;

UPDATE players p
SET suspension_return_date = d.suspension_return_date
FROM player_competition_discipline d
WHERE d.game_state_id=p.game_state_id AND d.player_id=p.id
  AND d.suspension_matches>0 AND p.suspension_matches>0
  AND d.suspension_return_date IS NOT NULL
  AND p.suspension_return_date IS NULL;

-- Current AS Roma 2025+ crest and current S.S. Lazio eagle/shield crest.
UPDATE world_club_catalog
SET logo_url='https://www.footylogos.com/downloads/logo/roma-logo-footylogos.svg',
    logo_source='FootyLogos current AS Roma crest 2025; rights remain with club'
WHERE lower(name) IN ('as roma','roma');

UPDATE sm27_club_pool
SET logo_url='https://www.footylogos.com/downloads/logo/roma-logo-footylogos.svg',
    logo_license='FootyLogos current crest reference; rights remain with club'
WHERE lower(club_name) IN ('as roma','roma');

UPDATE clubs
SET logo_url='https://www.footylogos.com/downloads/logo/roma-logo-footylogos.svg',updated_at=now()
WHERE lower(name) IN ('as roma','roma');

UPDATE world_club_catalog
SET logo_url='https://www.footylogos.com/downloads/logo/lazio-logo-footylogos.png',
    logo_source='FootyLogos current S.S. Lazio crest; rights remain with club'
WHERE lower(name) IN ('ss lazio','s.s. lazio','lazio');

UPDATE sm27_club_pool
SET logo_url='https://www.footylogos.com/downloads/logo/lazio-logo-footylogos.png',
    logo_license='FootyLogos current crest reference; rights remain with club'
WHERE lower(club_name) IN ('ss lazio','s.s. lazio','lazio');

UPDATE clubs
SET logo_url='https://www.footylogos.com/downloads/logo/lazio-logo-footylogos.png',updated_at=now()
WHERE lower(name) IN ('ss lazio','s.s. lazio','lazio');
