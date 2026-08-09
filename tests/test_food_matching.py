"""Tests voor app/food_matching.py.

Het gaat er hier vooral om dat een term ook zijn varianten vindt zonder dat hij
op willekeurige letterreeksen aanslaat.
"""

import pytest

from app.food_matching import bevat, expandeer, normaliseer, welke_komen_voor


def recept(naam="Testgerecht", ingredienten=(), tags=(), allergenen=()):
    return {
        "name": naam,
        "tags": list(tags),
        "allergens": list(allergenen),
        "ingredients": [{"name": n} for n in ingredienten],
    }


# --- Normaliseren ---


@pytest.mark.parametrize(
    "invoer,verwacht",
    [("  Paddenstoelen ", "paddenstoelen"), ("Rode  Biet", "rode biet"), (None, ""), ("", "")],
)
def test_normaliseer(invoer, verwacht):
    assert normaliseer(invoer) == verwacht


# --- Uitbreiden naar varianten ---


def test_overkoepelende_term_vindt_zijn_soorten():
    tokens = expandeer("paddenstoelen")
    assert "champignon" in tokens
    assert "shiitake" in tokens


def test_soortnaam_breidt_niet_uit_naar_de_hele_groep():
    """Wie shiitake niet lust, wil daarom nog niet alle champignons weren."""
    assert "champignon" not in expandeer("shiitake")


def test_synoniemen_werken_in_twee_richtingen():
    assert "ajuin" in expandeer("ui")
    assert "ui" in expandeer("ajuin")


def test_spellingvariant_paddestoel():
    assert "paddestoel" in expandeer("paddenstoel")
    assert "champignon" in expandeer("paddestoelen")


# --- Herkennen in een recept ---


def test_vindt_ingredient_in_samenstelling():
    """De site schrijft 'kastanjechampignons', de gebruiker typt 'champignon'."""
    assert bevat(recept(ingredienten=["kastanjechampignons", "room"]), "champignon") is True


def test_vindt_soort_via_de_groepsnaam():
    assert bevat(recept(ingredienten=["shiitake", "sojasaus"]), "paddenstoelen") is True


def test_vindt_term_in_de_receptnaam():
    assert bevat(recept(naam="Risotto met paddenstoelen"), "champignon") is False
    assert bevat(recept(naam="Risotto met paddenstoelen"), "paddenstoel") is True


def test_vindt_term_via_een_tag():
    assert bevat(recept(tags=["vegetarisch"]), "vegetarisch") is True


def test_kort_woord_slaat_niet_aan_midden_in_een_ander_woord():
    """Regressie: 'ui' mag niet matchen op 'bruine bonen' of 'kruiden'."""
    assert bevat(recept(ingredienten=["bruine bonen", "kruiden"]), "ui") is False
    assert bevat(recept(ingredienten=["gesnipperde ui"]), "ui") is True


def test_ajuin_wordt_gevonden_als_je_ui_opgeeft():
    assert bevat(recept(ingredienten=["grote ajuinen"]), "ui") is True


def test_allergeenlabel_op_het_recept_telt():
    assert bevat(recept(allergenen=["noten"]), "noten") is True


def test_eu_allergeen_gebruikt_dezelfde_regels_als_het_labelen():
    """'noten' hoort walnoten te vinden, ook zonder expliciet label."""
    assert bevat(recept(ingredienten=["walnoten", "honing"]), "noten") is True
    assert bevat(recept(ingredienten=["mozzarella"]), "lactose") is True


def test_lege_term_vindt_niets():
    assert bevat(recept(ingredienten=["kip"]), "") is False
    assert bevat(recept(ingredienten=["kip"]), None) is False


def test_recept_zonder_inhoud_geeft_geen_treffer():
    assert bevat({"name": "", "ingredients": [], "tags": [], "allergens": []}, "kip") is False


def test_welke_komen_voor_geeft_alleen_de_treffers():
    gerecht = recept(ingredienten=["champignons", "room", "kipfilet"])
    assert welke_komen_voor(gerecht, ["paddenstoel", "vis", "kip"]) == ["paddenstoel", "kip"]


# --- Engelse schrijfwijzen uit oudere profielen ---


def test_engelse_schrijfwijze_krijgt_dezelfde_dekking():
    """Regressie: 'soya' zocht letterlijk naar 'soya' en miste sojasaus."""
    assert bevat(recept(ingredienten=["scheutje sojasaus"]), "soya") is True
    assert bevat(recept(ingredienten=["tofu"]), "soya") is True


@pytest.mark.parametrize(
    "term,ingredient",
    [
        ("nuts", "walnoten"),
        ("peanut", "pindakaas"),
        ("fish", "kabeljauwfilet"),
        ("shellfish", "garnalen"),
        ("celery", "knolselder"),
        ("mustard", "dijonmosterd"),
        ("sesame", "sesamzaad"),
    ],
)
def test_engelse_allergienamen_vinden_het_nederlandse_ingredient(term, ingredient):
    assert bevat(recept(ingredienten=[ingredient]), term) is True
