"""Tests voor app/meal_engine.py.

generate_plan bevat een random-component, dus deze tests asserteren op eigenschappen
("komt nooit voor", "hoogstens N keer") en niet op exacte output. Waar toeval mee kan
spelen draaien we meerdere rondes.
"""

import pytest

from app.meal_engine import (
    _blocked_by_neighbors,
    _is_allowed,
    _max_occurrences,
    _primary_protein_key,
    _starch_key,
    _variety_penalty,
    generate_plan,
)

ROUNDS = 30


# --- Allergiefilter: dit is een harde uitsluiting en mag nooit lekken ---


def test_allergie_op_expliciete_metadata_sluit_recept_uit(settings, make_recipe):
    recipe = make_recipe("r1", allergens=["fish"])
    assert _is_allowed(recipe, settings, allergies_override=["fish"]) is False


def test_allergie_op_ingredientnaam_sluit_recept_uit(settings, make_recipe):
    recipe = make_recipe("r1", ingredients=[{"name": "zalm", "quantity": 300, "unit": "g"}])
    assert _is_allowed(recipe, settings, allergies_override=["zalm"]) is False


def test_allergie_op_receptnaam_sluit_recept_uit(settings, make_recipe):
    recipe = make_recipe("r1", name="Pasta met garnalen")
    assert _is_allowed(recipe, settings, allergies_override=["garnalen"]) is False


def test_citrus_aliassen_worden_uitgebreid(settings, make_recipe):
    """Wie 'citroen' opgeeft, moet ook beschermd zijn tegen 'lemon juice'."""
    recipe = make_recipe("r1", ingredients=[{"name": "lemon juice", "quantity": 1, "unit": "el"}])
    assert _is_allowed(recipe, settings, allergies_override=["citroen"]) is False


def test_zonder_allergieen_is_alles_toegestaan(settings, make_recipe):
    recipe = make_recipe("r1", allergens=["fish", "gluten"])
    assert _is_allowed(recipe, settings, allergies_override=[]) is True


def test_lege_allergiewaarden_worden_genegeerd(settings, make_recipe):
    recipe = make_recipe("r1")
    assert _is_allowed(recipe, settings, allergies_override=["", "   ", None]) is True


def test_allergie_uit_family_settings_wordt_gebruikt(settings, make_recipe):
    """Zonder override valt _is_allowed terug op settings['family']['allergies']."""
    settings["family"]["allergies"] = ["noten"]
    recipe = make_recipe("r1", ingredients=[{"name": "noten", "quantity": 50, "unit": "g"}])
    assert _is_allowed(recipe, settings) is False


def test_gegenereerd_plan_bevat_nooit_een_allergeen(settings, options, make_recipe, week):
    verboden = make_recipe("vis1", "Zalm uit de oven", tags=["fish"], allergens=["fish"])
    veilig = make_recipe("kip1", "Kip met groenten", tags=["chicken"])

    for _ in range(ROUNDS):
        plan = generate_plan(
            week, settings, options,
            allergies_override=["fish"],
            custom_recipes=[verboden, veilig],
            include_base_recipes=False,
        )
        assert all(item["meal_id"] != "vis1" for item in plan)


def test_plan_is_leeg_als_alles_wordt_uitgefilterd(settings, options, make_recipe, week):
    recipe = make_recipe("vis1", tags=["fish"], allergens=["fish"])
    plan = generate_plan(
        week, settings, options,
        allergies_override=["fish"],
        custom_recipes=[recipe],
        include_base_recipes=False,
    )
    assert plan == []


# --- Rotatielimieten ---


@pytest.mark.parametrize(
    "rotation,day_count,verwacht",
    [
        ("1_per_week", 7, 1),
        ("1_per_week", 14, 2),
        ("1_per_2_weeks", 14, 1),
        ("1_per_2_weeks", 28, 2),
        ("1_per_month", 30, 1),
        ("1_per_month", 7, 1),
        ("1_per_2_months", 60, 1),
        ("1_per_2_months", 30, 1),
    ],
)
def test_max_occurrences(make_recipe, rotation, day_count, verwacht):
    recipe = make_recipe("r1", rotation_limit=rotation)
    assert _max_occurrences(recipe, day_count) == verwacht


