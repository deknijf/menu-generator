"""Tests voor de boodschappenlijst-aggregatie in app/routes.py.

_build_shopping_items hangt aan twee DB-functies. Die worden hier vervangen, zodat
de aggregatie- en schaallogica geisoleerd getest wordt zonder data/app.db aan te raken.
"""

import pytest

from app import routes
from app.routes import _build_shopping_items, _normalize_ingredient_name, _normalize_unit


# --- Unitnormalisatie ---


@pytest.mark.parametrize(
    "hoeveelheid,unit,verwacht",
    [
        (500, "g", (500.0, "g")),
        (500, "gram", (500.0, "g")),
        (2, "kg", (2000.0, "g")),
        (2, "kilo", (2000.0, "g")),
        (250, "ml", (250.0, "ml")),
        (1, "l", (1000.0, "ml")),
        (1, "liter", (1000.0, "ml")),
        (2, "stuks", (2.0, "stuk")),
        (3, "el", (3.0, "eetlepel")),
        (1, "tbsp", (1.0, "eetlepel")),
        (2, "tl", (2.0, "theelepel")),
        (2, "cloves", (2.0, "teentje")),
        (1, "snufje", (1.0, "snufje")),
        (1, "zak", (1.0, "zak")),
    ],
)
def test_normalize_unit(hoeveelheid, unit, verwacht):
    assert _normalize_unit(hoeveelheid, unit) == verwacht


@pytest.mark.parametrize("unit", ["milliliter", "millilitre"])
def test_milliliter_wordt_niet_als_liter_gelezen(unit):
    """Regressie: 'liter' is een substring van 'milliliter'.

    Toen de liter-check eerst stond, werd 500 milliliter 500000 ml op de lijst.
    """
    assert _normalize_unit(500, unit) == (500.0, "ml")


@pytest.mark.parametrize(
    "invoer,verwacht",
    [
        ("chicken", "kipfilet"),
        ("kip", "kipfilet"),
        ("look", "knoflook"),
        ("garlic", "knoflook"),
        ("olive oil", "olijfolie"),
        ("ground beef", "rundergehakt"),
        ("  Tomaten  ", "tomaten"),
        ("onbekend ingredient", "onbekend ingredient"),
    ],
)
def test_normalize_ingredient_name(invoer, verwacht):
    assert _normalize_ingredient_name(invoer) == verwacht


# --- Aggregatie ---


@pytest.fixture
def shopping_env(monkeypatch):
    """Vervangt de twee DB-afhankelijkheden van _build_shopping_items.

    Geeft een helper terug die (dagplanning, recepten) instelt.
    """

    def _setup(dagen_naar_meal, recepten):
        monkeypatch.setattr(routes, "_recipe_map_for_user", lambda email: recepten)
        monkeypatch.setattr(
            routes,
            "get_day",
            lambda group_id, day: (
                {"meal_id": dagen_naar_meal[day]} if dagen_naar_meal.get(day) else None
            ),
        )

    return _setup


def _ingredient(naam, hoeveelheid, unit):
    return {"name": naam, "quantity": hoeveelheid, "unit": unit}


def test_zelfde_ingredient_over_meerdere_dagen_wordt_opgeteld(shopping_env):
    recept = {"id": "m1", "ingredients": [_ingredient("kipfilet", 300, "g")]}
    shopping_env({"2026-08-03": "m1", "2026-08-04": "m1"}, {"m1": recept})

    items = _build_shopping_items("x@y.be", 1, ["2026-08-03", "2026-08-04"], 2, 2)

    assert len(items) == 1
    assert items[0]["name"] == "kipfilet"
    assert items[0]["quantity"] == 600.0
    assert items[0]["unit"] == "g"


def test_hoeveelheden_schalen_met_aantal_personen(shopping_env):
    """Recepten leggen hoeveelheden vast voor base_servings; 4 personen verdubbelt."""
    recept = {"id": "m1", "ingredients": [_ingredient("kipfilet", 300, "g")]}
    shopping_env({"2026-08-03": "m1"}, {"m1": recept})

    items = _build_shopping_items("x@y.be", 1, ["2026-08-03"], 4, 2)

    assert items[0]["quantity"] == 600.0


