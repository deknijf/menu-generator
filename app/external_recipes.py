import json
import time
from pathlib import Path
from urllib.request import urlopen


CACHE_PATH = Path("data/themealdb_cache.json")
RANDOM_MEAL_URL = "https://www.themealdb.com/api/json/v1/1/random.php"
CACHE_TTL_SECONDS = 12 * 60 * 60


def _safe_float(value, fallback):
    try:
        return float(value)
    except Exception:
        return float(fallback)


def _infer_tags(name, category, area, ingredients):
    text = " ".join([name, category, area, *ingredients]).lower()
    tags = []
    if any(token in text for token in ["fish", "salmon", "cod", "tuna", "haddock", "mackerel"]):
        tags.append("fish")
    if any(token in text for token in ["chicken", "turkey"]):
        tags.append("chicken")
    if any(token in text for token in ["beef", "steak"]):
        tags.append("beef")
    if "pasta" in text or "spaghetti" in text:
        tags.append("pasta")
    if any(token in text for token in ["rice", "risotto"]):
        tags.append("rice")
    if any(token in text for token in ["potato", "chips"]):
        tags.append("potato")
    if any(token in text for token in ["soup", "stew"]):
        tags.append("soup")
    if any(token in text for token in ["fried", "roast", "casserole", "lasagna", "bolognese"]):
        tags.append("heavy")
    if "seafood" in text:
        tags.append("seafood")
    if not tags:
        tags.append("balanced")
    return list(dict.fromkeys(tags))


def _infer_allergens(ingredients):
    text = " ".join(ingredients).lower()
    allergens = []
    if any(token in text for token in ["fish", "salmon", "cod", "tuna", "mackerel"]):
        allergens.append("fish")
    if any(token in text for token in ["flour", "pasta", "bread", "noodle", "spaghetti"]):
        allergens.append("gluten")
    if any(token in text for token in ["milk", "cream", "butter", "cheese", "yogurt"]):
        allergens.append("lactose")
    if "soy" in text:
        allergens.append("soy")
    if "peanut" in text:
        allergens.append("peanut")
    if any(token in text for token in ["shrimp", "prawn", "mussel", "clam", "crab", "lobster"]):
        allergens.append("shellfish")
    return list(dict.fromkeys(allergens))


def _infer_nutrition(tags):
    protein = 26.0
    carbs = 28.0
    calories = 520.0
    if any(tag in tags for tag in ["fish", "chicken", "beef"]):
        protein = 38.0
    if any(tag in tags for tag in ["pasta", "rice", "potato"]):
        carbs = 46.0
        calories = 640.0
    if "heavy" in tags:
        calories += 80.0
    return {"protein": protein, "carbs": carbs, "calories": calories}


def _parse_ingredients(meal):
    out = []
    names = []
    for idx in range(1, 21):
        name = str(meal.get(f"strIngredient{idx}", "") or "").strip()
        if not name:
            continue
        measure = str(meal.get(f"strMeasure{idx}", "") or "").strip()
        names.append(name)
        out.append({"name": name.lower(), "quantity": _safe_float(0, 0), "unit": measure})
    return out, names


def _parse_steps(instructions):
    raw = str(instructions or "").strip()
    if not raw:
        return []
    lines = [part.strip() for part in raw.replace("\r", "\n").split("\n") if part.strip()]
    if len(lines) > 1:
        return lines
    parts = [part.strip() for part in raw.split(".") if part.strip()]
    return parts


def _to_recipe(meal):
    ingredients, ingredient_names = _parse_ingredients(meal)
    name = str(meal.get("strMeal") or "TheMealDB Recept").strip()
    category = str(meal.get("strCategory") or "").strip()
    area = str(meal.get("strArea") or "").strip()
    tags = _infer_tags(name, category, area, ingredient_names)
    return {
        "id": f"ext_{meal.get('idMeal')}",
        "name": name,
        "description": f"Variatie uit TheMealDB ({category}{' · ' + area if area else ''}).".strip(),
        "image_url": str(meal.get("strMealThumb") or "").strip(),
        "tags": tags,
        "allergens": _infer_allergens(ingredient_names),
        "ingredients": ingredients,
        "preparation": _parse_steps(meal.get("strInstructions")),
        "nutrition": _infer_nutrition(tags),
    }


def _load_cache():
    if not CACHE_PATH.exists():
        return None
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_cache(items):
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps({"fetched_at": int(time.time()), "items": items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _cache_fresh(payload):
    if not payload:
        return False
    fetched_at = int(payload.get("fetched_at") or 0)
    return (int(time.time()) - fetched_at) < CACHE_TTL_SECONDS and bool(payload.get("items"))


def _fetch_random_meal():
    with urlopen(RANDOM_MEAL_URL, timeout=5) as response:
        data = json.loads(response.read().decode("utf-8"))
        meals = data.get("meals") or []
        return meals[0] if meals else None


def get_external_ai_recipes(limit=16, force_refresh=False):
    cache = _load_cache()
    if not force_refresh and _cache_fresh(cache):
        return list(cache.get("items", []))[:limit]

    recipes = []
    seen = set()
    attempts = 0
    max_attempts = max(limit * 6, 40)

    while len(recipes) < limit and attempts < max_attempts:
        attempts += 1
        try:
            meal = _fetch_random_meal()
        except Exception:
            meal = None
        if not meal:
            continue
        meal_id = str(meal.get("idMeal") or "").strip()
        if not meal_id or meal_id in seen:
            continue
        seen.add(meal_id)
        recipes.append(_to_recipe(meal))

    if recipes:
        _save_cache(recipes)
        return recipes

    # fallback op bestaande cache (ook als die stale is)
    if cache and cache.get("items"):
        return list(cache.get("items", []))[:limit]
    return []