def test_rotatielimiet_wordt_gerespecteerd_in_plan(settings, options, make_recipe, week):
    """Een 1_per_month gerecht mag hoogstens 1x in een week van 7 dagen staan."""
    zeldzaam = make_recipe("zeldzaam", "Zeldzaam gerecht", rotation_limit="1_per_month", rating=5)
    vulling = [make_recipe(f"vul{i}", f"Vulling {i}") for i in range(6)]

    for _ in range(ROUNDS):
        plan = generate_plan(
            week, settings, options,
            custom_recipes=[zeldzaam, *vulling],
            include_base_recipes=False,
        )
        aantal = sum(1 for item in plan if item["meal_id"] == "zeldzaam")
        assert aantal <= 1


def test_plan_stopt_als_alle_recepten_hun_limiet_bereiken(settings, options, make_recipe, week):
    """Eén recept met 1_per_week over 7 dagen levert maar één ingeplande dag op."""
    recipe = make_recipe("solo", rotation_limit="1_per_week")
    plan = generate_plan(week, settings, options, custom_recipes=[recipe], include_base_recipes=False)
    assert len(plan) == 1


def test_plan_is_gesorteerd_op_datum(settings, options, make_recipe, week):
    recepten = [make_recipe(f"r{i}", f"Gerecht {i}") for i in range(10)]
    plan = generate_plan(week, settings, options, custom_recipes=recepten, include_base_recipes=False)
    datums = [item["date"] for item in plan]
    assert datums == sorted(datums)
    assert all({"date", "meal_id", "meal_name"} <= set(item) for item in plan)


def test_plan_vult_alle_kookdagen_bij_voldoende_recepten(settings, options, make_recipe, week):
    recepten = [make_recipe(f"r{i}", f"Gerecht {i}") for i in range(20)]
    plan = generate_plan(week, settings, options, custom_recipes=recepten, include_base_recipes=False)
    assert len(plan) == len(week)


# --- Variatie ---


def test_variety_penalty_is_nul_zonder_geschiedenis(make_recipe):
    assert _variety_penalty(make_recipe("r1"), []) == 0.0


def test_herhaling_van_hetzelfde_gerecht_wordt_zwaar_bestraft(make_recipe):
    recipe = make_recipe("r1", "Kip curry", tags=["chicken"])
    penalty = _variety_penalty(recipe, [recipe])
    assert penalty >= 12.0


def test_direct_herhalen_kost_meer_dan_later_herhalen(make_recipe):
    recipe = make_recipe("r1", "Kip curry", tags=["chicken"])
    ander = make_recipe("r2", "Rundstoofpot", tags=["beef"])

    direct = _variety_penalty(recipe, [recipe])
    later = _variety_penalty(recipe, [recipe, ander])
    assert direct > later


def test_zelfde_eiwitbron_na_elkaar_wordt_bestraft(make_recipe):
    kip_a = make_recipe("kip_a", "Kip met rijst", tags=["chicken"])
    kip_b = make_recipe("kip_b", "Kipfilet met salade", tags=["chicken"])
    rund = make_recipe("rund", "Rundstoofpot", tags=["beef"])

    zelfde_eiwit = _variety_penalty(kip_b, [kip_a])
    ander_eiwit = _variety_penalty(rund, [kip_a])
    assert zelfde_eiwit > ander_eiwit


@pytest.mark.parametrize(
    "naam,verwacht",
    [
        ("Zalm met broccoli", "vis"),
        ("Kipfilet met rijst", "kip"),
        ("Rundstoofpot", "rund"),
        ("Linzensoep", "peulvrucht"),
        ("Iets onherkenbaars", "other"),
    ],
)
def test_primary_protein_key(make_recipe, naam, verwacht):
    assert _primary_protein_key(make_recipe("r1", naam)) == verwacht


@pytest.mark.parametrize(
    "naam,verwacht",
    [
        ("Spaghetti bolognaise", "pasta"),
        ("Risotto met champignons", "rijst"),
        ("Stoofvlees met aardappelen", "aardappel"),
        ("Salade zonder bijgerecht", "none"),
    ],
)
def test_starch_key(make_recipe, naam, verwacht):
    assert _starch_key(make_recipe("r1", naam)) == verwacht


# --- Buren ---


def test_vis_mag_niet_twee_dagen_na_elkaar(make_recipe):
    vis_a = make_recipe("vis_a", tags=["fish"])
    vis_b = make_recipe("vis_b", tags=["fish"])
    assert _blocked_by_neighbors(vis_b, prev_recipe=vis_a) is True
    assert _blocked_by_neighbors(vis_b, next_recipe=vis_a) is True


def test_pasta_mag_niet_twee_dagen_na_elkaar(make_recipe):
    pasta_a = make_recipe("p_a", "Spaghetti bolognaise")
    pasta_b = make_recipe("p_b", tags=["pasta"])
    assert _blocked_by_neighbors(pasta_b, prev_recipe=pasta_a) is True