def test_halve_portie_schaalt_naar_beneden(shopping_env):
    recept = {"id": "m1", "ingredients": [_ingredient("kipfilet", 300, "g")]}
    shopping_env({"2026-08-03": "m1"}, {"m1": recept})

    items = _build_shopping_items("x@y.be", 1, ["2026-08-03"], 1, 2)

    assert items[0]["quantity"] == 150.0


def test_eenheden_worden_genormaliseerd_voor_het_optellen(shopping_env):
    """1 kg + 500 g van hetzelfde ingredient hoort samen te vallen op 1500 g."""
    recept_a = {"id": "m1", "ingredients": [_ingredient("aardappelen", 1, "kg")]}
    recept_b = {"id": "m2", "ingredients": [_ingredient("aardappelen", 500, "g")]}
    shopping_env({"2026-08-03": "m1", "2026-08-04": "m2"}, {"m1": recept_a, "m2": recept_b})

    items = _build_shopping_items("x@y.be", 1, ["2026-08-03", "2026-08-04"], 2, 2)

    assert len(items) == 1
    assert items[0]["quantity"] == 1500.0
    assert items[0]["unit"] == "g"


def test_ingredientnamen_worden_genormaliseerd_voor_het_optellen(shopping_env):
    """'chicken' en 'kip' zijn allebei kipfilet en horen op één regel."""
    recept_a = {"id": "m1", "ingredients": [_ingredient("chicken", 200, "g")]}
    recept_b = {"id": "m2", "ingredients": [_ingredient("kip", 100, "g")]}
    shopping_env({"2026-08-03": "m1", "2026-08-04": "m2"}, {"m1": recept_a, "m2": recept_b})

    items = _build_shopping_items("x@y.be", 1, ["2026-08-03", "2026-08-04"], 2, 2)

    assert len(items) == 1
    assert items[0]["name"] == "kipfilet"
    assert items[0]["quantity"] == 300.0


def test_verschillende_eenheden_blijven_gescheiden(shopping_env):
    """Ingredienten in stuks en in gram kunnen niet opgeteld worden."""
    recept = {
        "id": "m1",
        "ingredients": [_ingredient("ui", 2, "stuk"), _ingredient("ui", 100, "g")],
    }
    shopping_env({"2026-08-03": "m1"}, {"m1": recept})

    items = _build_shopping_items("x@y.be", 1, ["2026-08-03"], 2, 2)

    assert len(items) == 2
    assert {item["unit"] for item in items} == {"stuk", "g"}


def test_dagen_zonder_maaltijd_worden_overgeslagen(shopping_env):
    recept = {"id": "m1", "ingredients": [_ingredient("kipfilet", 300, "g")]}
    shopping_env({"2026-08-03": "m1", "2026-08-04": None}, {"m1": recept})

    items = _build_shopping_items("x@y.be", 1, ["2026-08-03", "2026-08-04"], 2, 2)

    assert items[0]["quantity"] == 300.0


def test_onbekend_meal_id_wordt_overgeslagen(shopping_env):
    """Een verwijderd recept mag de lijst niet laten crashen."""
    shopping_env({"2026-08-03": "verdwenen"}, {})

    items = _build_shopping_items("x@y.be", 1, ["2026-08-03"], 2, 2)

    assert items == []


def test_lijst_is_alfabetisch_met_oplopende_sort_order(shopping_env):
    recept = {
        "id": "m1",
        "ingredients": [
            _ingredient("ui", 1, "stuk"),
            _ingredient("aardappelen", 500, "g"),
            _ingredient("kipfilet", 300, "g"),
        ],
    }
    shopping_env({"2026-08-03": "m1"}, {"m1": recept})

    items = _build_shopping_items("x@y.be", 1, ["2026-08-03"], 2, 2)

    assert [item["name"] for item in items] == ["aardappelen", "kipfilet", "ui"]
    assert [item["sort_order"] for item in items] == [0, 1, 2]


def test_nieuwe_items_staan_niet_afgevinkt(shopping_env):
    recept = {"id": "m1", "ingredients": [_ingredient("kipfilet", 300, "g")]}
    shopping_env({"2026-08-03": "m1"}, {"m1": recept})

    items = _build_shopping_items("x@y.be", 1, ["2026-08-03"], 2, 2)

    assert all(item["checked"] is False for item in items)
