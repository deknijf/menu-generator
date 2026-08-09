"""Tests voor app/tagging.py: tags en allergenen afleiden."""

import pytest

from app.tagging import MAX_TAGS, MIN_TAGS, bepaal_allergenen, bepaal_tags


def recept(naam, ingredienten=(), stappen=(), **extra):
    basis = {
        "name": naam,
        "description": "",
        "course": "hoofdgerecht",
        "ingredients": [{"name": n} for n in ingredienten],
        "preparation": list(stappen),
    }
    basis.update(extra)
    return basis


# --- Aantal tags ---


def test_altijd_minstens_zes_tags():
    """Ook een recept waar weinig uit te halen valt krijgt bruikbare tags."""
    tags = bepaal_tags(recept("Iets onherkenbaars", ["mysterie"]))
    assert len(tags) >= MIN_TAGS


def test_nooit_meer_dan_tien_tags():
    tags = bepaal_tags(
        recept(
            "Alles erin",
            ["kip", "rund", "zalm", "aardappel", "rijst", "pasta", "tomaat",
             "wortel", "ui", "look", "paprika", "champignon", "kaas", "room"],
        )
    )
    assert len(tags) <= MAX_TAGS


def test_grove_en_concrete_tags_naast_elkaar():
    """De gebruiker wil "vlees" zien, de planner wil weten dat het kip is."""
    tags = bepaal_tags(recept("Kip met rijst", ["kipfilet", "rijst"]))
    assert "gevogelte" in tags
    assert "kip" in tags
    assert "rijst" in tags


# --- Herkenning ---


@pytest.mark.parametrize(
    "ingredient,verwacht",
    [
        ("kipfilet", "kip"),
        ("rundergehakt", "rund"),
        ("zalmfilet", "zalm"),
        ("frietaardappelen", "aardappel"),
        ("spaghetti", "pasta"),
        ("cherrytomaten", "tomaat"),
        ("champignons", "champignon"),
    ],
)
def test_ingredient_geeft_tag(ingredient, verwacht):
    assert verwacht in bepaal_tags(recept("Gerecht", [ingredient]))


def test_zwarte_peper_is_geen_paprika():
    """Peper zit in bijna elk recept; die mag geen groentetag opleveren.

    Zonder deze afbakening kreeg de helft van de bibliotheek de tag paprika.
    """
    tags = bepaal_tags(recept("Stoofvlees", ["rundvlees", "peper", "zout"]))
    assert "paprika" not in tags


def test_paprikapoeder_is_geen_paprika():
    assert "paprika" not in bepaal_tags(recept("Kip", ["kipfilet", "paprikapoeder"]))


def test_echte_paprika_wel():
    assert "paprika" in bepaal_tags(recept("Gevulde paprika", ["rode paprika", "rijst"]))


def test_bereidingswijze_uit_de_stappen():
    tags = bepaal_tags(recept("Kip", ["kipfilet"], ["Verwarm de oven voor op 180 graden."]))
    assert "oven" in tags


def test_vegetarisch_als_er_geen_dierlijk_eiwit_is():
    tags = bepaal_tags(recept("Groentesoep", ["wortel", "prei", "aardappel"]))
    assert "vegetarisch" in tags


def test_voedingsprofiel_wordt_tag():
    tags = bepaal_tags(
        recept("Kip", ["kipfilet"], nutrition={"protein": 45, "carbs": 12, "calories": 420})
    )
    assert "eiwitrijk" in tags
    assert "koolhydraatarm" in tags
    assert "licht" in tags


def test_eigen_tags_blijven_vooraan():
    tags = bepaal_tags(recept("Kip", ["kipfilet"]), bestaande=["favoriet"])
    assert tags[0] == "favoriet"


# --- Allergenen ---


@pytest.mark.parametrize(
    "ingredient,verwacht",
    [
        ("bloem", "gluten"),
        ("spaghetti", "gluten"),
        ("room", "lactose"),
        ("geraspte kaas", "lactose"),
        ("eieren", "ei"),
        ("zalm", "vis"),
        ("garnalen", "schaaldieren"),
        ("mosselen", "weekdieren"),
        ("amandelen", "noten"),
        ("pindakaas", "pinda"),
        ("sojasaus", "soja"),
        ("bleekselder", "selderij"),
        ("dijonmosterd", "mosterd"),
        ("sesamzaad", "sesam"),
        ("citroensap", "citrus"),
    ],
)
def test_allergeen_uit_ingredient(ingredient, verwacht):
    assert verwacht in bepaal_allergenen(recept("Gerecht", [ingredient]))


def test_citrus_telt_mee_ook_al_is_het_niet_officieel():
    """Citrusintolerantie speelt in dit huishouden; zie ook de allergiefilter."""
    assert "citrus" in bepaal_allergenen(recept("Vis", ["kabeljauw", "limoensap"]))


def test_geen_allergenen_bij_een_schoon_recept():
    assert bepaal_allergenen(recept("Groenten", ["wortel", "courgette", "ui"])) == []


def test_bestaande_allergenen_blijven_staan():
    resultaat = bepaal_allergenen(recept("Kip", ["kipfilet"]), bestaande=["gluten"])
    assert "gluten" in resultaat
