"""Gedeelde fixtures.

De unit tests raken de database niet: meal_engine is puur, en de shopping-aggregatie
wordt getest door haar twee DB-afhankelijkheden te vervangen. Zo blijven ze snel en
onafhankelijk van data/app.db.
"""

import pytest


@pytest.fixture
def settings():
    """Minimale settings-structuur zoals meal_engine die verwacht."""
    return {
        "family": {"allergies": [], "likes": [], "dislikes": []},
        "nutrition": {
            "high_protein_weight": 1.3,
            "low_carb_weight": 1.1,
            "weekly_min_fish": 0,
            "west_europe_preference": 2.2,
            "asian_penalty": 2.8,
        },
        "app": {"base_servings": 2},
    }


@pytest.fixture
def options():
    return {"high_protein": False, "low_carb": False, "prefer_fish": False, "person_count": 2}


@pytest.fixture
def make_recipe():
    """Factory voor een recept met alle velden die de engine aanraakt."""

    def _make(recipe_id, name="Testgerecht", *, tags=None, allergens=None,
              ingredients=None, protein=30, carbs=25, calories=500,
              rating=3, rotation_limit=None):
        recipe = {
            "id": recipe_id,
            "name": name,
            "tags": list(tags or []),
            "allergens": list(allergens or []),
            "ingredients": list(ingredients or [{"name": "ingredient", "quantity": 1, "unit": "stuk"}]),
            "nutrition": {"protein": protein, "carbs": carbs, "calories": calories},
            "rating": rating,
        }
        if rotation_limit is not None:
            recipe["rotation_limit"] = rotation_limit
        return recipe

    return _make


@pytest.fixture
def week():
    """Zeven opeenvolgende kookdagen, maandag t/m zondag."""
    return [f"2026-08-{day:02d}" for day in range(3, 10)]
