"""Curated, source-linked estimates for real players absent from EA FC 27.

FotMob provides season performance context. The FC-style attributes and OVR/POT
below are SM27 estimates, never presented as official EA ratings.
"""
from __future__ import annotations

import re
import unicodedata


def _key(value: str) -> str:
    text = (value or "").replace("Đ", "Dj").replace("đ", "dj")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]", "", text.casefold())


def _profile(position, overall, potential, attributes, url, minutes, rating, goals, assists, **extra):
    market_value = extra.pop("market_value", None)
    sofascore_url = extra.pop("sofascore_url", None)
    return {
        "position": position,
        "overall": overall,
        "potential": potential,
        "attributes": attributes,
        "source_url": url,
        "market_value": market_value,
        "market_value_source": "SofaScore" if market_value is not None else "not_available",
        "market_value_as_of": "2026-11-22" if market_value is not None else None,
        "profile_source": f"SM27 researched estimate · FotMob {extra.get('season', '2026/27')} (not EA FC 27)",
        "research": {
            "source": "FotMob",
            "season": "2026/27",
            "league": "Russian Premier League",
            "minutes": minutes,
            "fotmob_rating": rating,
            "goals": goals,
            "assists": assists,
            "sofascore_url": sofascore_url,
            "attribute_method": "SM27 FC-style estimate informed by primary position, role, season output and published player traits; not EA data",
            **extra,
        },
    }


