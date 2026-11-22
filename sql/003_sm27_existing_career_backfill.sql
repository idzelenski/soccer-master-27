-- Upgrade already-created careers to SM27 player and club profile rules.
-- Idempotent: only legacy/gap fields are filled; existing sourced market values are preserved.

WITH base AS (
  SELECT p.*,
    CASE
      WHEN p.position='DF' THEN (ARRAY['CB','RB','LB','RWB','LWB'])[1 + get_byte(decode(substr(md5(coalesce(p.external_id,p.id::text)),1,2),'hex'),0) % 5]
      WHEN p.position='MF' THEN (ARRAY['CM','CDM','CAM','RM','LM'])[1 + get_byte(decode(substr(md5(coalesce(p.external_id,p.id::text)),1,2),'hex'),0) % 5]
      WHEN p.position='FW' THEN (ARRAY['ST','CF','RW','LW'])[1 + get_byte(decode(substr(md5(coalesce(p.external_id,p.id::text)),1,2),'hex'),0) % 4]
      ELSE p.position
    END AS new_position,
    get_byte(decode(substr(md5(coalesce(p.external_id,p.id::text)),3,2),'hex'),0) AS seed_byte
  FROM players p
  JOIN game_states gs ON gs.id=p.game_state_id
  WHERE gs.status='active'
), valued AS (
  SELECT *,
    CASE WHEN market_value>0 THEN market_value ELSE
      (round(greatest(25000,
        power(greatest(0,overall-35)::numeric,2)*12000 *
        CASE WHEN age<=21 THEN 1.22 WHEN age<=24 THEN 1.08 WHEN age<=29 THEN 1.0
             ELSE greatest(0.25,1.0-(age-29)*0.07) END *
        (1 + greatest(0,potential-overall)*0.012)
      ) / 10000.0) * 10000)::bigint
    END AS estimated_value
  FROM base
), enriched AS (
  SELECT *,
    CASE new_position
      WHEN 'GK' THEN ARRAY[]::text[]
      WHEN 'RB' THEN ARRAY['LB','RWB']::text[]
      WHEN 'LB' THEN ARRAY['RB','LWB']::text[]
      WHEN 'CB' THEN ARRAY['CDM']::text[]
      WHEN 'RWB' THEN ARRAY['RB','RM']::text[]
      WHEN 'LWB' THEN ARRAY['LB','LM']::text[]
      WHEN 'CDM' THEN ARRAY['CM','CB']::text[]
      WHEN 'CM' THEN ARRAY['CDM','CAM']::text[]
      WHEN 'CAM' THEN ARRAY['CM','CF']::text[]
      WHEN 'RM' THEN ARRAY['RW','CM']::text[]
      WHEN 'LM' THEN ARRAY['LW','CM']::text[]
      WHEN 'RW' THEN ARRAY['RM','ST']::text[]
      WHEN 'LW' THEN ARRAY['LM','ST']::text[]
      WHEN 'ST' THEN ARRAY['CF','LW']::text[]
      WHEN 'CF' THEN ARRAY['ST','CAM']::text[]
      ELSE ARRAY[]::text[]
    END AS new_secondary
  FROM valued
)
UPDATE players p SET
  position=e.new_position,
  secondary_positions=CASE WHEN cardinality(p.secondary_positions)=0 THEN e.new_secondary ELSE p.secondary_positions END,
  market_value=CASE WHEN p.market_value<=0 THEN e.estimated_value ELSE p.market_value END,
  weekly_wage=CASE WHEN p.weekly_wage<=0
    THEN greatest(250,least(1500000,round(e.estimated_value*0.00154/100)*100))::bigint
    ELSE p.weekly_wage END,
  contract_end=coalesce(p.contract_end,
    make_date(2028 + (e.seed_byte % CASE WHEN e.age>=34 THEN 2 WHEN e.age>=30 THEN 3 ELSE 5 END),6,30)),
  form=coalesce(p.form,50),
  morale=coalesce(p.morale,70),
  sharpness=coalesce(p.sharpness,85),
  profile_source=CASE WHEN p.market_value>0 AND p.data_verified_at IS NOT NULL
    THEN coalesce(p.profile_source,'Transfermarkt snapshot')
    ELSE 'SM27 estimate — no verified Transfermarkt value in source snapshot' END,
  attributes=CASE
    WHEN p.attributes ? 'PAC' OR p.attributes ? 'DIV' THEN p.attributes
    WHEN e.new_position='GK' THEN jsonb_build_object(
      'DIV',greatest(20,least(99,p.overall+1+(e.seed_byte%9)-4)),
      'HAN',greatest(20,least(99,p.overall+(e.seed_byte%7)-3)),
      'KIC',greatest(20,least(99,p.overall-3+(e.seed_byte%9)-4)),
      'REF',greatest(20,least(99,p.overall+4+(e.seed_byte%9)-4)),
      'SPE',greatest(20,least(99,p.overall-2+(e.seed_byte%9)-4)),
      'POS',greatest(20,least(99,p.overall+2+(e.seed_byte%9)-4)))
    ELSE jsonb_build_object(
      'PAC',greatest(20,least(99,p.overall+(CASE WHEN e.new_position IN ('ST','CF','RW','LW') THEN 3 WHEN e.new_position IN ('CB','RB','LB','RWB','LWB') THEN -1 ELSE 1 END)+(e.seed_byte%9)-4)),
      'SHO',greatest(20,least(99,p.overall+(CASE WHEN e.new_position IN ('ST','CF','RW','LW') THEN 6 WHEN e.new_position IN ('CB','RB','LB','RWB','LWB') THEN -7 ELSE -1 END)+(e.seed_byte%9)-4)),
      'PAS',greatest(20,least(99,p.overall+(CASE WHEN e.new_position IN ('CM','CDM','CAM','RM','LM') THEN 4 WHEN e.new_position IN ('CB','RB','LB','RWB','LWB') THEN 0 ELSE -3 END)+(e.seed_byte%9)-4)),
      'DRI',greatest(20,least(99,p.overall+(CASE WHEN e.new_position IN ('ST','CF','RW','LW') THEN 5 WHEN e.new_position IN ('CM','CDM','CAM','RM','LM') THEN 2 ELSE -4 END)+(e.seed_byte%9)-4)),
      'DEF',greatest(20,least(99,p.overall+(CASE WHEN e.new_position IN ('CB','RB','LB','RWB','LWB') THEN 7 WHEN e.new_position IN ('CM','CDM','CAM','RM','LM') THEN 0 ELSE -12 END)+(e.seed_byte%9)-4)),
      'PHY',greatest(20,least(99,p.overall+(CASE WHEN e.new_position IN ('CB','RB','LB','RWB','LWB') THEN 4 WHEN e.new_position IN ('ST','CF','RW','LW') THEN 1 ELSE -1 END)+(e.seed_byte%9)-4)))
  END,
  updated_at=now()
FROM enriched e
WHERE p.id=e.id
  AND (p.position IN ('DF','MF','FW') OR cardinality(p.secondary_positions)=0
       OR p.market_value<=0 OR p.weekly_wage<=0 OR p.contract_end IS NULL
       OR NOT (p.attributes ? 'PAC' OR p.attributes ? 'DIV'));

UPDATE clubs c
SET star_rating=p.fifa_stars,
    reputation=p.team_strength,
    logo_url=coalesce(p.logo_url,c.logo_url),
    updated_at=now()
FROM sm27_club_pool p
WHERE c.external_id=p.source_id
  AND c.game_state_id IN (SELECT id FROM game_states WHERE status='active');
