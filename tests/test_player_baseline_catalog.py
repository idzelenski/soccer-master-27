from pathlib import Path


def test_fede_valverde_short_name_matches_official_ea_name():
    from scripts.import_fc27_ratings import choose_match, match_candidates

    record = {
        "ea_player_id": 239053,
        "display_name": "Federico Valverde",
        "name_key": "federicovalverde",
        "first_name": "Federico",
        "last_name": "Valverde",
        "nationality_code": "URY",
        "club_name": "Real Madrid",
        "position": "CM",
        "overall": 87,
    }
    matched = choose_match("Fede Valverde", "Uruguay", "Real Madrid CF", "MF", match_candidates([record]))
    assert matched is not None
    assert matched["ea_player_id"] == 239053
    assert matched["overall"] == 87


def test_new_careers_read_frozen_baseline_catalog_and_cache_initial_values():
    source = Path("app/main.py").read_text(encoding="utf-8")
    create_save = source.split('@app.post("/api/saves")', 1)[1].split(
        '@app.post("/api/saves/restart")', 1
    )[0]
    assert "FROM sm27_player_baseline_catalog b" in create_save
    assert "FROM world_player_catalog wp" not in create_save
    assert "baseline_overall=coalesce(baseline_overall,%s)" in create_save
    assert "baseline_market_value=coalesce(baseline_market_value,%s)" in create_save
    assert "baseline_attributes=coalesce(baseline_attributes,%s)" in create_save


def test_baseline_migration_preserves_fede_valverde_official_starting_data():
    migration = Path("sql/006_player_baseline_catalog.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS sm27_player_baseline_catalog" in migration
    assert "source_id='Q19509544'" in migration
    assert "baseline_overall=87" in migration
    assert "baseline_potential=90" in migration
    assert "baseline_market_value=120000000" in migration
