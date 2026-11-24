from app.engine import expected_goals
from app.main import flag_for_nationality


def test_fifa_and_iso_codes_resolve_bulgarian_and_kosovo_flags():
    assert flag_for_nationality("BUL") == "bg"
    assert flag_for_nationality("BGR") == "bg"
    assert flag_for_nationality("KOS") == "xk"


def test_common_fifa_aliases_resolve_to_rectangular_flag_codes():
    expected = {
        "ENG": "gb-eng",
        "SCO": "gb-sct",
        "WAL": "gb-wls",
        "NIR": "gb-nir",
        "NED": "nl",
        "GER": "de",
        "SUI": "ch",
        "CRO": "hr",
        "GRE": "gr",
        "DEN": "dk",
        "CIV": "ci",
        "ALG": "dz",
        "CHI": "cl",
        "NIG": "ne",
        "NGR": "ng",
        "SER": "rs",
        "SLO": "si",
        "LIT": "lt",
    }
    for nationality, flag_code in expected.items():
        assert flag_for_nationality(nationality) == flag_code


def test_localised_country_names_resolve_to_flags():
    expected = {
        "España": "es",
        "Francia": "fr",
        "Brasil": "br",
        "Inglaterra": "gb-eng",
        "Turquía": "tr",
        "Países Bajos": "nl",
        "Alemania": "de",
        "Ucrania": "ua",
        "Holland": "nl",
        "Republic of Ireland": "ie",
        "Congo DR": "cd",
    }
    for nationality, flag_code in expected.items():
        assert flag_for_nationality(nationality) == flag_code


def test_club_reputation_gap_has_material_effect_on_expected_goals():
    favourite = expected_goals(83, 72, 78, 73)
    underdog = expected_goals(72, 83, 73, 78)
    assert favourite[0] > favourite[1]
    assert favourite[0] / favourite[1] > 1.5
    assert underdog[1] > underdog[0]
