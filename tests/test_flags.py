import pycountry

from app.main import flag_for_nationality


def test_every_iso_country_code_resolves_to_a_flag():
    countries = list(pycountry.countries)
    assert len(countries) >= 240
    for country in countries:
        assert flag_for_nationality(country.alpha_2) == country.alpha_2.lower()
        assert flag_for_nationality(country.alpha_3) == country.alpha_2.lower()


def test_localized_and_source_generated_nationalities_resolve():
    expected = {
        "Équateur": "ec",
        "Géorgie": "ge",
        "États-Unis": "us",
        "Islande": "is",
        "Drapeau de la France": "fr",
        "Drapeau de l'Angleterre": "gb-eng",
        "Drapeau de la République populaire de Chine": "cn",
        "Nigéria": "ng",
        "République centrafricaine": "cf",
        "RD Congo": "cd",
    }
    for nationality, code in expected.items():
        assert flag_for_nationality(nationality) == code


def test_turkish_catalog_nationalities_resolve_to_rectangular_flag_codes():
    assert flag_for_nationality("Almanya") == "de"
    assert flag_for_nationality("Belçika") == "be"
    assert flag_for_nationality("İtalya") == "it"
    assert flag_for_nationality("Türkiye") == "tr"
