import json
import time
from pathlib import Path
from urllib.request import urlopen
from urllib.parse import quote


CACHE_PATH = Path("data/themealdb_cache.json")
CACHE_SCHEMA_VERSION = 4
LOOKUP_URL = "https://www.themealdb.com/api/json/v1/1/lookup.php?i={meal_id}"
FILTER_INGREDIENT_URL = "https://www.themealdb.com/api/json/v1/1/filter.php?i={ingredient}"
FILTER_CATEGORY_URL = "https://www.themealdb.com/api/json/v1/1/filter.php?c={category}"
CACHE_TTL_SECONDS = 12 * 60 * 60
HEALTHY_INGREDIENTS = ["chicken_breast", "salmon", "tuna", "cod", "turkey", "prawn"]
HEALTHY_CATEGORIES = ["Seafood", "Chicken"]
REJECT_WORDS = [
    "fried",
    "deep fry",
    "battered",
    "breaded",
    "pie",
    "lasagna",
    "burger",
    "donut",
    "cake",
    "mac and cheese",
    "katsu",
]

INGREDIENT_TRANSLATIONS = {
    "black olives": "zwarte olijven",
    "brown sugar": "bruine suiker",
    "butter": "boter",
    "cayenne pepper": "cayennepeper",
    "chicken breast": "kipfilet",
    "chicken stock": "kippenbouillon",
    "chickpeas": "kikkererwten",
    "coriander": "koriander",
    "garlic": "knoflook",
    "onion": "ui",
    "red onion": "rode ui",
    "tomato": "tomaat",
    "tomatoes": "tomaten",
    "cherry tomatoes": "cherrytomaten",
    "potato": "aardappel",
    "potatoes": "aardappelen",
    "rice": "rijst",
    "pasta": "pasta",
    "spaghetti": "spaghetti",
    "salmon": "zalm",
    "cod": "kabeljauw",
    "tuna": "tonijn",
    "prawn": "garnaal",
    "prawns": "garnalen",
    "beef": "rundvlees",
    "minced beef": "rundergehakt",
    "ground beef": "rundergehakt",
    "egg": "ei",
    "eggs": "eieren",
    "milk": "melk",
    "cream": "room",
    "cheese": "kaas",
    "spinach": "spinazie",
    "broccoli": "broccoli",
    "carrot": "wortel",
    "zucchini": "courgette",
    "bell pepper": "paprika",
    "lemon": "citroen",
    "lemon juice": "citroensap",
    "lemon zest": "citroenzeste",
    "lime juice": "limoensap",
    "lime zest": "limoenzeste",
    "lime": "limoen",
    "parsley": "peterselie",
}

UNIT_TRANSLATIONS = {
    "handful": "handvol",
    "pinch": "snufje",
    "tsp": "tl",
    "tbsp": "el",
    "cup": "kop",
    "cups": "kop",
    "clove": "teentje",
    "cloves": "teentjes",
    "oz": "oz",
    "g": "g",
    "kg": "kg",
    "ml": "ml",
    "l": "l",
}


def _safe_float(value, fallback):
    try:
        return float(value)
    except Exception:
        return float(fallback)


def _normalize_spaces(value):
    return " ".join(str(value or "").strip().split())


def _to_dutch_ingredient(name):
    key = _normalize_spaces(name).lower()
    if not key:
        return ""
    return INGREDIENT_TRANSLATIONS.get(key, key)


def _to_dutch_unit(unit):
    key = _normalize_spaces(unit).lower()
    if not key:
        return ""
    return UNIT_TRANSLATIONS.get(key, key)


def _parse_fraction_token(token):
    raw = token.strip()
    if not raw:
        return None
    if "/" in raw:
        parts = raw.split("/", 1)
        if len(parts) == 2:
            try:
                num = float(parts[0].strip())
                den = float(parts[1].strip())
                if den != 0:
                    return num / den
            except Exception:
                return None
    try:
        return float(raw)
    except Exception:
        return None


def _parse_measure(measure):
    text = _normalize_spaces(measure)
    if not text:
        return 0.0, ""
    parts = text.replace("-", " ").split(" ")
    qty = 0.0
    consumed = 0
    for part in parts:
        token_value = _parse_fraction_token(part)
        if token_value is None:
            break
        qty += token_value
        consumed += 1
    unit = " ".join(parts[consumed:]).strip()
    if consumed == 0:
        return 1.0, _to_dutch_unit(text)
    return qty, _to_dutch_unit(unit)


