"""Tests voor app/nutrition.py: de kcal-schatting per portie."""

import pytest

from app.nutrition import bereken_kcal, gram_van, kcal_per_100g, normaliseer


# --- Naam opzoeken ---


@pytest.mark.parametrize(
    "naam,verwacht",
    [
        ("kipfilet", 165),
        ("Kipfilet, in blokjes", 165),
        ("verse kipfilet", 165),
        ("olijfolie", 884),
        ("frietaardappelen", 77),          # samenstelling met "aardappel"
        ("kipfilets", 165),                # meervoud
    ],
)
def test_kcal_opzoeken(naam, verwacht):
    assert kcal_per_100g(naam) == verwacht


def test_langste_treffer_wint():
    """"zoete aardappel" mag niet op "aardappel" uitkomen."""
    assert kcal_per_100g("zoete aardappel") == 86
    assert kcal_per_100g("aardappel") == 77


def test_onbekend_ingredient_geeft_none():
    assert kcal_per_100g("ruimtevaartsoep met sterrenstof") is None


def test_normaliseer_haalt_ruis_weg():
    assert normaliseer("Verse kipfilet, fijngesneden (biologisch)") == "kipfilet"


# --- Hoeveelheid naar gram ---


@pytest.mark.parametrize(
    "ingredient,verwacht",
    [
        ({"name": "bloem", "quantity": 500, "unit": "g"}, 500),
        ({"name": "bloem", "quantity": 500, "unit": "gr"}, 500),   # veelgebruikte spelling
        ({"name": "melk", "quantity": 1, "unit": "l"}, 1000),
        ({"name": "olijfolie", "quantity": 2, "unit": "el"}, 30),
        ({"name": "look", "quantity": 2, "unit": "teentje"}, 6),
        ({"name": "ui", "quantity": 2, "unit": "stuk"}, 220),
    ],
)
def test_gram_van(ingredient, verwacht):
    assert gram_van(ingredient) == pytest.approx(verwacht)


def test_groot_getal_zonder_eenheid_is_gram():
    """"500 gehakt" zonder eenheid is 500 gram, geen 500 stuks.

    Zonder deze regel werd dat 500 x 100 g = 50 kilo en kwam een spaghetti
    bolognese op 44.000 kcal per portie uit.
    """
    assert gram_van({"name": "gehakt", "quantity": 500, "unit": ""}) == 500


def test_klein_getal_zonder_eenheid_is_stuks():
    assert gram_van({"name": "ui", "quantity": 2, "unit": ""}) == pytest.approx(220)


def test_snede_brood_is_geen_heel_brood():
    """"4 sneden witbrood" is geen 3,2 kilo brood."""
    gram = gram_van({"name": "sneden witbrood", "quantity": 4, "unit": "stuk"})
    assert gram == pytest.approx(140)


def test_bovengrens_per_ingredient():
    assert gram_van({"name": "bloem", "quantity": 99, "unit": "kg"}) == 5000


# --- Recept doorrekenen ---


def test_kcal_per_portie():
    recept = {
        "servings": 4,
        "ingredients": [
            {"name": "kipfilet", "quantity": 600, "unit": "g"},   # 990 kcal
            {"name": "rijst", "quantity": 200, "unit": "g"},      # 700 kcal
        ],
    }
    kcal, dekking = bereken_kcal(recept)
    assert kcal == pytest.approx(422, abs=2)   # 1690 / 4
    assert dekking == 1.0


def test_meer_porties_geeft_minder_per_portie():
    ingredienten = [{"name": "kipfilet", "quantity": 600, "unit": "g"}]
    voor_twee, _ = bereken_kcal({"servings": 2, "ingredients": ingredienten})
    voor_vier, _ = bereken_kcal({"servings": 4, "ingredients": ingredienten})
    assert voor_twee == pytest.approx(voor_vier * 2, abs=2)


def test_dekking_zakt_bij_onbekende_ingredienten():
    recept = {
        "servings": 2,
        "ingredients": [
            {"name": "kipfilet", "quantity": 200, "unit": "g"},
            {"name": "iets volstrekt onbekends", "quantity": 100, "unit": "g"},
        ],
    }
    _, dekking = bereken_kcal(recept)
    assert dekking == 0.5


def test_frituurolie_telt_maar_deels_mee():
    """Frituurolie gaat grotendeels de vuilbak in, niet op je bord."""
    olie = [{"name": "frituurolie om te frituren", "quantity": 1000, "unit": "ml"}]
    kcal, _ = bereken_kcal({"servings": 1, "ingredients": olie})
    volledig = 1000 * 884 / 100
    assert kcal < volledig * 0.2


def test_recept_zonder_ingredienten():
    kcal, dekking = bereken_kcal({"servings": 4, "ingredients": []})
    assert kcal == 0
    assert dekking == 0.0
