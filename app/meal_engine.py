import json
from pathlib import Path
import random
from datetime import datetime
import re


def load_recipes(path="app/recipes.json"):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _cuisine_bias(recipe, settings):
    nutrition = settings.get("nutrition", {})
    west_pref = float(nutrition.get("west_europe_preference", 2.2) or 0)
    asian_penalty = float(nutrition.get("asian_penalty", 2.8) or 0)

    tags = {str(tag).strip().lower() for tag in recipe.get("tags", [])}
    text_parts = [str(recipe.get("name", "")).lower(), str(recipe.get("description", "")).lower(), " ".join(tags)]
    for ingredient in recipe.get("ingredients", []):
        text_parts.append(str(ingredient.get("name", "")).lower())
    text = " ".join(part for part in text_parts if part)

    west_markers = {
        "west-europe",
        "belgian",
        "dutch",
        "french",
        "german",
        "british",
        "irish",
        "mediterranean",
        "italian",
        "spanish",
        "portuguese",
        "greek",
    }
    asian_markers = {
        "asian",
        "thai",
        "vietnamese",
        "japanese",
        "korean",
        "chinese",
        "indian",
        "indonesian",
        "malaysian",
    }

    score = 0.0
    if any(marker in tags or marker in text for marker in west_markers):
        score += west_pref
    if any(marker in tags or marker in text for marker in asian_markers):
        score -= asian_penalty
    return score


def _recipe_score(recipe, settings, options):
    family = settings["family"]
    nutrition = settings["nutrition"]

    likes = set(family.get("likes", []))
    dislikes = set(family.get("dislikes", []))

    score = 0.0

    for tag in recipe.get("tags", []):
        if tag in likes:
            if tag == "fish" and not options.get("prefer_fish"):
                score += 0.2
            else:
                score += 2.0
        if tag in dislikes:
            score -= 2.0
        if tag == "favorite":
            score += 1.25

    protein = recipe["nutrition"].get("protein", 0)
    carbs = recipe["nutrition"].get("carbs", 0)

    protein_weight = nutrition.get("high_protein_weight", 1.0)
    carb_weight = nutrition.get("low_carb_weight", 1.0)

    if options.get("high_protein"):
        protein_weight += 0.4
    if options.get("low_carb"):
        carb_weight += 0.2

    score += (protein / 10.0) * protein_weight

    # Keep carbs in balance instead of hard-avoiding them: occasional pasta/rice/potatoes are fine.
    score -= (max(carbs - 18, 0) / 16.0) * carb_weight
    if 20 <= carbs <= 48:
        score += 0.55
    elif carbs > 55:
        score -= 0.25

    if options.get("prefer_fish") and "fish" in recipe.get("tags", []):
        score += 1.5

    score += _cuisine_bias(recipe, settings)

    # Give externally sourced AI meals a small boost so they actually appear in rotation.
    if str(recipe.get("id", "")).startswith("ext_"):
        score += 0.95

    rating = int(recipe.get("rating") or 3)
    rating = max(1, min(5, rating))
    # Higher rated recipes are preferred and can show up more often in generated weeks.
    score += (rating - 3) * 0.55

    return score


def _day_is_weekend(day_iso):
    weekday = datetime.strptime(day_iso, "%Y-%m-%d").weekday()  # Monday=0
    return weekday in {4, 5, 6}  # Friday/Saturday/Sunday


def _has_tag(recipe, tag):
    return tag in recipe.get("tags", [])


def _is_pasta_like(recipe):
    if _has_tag(recipe, "pasta"):
        return True
    name = (recipe.get("name") or "").lower()
    return "pasta" in name or "spaghetti" in name