def test_verschillende_gerechten_blokkeren_elkaar_niet(make_recipe):
    kip = make_recipe("kip", tags=["chicken"])
    vis = make_recipe("vis", tags=["fish"])
    assert _blocked_by_neighbors(kip, prev_recipe=vis) is False


# --- Caloriebalans over de periode ---


def test_kcal_penalty_is_nul_binnen_het_budget(make_recipe):
    """Een gerecht dat onder de resterende ruimte blijft kost niets."""
    from app.meal_engine import _kcal_penalty

    licht = make_recipe("r1", calories=400)
    assert _kcal_penalty(licht, verbruikt=0, dagen_gepland=0, totaal_dagen=7, doel=700) == 0


def test_kcal_penalty_loopt_op_boven_het_budget(make_recipe):
    from app.meal_engine import _kcal_penalty

    zwaar = make_recipe("r1", calories=1400)
    straf = _kcal_penalty(zwaar, verbruikt=0, dagen_gepland=0, totaal_dagen=7, doel=700)
    assert straf > 0


def test_na_een_zware_dag_wordt_zwaar_duurder(make_recipe):
    """Kern van de balans: een uitschieter maakt de volgende dagen strenger."""
    from app.meal_engine import _kcal_penalty

    zwaar = make_recipe("r1", calories=1200)
    vers = _kcal_penalty(zwaar, verbruikt=0, dagen_gepland=0, totaal_dagen=7, doel=700)
    na_uitschieter = _kcal_penalty(zwaar, verbruikt=2000, dagen_gepland=1, totaal_dagen=7, doel=700)
    assert na_uitschieter > vers


def test_recept_zonder_calorieen_krijgt_geen_straf(make_recipe):
    from app.meal_engine import _kcal_penalty

    assert _kcal_penalty(make_recipe("r1", calories=0), 0, 0, 7, 700) == 0


def test_week_blijft_gemiddeld_rond_het_doel(settings, options, make_recipe, week):
    """Met een mix van licht en zwaar mag het weekgemiddelde niet ontsporen."""
    from app.meal_engine import _recipe_kcal

    recepten = []
    for i in range(10):
        recepten.append(make_recipe(f"licht{i}", f"Licht {i}", calories=450))
    for i in range(10):
        recepten.append(make_recipe(f"zwaar{i}", f"Zwaar {i}", calories=1300))

    op_id = {r["id"]: r for r in recepten}
    for _ in range(5):
        plan = generate_plan(week, settings, options, custom_recipes=recepten, include_base_recipes=False)
        kcals = [_recipe_kcal(op_id[item["meal_id"]]) for item in plan]
        gemiddelde = sum(kcals) / len(kcals)
        assert gemiddelde < 1000, f"weekgemiddelde {gemiddelde} te hoog"


# --- Variatie in groente ---


def test_zelfde_hoofdgroente_wordt_bestraft(make_recipe):
    from app.meal_engine import _variety_penalty

    bloemkool_a = make_recipe("a", "Gratin van bloemkool", tags=["bloemkool"])
    bloemkool_b = make_recipe("b", "Soep van bloemkool", tags=["bloemkool"])
    wortel = make_recipe("c", "Stoemp met wortel", tags=["wortel"])

    assert _variety_penalty(bloemkool_b, [bloemkool_a]) > _variety_penalty(wortel, [bloemkool_a])


def test_geen_vier_keer_dezelfde_groente_in_een_week(settings, options, make_recipe, week):
    """Vier bloemkoolgerechten naast genoeg alternatieven mag niet gebeuren."""
    from app.meal_engine import _vegetable_key

    recepten = [make_recipe(f"bk{i}", f"Bloemkool {i}", tags=["bloemkool"]) for i in range(6)]
    recepten += [make_recipe(f"wo{i}", f"Wortel {i}", tags=["wortel"]) for i in range(4)]
    recepten += [make_recipe(f"br{i}", f"Broccoli {i}", tags=["broccoli"]) for i in range(4)]
    op_id = {r["id"]: r for r in recepten}

    for _ in range(5):
        plan = generate_plan(week, settings, options, custom_recipes=recepten, include_base_recipes=False)
        groenten = [_vegetable_key(op_id[item["meal_id"]]) for item in plan]
        assert groenten.count("bloemkool") <= 3


