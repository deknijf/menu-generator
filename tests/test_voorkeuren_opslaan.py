"""Tests voor _bewaar_voorkeuren in app/routes.py.

Sinds de voorkeuren op de accountpagina staan, stuurt het profielscherm ze niet
meer mee. Een ontbrekend veld moet dan "niet aangeraakt" betekenen; deed het dat
niet, dan wiste elk profielbewaring stilletjes iemands allergieen.
"""

import pytest

from app import routes


@pytest.fixture
def opgeslagen(monkeypatch):
    """Vangt op welke setters aangeroepen worden, zonder database."""
    gezien = {}
    monkeypatch.setattr(routes, "set_user_dislikes", lambda e, v: gezien.__setitem__("dislikes", v))
    monkeypatch.setattr(routes, "set_user_allergies", lambda e, v: gezien.__setitem__("allergies", v))
    monkeypatch.setattr(routes, "set_user_likes", lambda e, v: gezien.__setitem__("likes", v))
    return gezien


def test_ontbrekende_velden_worden_niet_aangeraakt(opgeslagen):
    routes._bewaar_voorkeuren("x@y.be", {"menu_mode": "custom_only"})
    assert opgeslagen == {}


def test_alleen_wat_meegestuurd_is_wordt_bewaard(opgeslagen):
    routes._bewaar_voorkeuren("x@y.be", {"allergies": ["Noten"]})
    assert opgeslagen == {"allergies": ["noten"]}


def test_een_leeg_lijstje_wist_wel_degelijk(opgeslagen):
    """Alles weghalen moet kunnen; dat is iets anders dan niets meesturen."""
    routes._bewaar_voorkeuren("x@y.be", {"dislikes": []})
    assert opgeslagen == {"dislikes": []}


def test_alle_drie_tegelijk(opgeslagen):
    routes._bewaar_voorkeuren(
        "x@y.be", {"dislikes": ["witloof"], "allergies": ["noten"], "likes": ["kip"]}
    )
    assert opgeslagen == {"dislikes": ["witloof"], "allergies": ["noten"], "likes": ["kip"]}


def test_komma_gescheiden_tekst_mag_ook(opgeslagen):
    routes._bewaar_voorkeuren("x@y.be", {"dislikes": "paddenstoelen, witloof"})
    assert opgeslagen == {"dislikes": ["paddenstoelen", "witloof"]}


def test_dubbels_en_lege_waarden_vallen_weg(opgeslagen):
    routes._bewaar_voorkeuren("x@y.be", {"likes": ["kip", "Kip", "", "  ", "vis"]})
    assert opgeslagen == {"likes": ["kip", "vis"]}