def _max_occurrences(recipe, day_count):
    rotation = (recipe.get("rotation_limit") or "").lower().strip()
    rating = max(1, min(5, int(recipe.get("rating") or 3)))
    if not rotation:
        # Default diversity guardrails for meals without explicit rotation settings.
        recipe_id = str(recipe.get("id", ""))
        if recipe_id.startswith("ext_"):
            # External AI meals should be rotated aggressively to keep variety high.
            base = max(1, int((day_count + 6) // 7))
            return min(day_count, base + (1 if rating >= 4 else 0))
        base = max(2, int((day_count + 3) // 4))
        return min(day_count, base + max(0, rating - 3))
    if rotation == "2_per_week":
        base = max(1, int((day_count * 2 + 6) // 7))
        return min(day_count, base + (1 if rating >= 4 else 0))
    if rotation == "1_per_week":
        base = max(1, int((day_count + 6) // 7))
        return min(day_count, base + (1 if rating == 5 else 0))
    if rotation == "1_per_month":
        return max(1, int((day_count + 29) // 30))
    return None


def _blocked_by_neighbors(recipe, prev_recipe=None, next_recipe=None):
    if prev_recipe is not None and _has_tag(prev_recipe, "fish") and _has_tag(recipe, "fish"):
        return True
    if next_recipe is not None and _has_tag(next_recipe, "fish") and _has_tag(recipe, "fish"):
        return True
    if prev_recipe is not None and _is_pasta_like(prev_recipe) and _is_pasta_like(recipe):
        return True
    if next_recipe is not None and _is_pasta_like(next_recipe) and _is_pasta_like(recipe):
        return True
    return False


def _normalize_token(value):
    return str(value or "").strip().lower()


def _expand_allergy_tokens(token):
    base = _normalize_token(token)
    if not base:
        return set()

    expanded = {base}
    citrus_aliases = {
        "citroen",
        "citroensap",
        "citroenzeste",
        "lemon",
        "lemon juice",
        "lemon zest",
        "limoen",
        "limoensap",
        "limoenzeste",
        "lime",
        "lime juice",
        "lime zest",
    }

    if base in citrus_aliases:
        expanded.update(citrus_aliases)
    return expanded


def _recipe_contains_allergy(recipe, allergy):
    tokens = _expand_allergy_tokens(allergy)
    if not tokens:
        return False

    # 1) Explicit allergen metadata
    recipe_allergens = {_normalize_token(a) for a in recipe.get("allergens", [])}
    if tokens.intersection(recipe_allergens):
        return True

    # 2) Ingredient names, tags and recipe name (for user-defined intolerances like "citroen")
    parts = [_normalize_token(recipe.get("name", ""))]
    parts.extend(_normalize_token(tag) for tag in recipe.get("tags", []))
    for ing in recipe.get("ingredients", []):
        parts.append(_normalize_token(ing.get("name", "")))
    haystack = " ".join(part for part in parts if part)
    if not haystack:
        return False

    # Match full token boundaries when possible, fallback to substring for multi-word values.
    for token in tokens:
        if re.search(rf"(^|[^a-z0-9]){re.escape(token)}([^a-z0-9]|$)", haystack):
            return True
        if token in haystack:
            return True
    return False


def _is_allowed(recipe, settings, allergies_override=None):
    if allergies_override is None:
        allergies = {_normalize_token(a) for a in settings["family"].get("allergies", [])}
    else:
        allergies = {_normalize_token(a) for a in allergies_override}

    allergies = {a for a in allergies if a}
    return not any(_recipe_contains_allergy(recipe, allergy) for allergy in allergies)


def generate_plan(cook_days, settings, options, allergies_override=None, custom_recipes=None, include_base_recipes=True):
    base = list(load_recipes()) if include_base_recipes else []
    all_recipes = base + list(custom_recipes or [])
    recipes = [r for r in all_recipes if _is_allowed(r, settings, allergies_override=allergies_override)]
    if not recipes:
        return []

    ranked = sorted(
        recipes,
        key=lambda r: _recipe_score(r, settings, options),
        reverse=True,
    )

    plan = []
    used = {}
    fish_count = 0

    custom_pool = [r for r in ranked if str(r.get("id", "")).startswith("custom_")]
    min_fish = options.get("min_fish", settings["nutrition"].get("weekly_min_fish", 0))

    for day_idx, day in enumerate(cook_days):
        best = None
        best_score = float("-inf")
        prev_recipe = None
        if plan:
            prev_id = plan[-1]["meal_id"]
            prev_recipe = next((r for r in recipes if r["id"] == prev_id), None)
        remaining_days = len(cook_days) - day_idx

        # Occasionally inject a custom meal to diversify the week.
        if custom_pool and random.random() < 0.35:
            best_custom = None
            best_custom_score = float("-inf")
            for recipe in custom_pool:
                max_occ = _max_occurrences(recipe, len(cook_days))
                if max_occ is not None and used.get(recipe["id"], 0) >= max_occ:
                    continue
                if _blocked_by_neighbors(recipe, prev_recipe=prev_recipe):
                    continue
                rating = max(1, min(5, int(recipe.get("rating") or 3)))
                repeat_penalty = used.get(recipe["id"], 0) * max(1.15, 2.85 - (rating * 0.3))
                score = _recipe_score(recipe, settings, options) - repeat_penalty + random.uniform(-0.3, 1.0)
                if _has_tag(recipe, "heavy"):
                    score += 0.9 if _day_is_weekend(day) else -0.45
                if score > best_custom_score:
                    best_custom = recipe
                    best_custom_score = score
            if best_custom is not None:
                best = best_custom
                best_score = best_custom_score

        for recipe in ranked:
            max_occ = _max_occurrences(recipe, len(cook_days))
            if max_occ is not None and used.get(recipe["id"], 0) >= max_occ:
                continue

            if _blocked_by_neighbors(recipe, prev_recipe=prev_recipe):
                continue

            rating = max(1, min(5, int(recipe.get("rating") or 3)))
            repeat_penalty = used.get(recipe["id"], 0) * max(1.2, 2.9 - (rating * 0.3))
            score = _recipe_score(recipe, settings, options) - repeat_penalty + random.uniform(-0.6, 0.6)

            if _has_tag(recipe, "heavy"):
                score += 0.9 if _day_is_weekend(day) else -0.45

            if min_fish and fish_count < min_fish and _has_tag(recipe, "fish"):
                score += 0.8
            if min_fish and fish_count >= min_fish and _has_tag(recipe, "fish"):
                score -= 0.35

            fish_missing = max(min_fish - fish_count, 0)
            if fish_missing and remaining_days <= fish_missing + 1 and _has_tag(recipe, "fish"):
                score += 1.1

            if score > best_score:
                best = recipe
                best_score = score

        if best is None:
            continue

        plan.append({"date": day, "meal_id": best["id"], "meal_name": best["name"]})
        used[best["id"]] = used.get(best["id"], 0) + 1
        if _has_tag(best, "fish"):
            fish_count += 1

    return sorted(plan, key=lambda item: item["date"])


def recipes_by_id():
    return {r["id"]: r for r in load_recipes()}


def select_best_recipe(
    settings,
    options,
    day_iso=None,
    prev_recipe=None,
    next_recipe=None,
    allergies_override=None,
    excluded_ids=None,
    recent_ids=None,
    custom_recipes=None,
    include_base_recipes=True,
):
    excluded = set(excluded_ids or [])
    recent_usage = {}
    for rid in recent_ids or []:
        key = str(rid or "").strip()
        if not key:
            continue
        recent_usage[key] = recent_usage.get(key, 0) + 1
    candidates = []
    base = list(load_recipes()) if include_base_recipes else []
    all_recipes = base + list(custom_recipes or [])
    day_count = max(7, len(all_recipes))
    for recipe in all_recipes:
        if recipe["id"] in excluded:
            continue
        if not _is_allowed(recipe, settings, allergies_override=allergies_override):
            continue
        max_occ = _max_occurrences(recipe, day_count)
        if max_occ is not None and max_occ <= 0:
            continue
        if _blocked_by_neighbors(recipe, prev_recipe=prev_recipe, next_recipe=next_recipe):
            continue
        candidates.append(recipe)

    if not candidates:
        return None

    def score(recipe):
        value = _recipe_score(recipe, settings, options)
        rating = max(1, min(5, int(recipe.get("rating") or 3)))
        recent_penalty = max(0.65, 1.5 - (rating * 0.12))
        value -= recent_usage.get(recipe.get("id"), 0) * recent_penalty
        if _has_tag(recipe, "heavy"):
            if day_iso and _day_is_weekend(day_iso):
                value += 0.7
            else:
                value -= 0.35
        return value

    ranked = sorted(candidates, key=score, reverse=True)
    top_k = ranked[: min(6, len(ranked))]
    return random.choice(top_k)
