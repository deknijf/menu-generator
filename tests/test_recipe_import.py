"""Tests voor app/recipe_import.py.

Bewust zonder netwerk: alle functies die het internet raken zijn gescheiden van
de functies die tekst omzetten, en alleen die laatste worden hier getest.
"""

import pytest

from app.recipe_import import (
    _dagelijksekost_stappen,
    _GEEN_RECEPT,
    _ingredient_ontleden,
    _links_op_pagina,
    _porties_uit,
    _stappen_opschonen,
)


# --- Ingredienten ontleden ---


@pytest.mark.parametrize(
    "regel,naam,hoeveelheid,eenheid",
    [
        ("1 kg frietaardappelen", "frietaardappelen", 1.0, "kg"),
        ("500 g bloem", "bloem", 500.0, "g"),
        ("2 el olijfolie", "olijfolie", 2.0, "el"),
        ("4 kipfilets", "kipfilets", 4.0, ""),
        ("1,5 l water", "water", 1.5, "l"),
        ("2 teentjes look", "look", 2.0, "teentjes"),
        ("3 tbsp soy sauce", "soy sauce", 3.0, "el"),   # tbsp wordt eetlepel
        ("4 oz butter", "butter", 115.0, "g"),          # imperiaal wordt metrisch
        ("2 lbs (908g) cream cheese", "cream cheese", 908.0, "g"),
    ],
)
def test_ingredient_met_hoeveelheid(regel, naam, hoeveelheid, eenheid):
    resultaat = _ingredient_ontleden(regel)
    assert resultaat["name"] == naam
    assert resultaat["quantity"] == hoeveelheid
    assert resultaat["unit"] == eenheid


@pytest.mark.parametrize("regel", ["peper", "zout naar smaak", "een handvol verse kruiden"])
def test_ingredient_zonder_hoeveelheid_blijft_leesbaar(regel):
    """Liever de hele regel als naam dan een verkeerde gok."""
    resultaat = _ingredient_ontleden(regel)
    assert resultaat["name"]
    assert resultaat["quantity"] == 0


def test_lege_ingredientregel_wordt_overgeslagen():
    assert _ingredient_ontleden("") is None
    assert _ingredient_ontleden("   ") is None


# --- Porties ---


@pytest.mark.parametrize(
    "waarde,verwacht",
    [
        (4, 4),
        ("4 servings", 4),
        ("4 personen", 4),
        ("2-3 porties", 2),
        ("8 servings", 6),  # boven het maximum
        (None, 2),
        ("geen idee", 2),
        (0, 1),
    ],
)
def test_porties_uit(waarde, verwacht):
    assert _porties_uit(waarde) == verwacht


# --- Stappen opschonen ---


def test_stappen_opschonen_verwijdert_lege_en_witruimte():
    ruw = ["  Snij de ui  ", "", "   ", "Bak\n\n  de kip"]
    assert _stappen_opschonen(ruw) == ["Snij de ui", "Bak de kip"]


# --- Linkherkenning ---


def test_links_vindt_hrefs_en_kale_paden():
    """JavaScript-sites zetten hun links in een payload, niet in href."""
    html = """
      <a href="/gerechten/kip-met-appelmoes">Kip</a>
      <a href="https://ander.be/gerechten/niet-van-ons">Extern</a>
      {"url":"/gerechten/stoofpot-met-kip-en-pasta"}
    """
    links = _links_op_pagina(html, "https://dagelijksekost.vrt.be/themas/kip")
    assert "https://dagelijksekost.vrt.be/gerechten/kip-met-appelmoes" in links
    assert "https://dagelijksekost.vrt.be/gerechten/stoofpot-met-kip-en-pasta" in links
    assert all("ander.be" not in link for link in links), "externe host hoort niet mee"


def test_links_slaat_zoek_en_overzichtspaginas_over():
    html = '<a href="/gerechten/zoeken">Zoeken</a><a href="/gerechten/echt-recept">Recept</a>'
    links = _links_op_pagina(html, "https://dagelijksekost.vrt.be/")
    assert links == ["https://dagelijksekost.vrt.be/gerechten/echt-recept"]


def test_links_ontdubbelt_hetzelfde_recept_onder_twee_paden():
    """Sommige sites linken hetzelfde recept via /gerechten/<id> en /recipes/<id>."""
    html = '<a href="/gerechten/ABC123xyz">x</a><a href="/recipes/ABC123xyz">y</a>'
    links = _links_op_pagina(html, "https://dagelijksekost.vrt.be/")
    assert len(links) == 1


def test_overzichtspad_zelf_is_geen_recept():
    html = '<a href="/recipes">Alle recepten</a>'
    assert _links_op_pagina(html, "https://www.joshuaweissman.com/") == []


def test_blocklist_bevat_de_bekende_niet_recepten():
    assert "zoeken" in _GEEN_RECEPT and "search" in _GEEN_RECEPT