def test_ontbrekende_voedingswaarden_scoren_neutraal(settings, options, make_recipe):
    """Een recept zonder eiwitgegevens mag niet structureel onderaan bungelen.

    Zonder deze terugval koos de planner altijd dezelfde handvol recepten die wel
    voedingswaarden hadden.
    """
    from app.meal_engine import _recipe_score

    met_data = make_recipe("a", "Met data", protein=30, carbs=35)
    zonder = make_recipe("b", "Zonder data", protein=0, carbs=0)
    verschil = abs(_recipe_score(met_data, settings, options) - _recipe_score(zonder, settings, options))
    assert verschil < 0.5


# --- Wat je niet lekker vindt ---


def test_afkeer_wordt_herkend_via_een_variant(make_recipe):
    """De gebruiker typt 'paddenstoelen', het recept zegt 'kastanjechampignons'."""
    from app.meal_engine import bevat_afkeer

    recept = make_recipe("r1", ingredients=[{"name": "kastanjechampignons"}])
    assert bevat_afkeer(recept, ["paddenstoelen"]) is True
    assert bevat_afkeer(recept, ["witloof"]) is False


def test_afkeer_zonder_termen_raakt_niets(make_recipe):
    from app.meal_engine import bevat_afkeer

    recept = make_recipe("r1", ingredients=[{"name": "champignons"}])
    assert bevat_afkeer(recept, []) is False
    assert bevat_afkeer(recept, ["", None]) is False


def test_gerecht_met_afkeer_valt_meestal_af(make_recipe, monkeypatch):
    """Zeven procent kans betekent: bij een hoge worp gaat het gerecht eruit."""
    from app import meal_engine

    monkeypatch.setattr(meal_engine.random, "random", lambda: 0.99)
    lekker = make_recipe("goed", ingredients=[{"name": "kipfilet"}])
    niet_lekker = make_recipe("slecht", ingredients=[{"name": "champignons"}])

    overgebleven = meal_engine._filter_afkeer([lekker, niet_lekker], ["paddenstoelen"])

    assert [r["id"] for r in overgebleven] == ["goed"]


def test_gerecht_met_afkeer_glipt_er_af_en_toe_door(make_recipe, monkeypatch):
    from app import meal_engine

    monkeypatch.setattr(meal_engine.random, "random", lambda: 0.01)
    lekker = make_recipe("goed", ingredients=[{"name": "kipfilet"}])
    niet_lekker = make_recipe("slecht", ingredients=[{"name": "champignons"}])

    overgebleven = meal_engine._filter_afkeer([lekker, niet_lekker], ["paddenstoelen"])

    assert {r["id"] for r in overgebleven} == {"goed", "slecht"}


def test_liever_iets_dat_je_niet_lust_dan_een_lege_week(make_recipe, monkeypatch):
    """Als alles afvalt, is een matig gerecht beter dan geen planning."""
    from app import meal_engine

    monkeypatch.setattr(meal_engine.random, "random", lambda: 0.99)
    alleen_paddenstoelen = [make_recipe("r1", ingredients=[{"name": "shiitake"}])]

    overgebleven = meal_engine._filter_afkeer(alleen_paddenstoelen, ["paddenstoelen"])

    assert [r["id"] for r in overgebleven] == ["r1"]


def test_allergie_kent_geen_uitzondering(settings, make_recipe, week, options):
    """Anders dan een afkeer mag een allergeen er nooit doorglippen."""
    from app.meal_engine import generate_plan

    veilig = make_recipe("veilig", ingredients=[{"name": "kipfilet"}])
    met_noten = make_recipe("noten", ingredients=[{"name": "walnoten"}])

    plan = generate_plan(
        week, settings, options,
        allergies_override=["noten"],
        custom_recipes=[veilig, met_noten],
        include_base_recipes=False,
    )

    assert plan
    assert all(dag["meal_id"] != "noten" for dag in plan)


def test_afkeer_uit_de_settings_wordt_gebruikt(settings, make_recipe, week, options, monkeypatch):
    """Zonder expliciete override valt de planner terug op family.dislikes."""
    from app import meal_engine

    monkeypatch.setattr(meal_engine.random, "random", lambda: 0.99)
    settings["family"]["dislikes"] = ["paddenstoelen"]
    veilig = make_recipe("veilig", ingredients=[{"name": "kipfilet"}])
    met_zwam = make_recipe("zwam", ingredients=[{"name": "oesterzwammen"}])

    plan = meal_engine.generate_plan(
        week, settings, options,
        custom_recipes=[veilig, met_zwam],
        include_base_recipes=False,
    )

    assert plan
    assert all(dag["meal_id"] != "zwam" for dag in plan)