def _infer_tags(name, category, area, ingredients):
    text = " ".join([name, category, area, *ingredients]).lower()
    tags = []
    if any(token in text for token in ["fish", "salmon", "cod", "tuna", "haddock", "mackerel", "vis", "zalm", "kabeljauw", "tonijn"]):
        tags.append("fish")
    if any(token in text for token in ["chicken", "turkey", "kip", "kalkoen"]):
        tags.append("chicken")
    if any(token in text for token in ["beef", "steak", "rund", "runder"]):
        tags.append("beef")
    if "pasta" in text or "spaghetti" in text:
        tags.append("pasta")
    if any(token in text for token in ["rice", "risotto"]):
        tags.append("rice")
    if any(token in text for token in ["potato", "chips", "aardappel"]):
        tags.append("potato")
    if any(token in text for token in ["soup", "stew", "soep", "stoof"]):
        tags.append("soup")
    if any(token in text for token in ["fried", "roast", "casserole", "lasagna", "bolognese"]):
        tags.append("heavy")
    if "seafood" in text:
        tags.append("seafood")
    if any(token in text for token in ["belgian", "dutch", "french", "german", "irish", "british", "english", "welsh", "scottish", "portuguese", "spanish", "italian", "greek", "europe"]):
        tags.append("west-europe")
    if any(token in text for token in ["belgium", "netherlands", "france", "germany", "ireland", "uk", "britain", "portugal", "spain", "italy", "greece"]):
        tags.append("west-europe")
    if any(token in text for token in ["asian", "thai", "vietnam", "japan", "korean", "china", "indian", "malaysian", "indonesia", "bangladesh", "pakistan"]):
        tags.append("asian")
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
        qty, unit = _parse_measure(measure)
        dutch_name = _to_dutch_ingredient(name)
        names.append(dutch_name)
        out.append({"name": dutch_name, "quantity": _safe_float(qty, 0), "unit": unit})
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
        json.dumps(
            {"schema_version": CACHE_SCHEMA_VERSION, "fetched_at": int(time.time()), "items": items},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _cache_fresh(payload):
    if not payload:
        return False
    if int(payload.get("schema_version") or 0) != CACHE_SCHEMA_VERSION:
        return False
    fetched_at = int(payload.get("fetched_at") or 0)
    return (int(time.time()) - fetched_at) < CACHE_TTL_SECONDS and bool(payload.get("items"))


def _fetch_json(url):
    with urlopen(url, timeout=7) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data


def _fetch_meal_ids_from_filter(url):
    try:
        data = _fetch_json(url)
    except Exception:
        return []
    out = []
    for item in data.get("meals") or []:
        meal_id = str(item.get("idMeal") or "").strip()
        if meal_id:
            out.append(meal_id)
    return out


def _fetch_meal_by_id(meal_id):
    try:
        data = _fetch_json(LOOKUP_URL.format(meal_id=quote(str(meal_id))))
    except Exception:
        return None
    meals = data.get("meals") or []
    return meals[0] if meals else None


def _is_healthier_meal(meal):
    name = str(meal.get("strMeal") or "").lower()
    category = str(meal.get("strCategory") or "").lower()
    instructions = str(meal.get("strInstructions") or "").lower()
    text = f"{name} {category} {instructions}"
    return not any(word in text for word in REJECT_WORDS)


def _candidate_meal_ids():
    ids = []
    for ingredient in HEALTHY_INGREDIENTS:
        url = FILTER_INGREDIENT_URL.format(ingredient=quote(ingredient))
        ids.extend(_fetch_meal_ids_from_filter(url))
    for category in HEALTHY_CATEGORIES:
        url = FILTER_CATEGORY_URL.format(category=quote(category))
        ids.extend(_fetch_meal_ids_from_filter(url))
    # unique while keeping order
    return list(dict.fromkeys(ids))


def get_external_ai_recipes(limit=16, force_refresh=False):
    cache = _load_cache()
    if not force_refresh and _cache_fresh(cache):
        return list(cache.get("items", []))[:limit]

    recipes = []
    meal_ids = _candidate_meal_ids()
    for meal_id in meal_ids:
        if len(recipes) >= limit:
            break
        meal = _fetch_meal_by_id(meal_id)
        if not meal:
            continue
        if not _is_healthier_meal(meal):
            continue
        recipes.append(_to_recipe(meal))

    if recipes:
        _save_cache(recipes)
        return recipes

    # fallback op bestaande cache (ook als die stale is)
    if cache and cache.get("items"):
        return list(cache.get("items", []))[:limit]
    return []