# --- Dagelijkse Kost: stappen uit de paginadata ---


def test_dagelijksekost_stappen_uit_react_payload():
    """De volledige bereiding staat in de payload van de pagina zelf.

    Hun schema.org-blok bevat maar de voorverwarm-instructies; deze extractie
    haalt de rest uit dezelfde pagina, zonder /api/ aan te spreken.
    """
    binnenste = (
        '{"step":2,"name":null,"externalPhotoUrl":"https://x/y.png",'
        '"description":"Snij de ui fijn."}'
        '{"step":1,"name":null,"description":"Verwarm de oven voor."}'
    )
    payload = binnenste.replace('"', '\\"')
    html = f'<script>self.__next_f.push([1,"{payload}"])</script>'

    assert _dagelijksekost_stappen(html) == ["Verwarm de oven voor.", "Snij de ui fijn."]


def test_dagelijksekost_stappen_zonder_payload_is_leeg():
    assert _dagelijksekost_stappen("<html><body>niets</body></html>") == []


# --- Bronlabel voor de pill ---


@pytest.mark.parametrize(
    "url,verwacht",
    [
        ("https://dagelijksekost.vrt.be/gerechten/kip", "dagelijksekost"),
        ("https://www.joshuaweissman.com/recipes/x", "joshuaweissman"),
        ("https://ah.be/allerhande/recept/R-123", "ah"),
        ("https://www.leukerecepten.nl/recepten/x/", "leukerecepten"),
        ("", "custom"),
        (None, "custom"),
        ("geen-geldige-url", "custom"),
    ],
)
def test_source_label(url, verwacht):
    from app.routes import _source_label

    assert _source_label({"source_url": url}) == verwacht


def test_source_label_zonder_bron_is_custom():
    from app.routes import _source_label

    assert _source_label({}) == "custom"


# --- Indeling in gangen ---


@pytest.mark.parametrize(
    "naam,verwacht",
    [
        ("Creamy Cheesecake at Home", "dessert"),
        ("Chocolademousse met framboos", "dessert"),
        ("Appeltaart", "dessert"),
        ("Tomatensoep met balletjes", "voorgerecht"),
        ("Carpaccio van rund", "voorgerecht"),
        ("Steak Tagliata", "hoofdgerecht"),
        ("Quick Easy Vodka Pasta", "hoofdgerecht"),
    ],
)
def test_classificeer_gang_op_naam(naam, verwacht):
    from app.recipe_import import _classificeer_gang

    assert _classificeer_gang(naam) == verwacht


@pytest.mark.parametrize(
    "naam",
    [
        "Kip pirri pirri met geroosterde groenten en rijst",  # 'ijs' zit in 'rijst'
        "Stoofvlees met frieten voor een goede prijs",        # 'ijs' zit in 'prijs'
        "Vlaamse stoverij",                                   # 'vla' zit in 'Vlaamse'
    ],
)
def test_deelwoorden_maken_er_geen_dessert_van(naam):
    """Zonder woordgrenzen werd een kipgerecht met rijst als dessert ingedeeld."""
    from app.recipe_import import _classificeer_gang

    assert _classificeer_gang(naam) == "hoofdgerecht"


def test_categorie_van_de_site_wint_van_de_naam():
    """Dagelijkse Kost geeft recipeCategory mee; die is betrouwbaarder dan raden."""
    from app.recipe_import import _classificeer_gang

    assert _classificeer_gang("Taart van bloemkool", categorie="Hoofdgerecht") == "hoofdgerecht"
    assert _classificeer_gang("Kip met appelmoes", categorie="Dessert") == "dessert"


def test_onbekend_wordt_hoofdgerecht():
    from app.recipe_import import _classificeer_gang

    assert _classificeer_gang("Iets onherkenbaars") == "hoofdgerecht"


# --- Sauzen en snacks zijn geen avondmaal ---


@pytest.mark.parametrize(
    "naam",
    ["Salsa verde", "Zigeunersaus", "Sesamsaus", "Fond", "Ultieme bioscooppopcorn",
     "Tomatensaus (basisbereiding)"],
)
def test_saus_of_snack_is_geen_hoofdgerecht(naam):
    from app.recipe_import import _classificeer_gang

    assert _classificeer_gang(naam) == "voorgerecht"


@pytest.mark.parametrize(
    "naam",
    ["Kipfilet met champignonsaus en frietjes", "Balletjes in seldersaus",
     "French dip-sandwich", "Pasta met pesto van boerenkool en gebakken kip"],
)
def test_gerecht_met_saus_blijft_hoofdgerecht(naam):
    """De regel geldt alleen als de hele naam over de saus gaat.

    Met een ruimere drempel werden "Balletjes in seldersaus" en
    "French dip-sandwich" onterecht uit de planner gefilterd.
    """
    from app.recipe_import import _classificeer_gang

    assert _classificeer_gang(naam) == "hoofdgerecht"
