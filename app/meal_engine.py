import json
from pathlib import Path
import random
from datetime import datetime


def load_recipes(path="app/recipes.json"):
    return json.loads(Path(path).read_text(encoding="utf-8"))


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

    # Give externally sourced AI meals a small boost so they actually appear in rotation.
    if str(recipe.get("id", "")).startswith("ext_"):
        score += 0.95

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
    if not rotation:
        # Default diversity guardrails for meals without explicit rotation settings.
        recipe_id = str(recipe.get("id", ""))
        if recipe_id.startswith("ext_"):
            # External AI meals should be rotated aggressively to keep variety high.
            return max(1, int((day_count + 6) // 7))
        return max(2, int((day_count + 3) // 4))
    if rotation == "2_per_week":
        return max(1, int((day_count * 2 + 6) // 7))
    if rotation == "1_per_week":
        return max(1, int((day_count + 6) // 7))
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


def _is_allowed(recipe, settings, allergies_override=None):
    if allergies_override is None:
        allergies = set(a.lower() for a in settings["family"].get("allergies", []))
    else:
        allergies = set(a.lower() for a in allergies_override)
    recipe_allergens = set(a.lower() for a in recipe.get("allergens", []))
    return not allergies.intersection(recipe_allergens)


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
                repeat_penalty = used.get(recipe["id"], 0) * 2.6
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

            repeat_penalty = used.get(recipe["id"], 0) * 2.6
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
    custom_recipes=None,
    include_base_recipes=True,
):
    excluded = set(excluded_ids or [])
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
        if _has_tag(recipe, "heavy"):
            if day_iso and _day_is_weekend(day_iso):
                value += 0.7
            else:
                value -= 0.35
        return value

    ranked = sorted(candidates, key=score, reverse=True)
    return ranked[0]
