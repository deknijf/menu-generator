"""Tests voor het Nederlands houden van tags, allergenen en voorkeuren.

De app is Nederlandstalig, maar er staat nog Engels in oudere profielen en in de
basisrecepten. Die termen moeten vertaald worden in plaats van te zoeken naar een
woord dat nergens meer voorkomt.
"""

import json

import pytest

from app.tagging import bepaal_allergenen, bepaal_tags, vernederlands, vernederlands_lijst


@pytest.mark.parametrize(
    "engels,nederlands",
    [
        ("chicken", "kip"),
        ("fish", "vis"),
        ("mediterranean", "mediterraans"),
        ("high-protein", "eiwitrijk"),
        ("low-carb", "koolhydraatarm"),
        ("west-europe", "west-europees"),
        ("soy", "soja"),
        ("soya", "soja"),
        ("shellfish", "schaaldieren"),
        ("favorite", "favoriet"),
        ("heavy", "zwaar"),
    ],
)
def test_engelse_termen_worden_vertaald(engels, nederlands):
    assert vernederlands(engels) == nederlands


def test_nederlandse_termen_blijven_ongemoeid():
    assert vernederlands("paddenstoelen") == "paddenstoelen"
    assert vernederlands("Witloof") == "witloof"


def test_onbekende_termen_blijven_staan():
    """Zelf ingetypte voorkeuren mogen niet verdwijnen omdat we ze niet kennen."""
    assert vernederlands("rabarber") == "rabarber"


def test_lijst_vertaalt_en_ontdubbelt():
    """"chicken" en "kip" naast elkaar worden een keer kip."""
    assert vernederlands_lijst(["chicken", "kip", "fish"]) == ["kip", "vis"]


def test_lege_waarden_vallen_weg():
    assert vernederlands_lijst(["", None, "  "]) == []


def test_basisrecepten_hebben_nederlandse_tags():
    with open("app/recipes.json") as bestand:
        recepten = json.load(bestand)
    engels = {"chicken", "fish", "high-protein", "low-carb", "mediterranean",
              "west-europe", "balanced-carb", "heavy", "favorite", "soy"}
    for recept in recepten:
        assert not engels.intersection(recept["tags"]), recept["name"]
        assert not engels.intersection(recept["allergens"]), recept["name"]


# --- Vis in samenstellingen ---


def _recept(naam):
    return {"name": naam, "ingredients": [], "preparation": [], "description": ""}


@pytest.mark.parametrize(
    "naam", ["Vissoep", "Visfilet met puree", "Schelvis met puree", "Koolvis met spinazie"]
)
def test_vis_wordt_herkend_in_samenstellingen(naam):
    """Regressie: schelvisgerechten kregen geen eiwittag en heetten vegetarisch."""
    tags = bepaal_tags(_recept(naam))
    assert "vis" in tags
    assert "vegetarisch" not in tags
    assert "vis" in bepaal_allergenen(_recept(naam))


def test_inktvis_is_geen_vis():
    """Inktvis is een weekdier; het woord eindigt alleen toevallig op vis."""
    assert "vis" not in bepaal_tags(_recept("Gebakken inktvis met aioli"))
    assert "weekdieren" in bepaal_allergenen(_recept("Gebakken inktvis met aioli"))


@pytest.mark.parametrize("naam", ["Pasta met een visie op tomaat", "Gegrilde groenten"])
def test_woorden_die_toevallig_met_vis_beginnen_tellen_niet(naam):
    assert "vis" not in bepaal_tags(_recept(naam))