RESEARCHED_PLAYER_PROFILES = {
    "antonzinkovskiy": _profile(
        "LM", 73, 73, {"PAC": 75, "SHO": 70, "PAS": 70, "DRI": 75, "DEF": 45, "PHY": 62},
        "https://www.fotmob.com/players/785808/anton-zinkovskiy", 1698, 6.54, 3, 2,
        xg=1.44, xa=2.38, shots=32, chances_created=22, successful_dribbles=27,
        season="2025/26", role="Left midfielder / winger; SM27 researched estimate",
        market_value=2200000, sofascore_url="https://www.sofascore.com/football/player/anton-zinkovski/848073",
    ),
    "esequielbarco": _profile(
        "CAM", 80, 80, {"PAC": 76, "SHO": 75, "PAS": 82, "DRI": 85, "DEF": 43, "PHY": 62},
        "https://www.fotmob.com/players/789068/esequiel-barco", 770, 7.69, 2, 2,
        xg=1.83, xa=2.45, chances_created=29, pass_accuracy=85.7, successful_dribbles=5,
        market_value=16700000, sofascore_url="https://www.sofascore.com/football/player/ezequiel-barco/848473",
    ),
    "marquinhos": _profile(
        "LW", 80, 80, {"PAC": 86, "SHO": 73, "PAS": 78, "DRI": 85, "DEF": 40, "PHY": 64},
        "https://www.fotmob.com/players/857270/marquinhos", 927, 7.32, 1, 4,
        chances_created=32, x_a=3.1, touches=740, role="Left winger",
        market_value=8400000, sofascore_url="https://www.sofascore.com/football/player/marquinhos/885194",
    ),
    "pablosolari": _profile(
        "RW", 78, 79, {"PAC": 87, "SHO": 75, "PAS": 70, "DRI": 82, "DEF": 42, "PHY": 70},
        "https://www.fotmob.com/players/1201406/pablo-solari", 1140, 7.39, 3, 1,
        role="Right winger",
        market_value=8600000, sofascore_url="https://www.sofascore.com/football/player/pablo-solari/1018450",
    ),
    "gedsonfernandes": _profile(
        "RB", 79, 80, {"PAC": 79, "SHO": 68, "PAS": 76, "DRI": 78, "DEF": 75, "PHY": 79},
        "https://www.fotmob.com/players/747785/gedson-fernandes", 975, 7.38, 1, 1,
        tackles_per_90=2.6, role="Right back",
        market_value=19000000, sofascore_url="https://www.sofascore.com/football/player/gedson-fernandes/862055",
    ),
    "romanzobnin": _profile(
        "CM", 77, 77, {"PAC": 68, "SHO": 66, "PAS": 76, "DRI": 75, "DEF": 72, "PHY": 74},
        "https://www.fotmob.com/players/464304/roman-zobnin", 751, 7.31, 1, 1,
        roles=["CM", "CDM", "LB", "CAM"],
        market_value=2100000, sofascore_url="https://www.sofascore.com/football/player/roman-zobnin/138452",
    ),
    "aleksandarmaksimenko": _profile(
        "GK", 77, 78, {"DIV": 78, "HAN": 74, "KIC": 70, "REF": 78, "SPE": 69, "POS": 75},
        "https://www.fotmob.com/players/742481/aleksandar-maksimenko", 1097, 6.94, 0, 0,
        clean_sheets=5, goals_conceded=10, save_percentage=78.7,
        saves_per_90=3.0, goals_prevented=2.9,
        market_value=3900000, sofascore_url="https://www.sofascore.com/football/player/aleksandr-maksimenko/800905",
    ),
    "srdjanbabic": _profile(
        "CB", 76, 76, {"PAC": 55, "SHO": 44, "PAS": 66, "DRI": 61, "DEF": 80, "PHY": 79},
        "https://www.fotmob.com/players/540967/srdjan-babic", 898, 7.19, 0, 0,
        starts=11, role="Left-footed centre-back",
        market_value=4100000, sofascore_url="https://www.sofascore.com/football/player/sran-babic/280815",
    ),
    "alexanderdjiku": _profile(
        "CB", 76, 76, {"PAC": 70, "SHO": 50, "PAS": 66, "DRI": 66, "DEF": 78, "PHY": 77},
        "https://www.fotmob.com/players/407765/alexander-djiku", 477, 7.30, 0, 1,
        starts=5, clearances=24, role="Right-footed centre-back",
        market_value=3800000, sofascore_url="https://www.sofascore.com/football/player/alexander-djiku/289977",
    ),
    "ruslanlitvinov": _profile(
        "CDM", 76, 79, {"PAC": 67, "SHO": 55, "PAS": 78, "DRI": 70, "DEF": 78, "PHY": 79},
        "https://www.fotmob.com/players/1084160/ruslan-litvinov", 687, 7.29, 0, 1,
        role="Defensive midfielder / centre-back",
        market_value=5600000, sofascore_url="https://www.sofascore.com/football/player/ruslan-litvinov/919378",
    ),
    "nailumyarov": _profile(
        "CDM", 76, 78, {"PAC": 67, "SHO": 53, "PAS": 72, "DRI": 68, "DEF": 79, "PHY": 77},
        "https://www.fotmob.com/teams/8643/stats/spartak-moscow/players", 1247, 7.14, 0, 0,
        interceptions_per_90=2.2, role="Defensive midfielder",
        market_value=7200000, sofascore_url="https://www.sofascore.com/football/player/nail-umyarov/939507",
    ),
    "christopherwooh": _profile(
        "CB", 76, 81, {"PAC": 74, "SHO": 48, "PAS": 61, "DRI": 64, "DEF": 80, "PHY": 82},
        "https://www.fotmob.com/players/987142/christopher-wooh", 555, 7.11, 1, 0,
        defensive_contributions_per_90=11.7, clearances_per_90=6.5,
        tackles_per_90=2.6, interceptions_per_90=1.5,
        market_value=4800000, sofascore_url="https://www.sofascore.com/football/player/christopher-wooh/930231",
    ),
    "mirlinddaku": _profile(
        "ST", 76, 76, {"PAC": 73, "SHO": 79, "PAS": 59, "DRI": 68, "DEF": 34, "PHY": 78},
        "https://www.fotmob.com/players/1059398/mirlind-daku", 547, 6.96, 5, 1,
        aerial_duels_won=37.5, duels_won=40.6, defensive_contributions=13,
        market_value=10700000, sofascore_url="https://www.sofascore.com/football/player/mirlind-daku/970516",
    ),
    "danildenisov": _profile(
        "RB", 73, 78, {"PAC": 76, "SHO": 53, "PAS": 67, "DRI": 69, "DEF": 73, "PHY": 67},
        "https://www.fotmob.com/players/1172804/danil-denisov", 392, 6.66, 0, 1,
        tackles=4, interceptions=3, clearances=12, pass_accuracy=72.5,
        market_value=3900000, sofascore_url="https://www.sofascore.com/football/player/denisov-daniil/983539",
    ),
    "manfredugalde": _profile(
        "ST", 78, 82, {"PAC": 83, "SHO": 79, "PAS": 64, "DRI": 77, "DEF": 34, "PHY": 68},
        "https://www.fotmob.com/players/1016738/manfred-ugalde", 1078, 7.16, 6, 0,
        xg=6.1, role="Striker",
        market_value=12400000, sofascore_url="https://www.sofascore.com/football/player/manfred-ugalde/993560",
    ),
    "danilprutsev": _profile(
        "CDM", 75, 78, {"PAC": 70, "SHO": 69, "PAS": 72, "DRI": 71, "DEF": 69, "PHY": 75},
        "https://www.fotmob.com/players/880227/danil-prutsev", 230, 6.76, 2, 0,
        role="Defensive midfielder; limited league minutes",
    ),
    "victorparada": _profile(
        "CB", 73, 77, {"PAC": 78, "SHO": 48, "PAS": 65, "DRI": 67, "DEF": 71, "PHY": 69},
        "https://www.fotmob.com/players/1056071/victor-parada", 250, 6.61, 0, 0,
        role="Centre-back, left-footed; limited league minutes",
        market_value=3900000, sofascore_url="https://www.sofascore.com/football/player/victor-parada/985726",
    ),
    "igordmitriev": _profile(
        "LB", 73, 82, {"PAC": 83, "SHO": 55, "PAS": 69, "DRI": 77, "DEF": 63, "PHY": 62},
        "https://www.fotmob.com/players/1265176/igor-dmitriev", 224, 6.68, 0, 2,
        chances_created_per_90=0.47, tackles_per_90=3.2, role="Left-back / wing-back",
        market_value=3200000, sofascore_url="https://www.sofascore.com/football/player/dmitriev-igor/1509269",
    ),
    "ilyapomazun": _profile(
        "GK", 73, 73, {"DIV": 74, "HAN": 70, "KIC": 64, "REF": 74, "SPE": 65, "POS": 71},
        "https://www.fotmob.com/players/308232/ilya-pomazun", 159, 7.01, 0, 0,
        saves=5, save_percentage=83.3, goals_conceded=1, clean_sheets=1, goals_prevented=0.49,
        market_value=1000000, sofascore_url="https://www.sofascore.com/football/player/ilya-pomazun/223608",
    ),
    "christophermartins": _profile(
        "CM", 74, 74, {"PAC": 74, "SHO": 70, "PAS": 72, "DRI": 73, "DEF": 70, "PHY": 76},
        "https://www.fotmob.com/players/561200/christopher-martins", 137, 7.03, 1, 0,
        role="Central midfielder; limited league minutes",
        market_value=3800000, sofascore_url="https://www.sofascore.com/football/player/christopher-martins/227756",
    ),
}

ALIASES = {
    "daniildenisov": "danildenisov",
    "igordmitriyev": "igordmitriev",
    "christophermartinspereira": "christophermartins",
    "aleksandrmaksimenko": "aleksandarmaksimenko",
}


def get_researched_profile(name: str | None, club_name: str | None = None):
    key = _key(name or "")
    profile = RESEARCHED_PLAYER_PROFILES.get(ALIASES.get(key, key))
    if profile and club_name and "spartakmoscow" not in _key(club_name):
        return None
    return profile
