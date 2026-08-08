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
        ("2_per_week", 7, 2),
        ("1_per_week", 14, 2),
        ("2_per_week", 14, 4),
        ("1_per_month", 30, 1),
        ("1_per_month", 7, 1),
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
        ("Zalm met broccoli", "fish"),
        ("Kipfilet met rijst", "chicken"),
        ("Rundstoofpot", "beef"),
        ("Linzensoep", "legume"),
        ("Iets onherkenbaars", "other"),
    ],
)
def test_primary_protein_key(make_recipe, naam, verwacht):
    assert _primary_protein_key(make_recipe("r1", naam)) == verwacht


@pytest.mark.parametrize(
    "naam,verwacht",
    [
        ("Spaghetti bolognaise", "pasta"),
        ("Risotto met champignons", "rice"),
        ("Stoofvlees met aardappelen", "potato"),
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
