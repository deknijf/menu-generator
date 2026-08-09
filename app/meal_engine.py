import json
from pathlib import Path
import random
from datetime import datetime
import re

from .food_matching import bevat as _bevat_ingredient
from .food_matching import maak_hooiberg as _hooiberg_van

# Wat je niet lust hoort zeldzaam te zijn, niet onmogelijk: af en toe eens iets
# met paddenstoelen houdt de planning gevarieerd zonder dat het een gewoonte wordt.
KANS_NIET_LEKKER = 0.07


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

    # De Engelse namen blijven staan voor recepten uit een oudere versie.
    west_markers = {
        "west-europees", "west-europe",
        "belgisch", "belgian",
        "nederlands", "dutch",
        "frans", "french",
        "duits", "german",
        "brits", "british",
        "iers", "irish",
        "mediterraans", "mediterranean",
        "italiaans", "italian",
        "spaans", "spanish",
        "portugees", "portuguese",
        "grieks", "greek",
    }
    asian_markers = {
        "aziatisch", "asian",
        "thais", "thai",
        "vietnamees", "vietnamese",
        "japans", "japanese",
        "koreaans", "korean",
        "chinees", "chinese",
        "indisch", "indian",
        "indonesisch", "indonesian",
        "maleisisch", "malaysian",
    }

    score = 0.0
    if any(marker in tags or marker in text for marker in west_markers):
        score += west_pref
    if any(marker in tags or marker in text for marker in asian_markers):
        score -= asian_penalty
    return score


# Waarden voor recepten waar geen voedingsgegevens bij zitten: een doorsnee
# avondmaal, zodat ze niet gestraft worden voor ontbrekende data.
NEUTRAAL_EIWIT = 30.0
NEUTRAAL_KOOLHYDRATEN = 35.0


def _recipe_score(recipe, settings, options):
    family = settings["family"]
    nutrition = settings["nutrition"]

    likes = set(family.get("likes", []))
    dislikes = set(family.get("dislikes", []))

    score = 0.0

    # Voorkeuren worden op dezelfde manier herkend als allergieen: wie "kip" als
    # favoriet opgeeft, bedoelt ook kipfilet, en wie "paddenstoelen" niet lust
    # bedoelt ook shiitake. Een vergelijking op exacte tags miste dat.
    tekst = _hooiberg_van(recipe) if likes or dislikes else ""
    for voorkeur in likes:
        if not _bevat_ingredient(recipe, voorkeur, tekst):
            continue
        # Vis is een uitzondering: dat wordt pas een echte plus als je er
        # deze week ook om vraagt, anders zwemt de hele week in de vis.
        score += 0.2 if voorkeur == "vis" and not options.get("prefer_fish") else 2.0

    for afkeer in dislikes:
        if _bevat_ingredient(recipe, afkeer, tekst):
            score -= 2.0

    if _has_tag(recipe, "favoriet"):
        score += 1.25

    # Ontbrekende voedingswaarden zijn onbekend, niet nul. Zonder deze terugval
    # scoort elk geimporteerd recept (protein 0) structureel lager dan een
    # zelf ingevoerd recept, en kiest de planner altijd dezelfde handvol.
    protein = float(recipe["nutrition"].get("protein") or 0) or NEUTRAAL_EIWIT
    carbs = float(recipe["nutrition"].get("carbs") or 0) or NEUTRAAL_KOOLHYDRATEN

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

    if options.get("prefer_fish") and _has_tag(recipe, "vis"):
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


# Nederlands is de norm. De Engelse varianten staan erbij voor recepten en
# voorkeuren die nog uit een oudere versie komen; zonder die ingang stopte de
# vis-op-vis-regel stil met werken.
_TAG_ALIASSEN = {
    "vis": ("vis", "fish", "zalm", "kabeljauw", "tonijn"),
    "zwaar": ("zwaar", "heavy"),
    "pasta": ("pasta", "spaghetti"),
    "kip": ("kip", "chicken", "gevogelte", "kalkoen"),
    "rund": ("rund", "beef"),
    "vegetarisch": ("vegetarisch", "vegetarian"),
    "favoriet": ("favoriet", "favorite"),
}


def _has_tag(recipe, tag):
    tags = {str(t).strip().lower() for t in recipe.get("tags", [])}
    return bool(tags.intersection(_TAG_ALIASSEN.get(tag, (tag,))))


def _is_pasta_like(recipe):
    if _has_tag(recipe, "pasta"):
        return True
    name = (recipe.get("name") or "").lower()
    return "pasta" in name or "spaghetti" in name


def _primary_protein_key(recipe):
    tags = {str(tag or "").strip().lower() for tag in recipe.get("tags", [])}
    text_parts = [str(recipe.get("name", "")).lower(), str(recipe.get("description", "")).lower(), " ".join(tags)]
    for ingredient in recipe.get("ingredients", []):
        text_parts.append(str(ingredient.get("name", "")).lower())
    text = " ".join(part for part in text_parts if part)

    protein_markers = [
        ("vis", ["fish", "vis", "zalm", "kabeljauw", "tonijn", "salmon", "cod", "tuna"]),
        ("kip", ["kip", "chicken", "kalkoen", "turkey"]),
        ("rund", ["rund", "beef", "gehakt", "steak", "hamburger", "bolognese"]),
        ("varken", ["varken", "pork", "ham", "spek", "bacon", "worst", "sausage"]),
        ("schaaldieren", ["garnaal", "garnalen", "shrimp", "prawn", "scampi"]),
        ("peulvrucht", ["linzen", "lentil", "kikkererwt", "chickpea", "bonen", "beans"]),
        ("ei", ["ei", "egg", "omelet", "frittata"]),
        ("kaas", ["kaas", "cheese", "halloumi", "mozzarella", "feta"]),
    ]
    for key, markers in protein_markers:
        if key in tags or any(marker in text for marker in markers):
            return key
    return "other"


def _starch_key(recipe):
    tags = {str(tag or "").strip().lower() for tag in recipe.get("tags", [])}
    text_parts = [str(recipe.get("name", "")).lower(), str(recipe.get("description", "")).lower(), " ".join(tags)]
    for ingredient in recipe.get("ingredients", []):
        text_parts.append(str(ingredient.get("name", "")).lower())
    text = " ".join(part for part in text_parts if part)

    starch_markers = [
        ("pasta", ["pasta", "spaghetti", "tagliatelle", "penne", "fusilli", "lasagne"]),
        ("rijst", ["rijst", "rice", "risotto"]),
        ("aardappel", ["aardappel", "aardappelen", "krieltjes", "patat", "potato"]),
        ("brood", ["brood", "wrap", "toast", "baguette"]),
        ("graan", ["quinoa", "couscous", "bulgur"]),
    ]
    for key, markers in starch_markers:
        if key in tags or any(marker in text for marker in markers):
            return key
    return "none"


def _vegetable_key(recipe):
    """De hoofdgroente van een gerecht, of "none".

    Zonder deze dimensie kan een week vier keer bloemkool bevatten zolang de
    eiwitbron en het zetmeel wisselen.
    """
    tags = {str(tag or "").strip().lower() for tag in recipe.get("tags", [])}
    delen = [str(recipe.get("name", "")).lower(), " ".join(tags)]
    for ingredient in recipe.get("ingredients", []):
        delen.append(str(ingredient.get("name", "")).lower())
    tekst = " ".join(deel for deel in delen if deel)

    markers = [
        ("bloemkool", ["bloemkool", "cauliflower"]),
        ("broccoli", ["broccoli"]),
        ("spinazie", ["spinazie", "spinach"]),
        ("wortel", ["wortel", "peen", "carrot"]),
        ("prei", ["prei", "leek"]),
        ("courgette", ["courgette", "zucchini"]),
        ("aubergine", ["aubergine", "eggplant"]),
        ("paprika", ["paprika"]),
        ("kool", ["spruit", "boerenkool", "spitskool", "witte kool", "rode kool"]),
        ("champignon", ["champignon", "paddenstoel", "mushroom"]),
        ("tomaat", ["tomaat", "tomaten", "tomato"]),
        ("witloof", ["witloof", "chicon"]),
        ("pompoen", ["pompoen", "pumpkin"]),
        ("venkel", ["venkel", "fennel"]),
        ("boon", ["sperzieboon", "prinsessenboon", "boontjes"]),
        ("erwt", ["erwten", "doperwten"]),
    ]
    for sleutel, woorden in markers:
        if sleutel in tags or any(woord in tekst for woord in woorden):
            return sleutel
    return "none"


def _variety_penalty(recipe, recent_recipes):
    if not recent_recipes:
        return 0.0

    penalty = 0.0
    recipe_id = str(recipe.get("id", "")).strip()
    recent_ids = [str(item.get("id", "")).strip() for item in recent_recipes]
    if recipe_id:
        for steps_ago, recent_id in enumerate(reversed(recent_ids), start=1):
            if recipe_id != recent_id:
                continue
            if steps_ago == 1:
                penalty += 12.0
            elif steps_ago == 2:
                penalty += 9.0
            elif steps_ago <= 4:
                penalty += 6.5
            else:
                penalty += 4.0

    protein = _primary_protein_key(recipe)
    recent_proteins = [_primary_protein_key(item) for item in recent_recipes]
    if recent_proteins:
        if protein == recent_proteins[-1]:
            penalty += 4.2
        if len(recent_proteins) >= 2 and protein == recent_proteins[-2]:
            penalty += 2.1
        penalty += recent_proteins.count(protein) * 1.35

    starch = _starch_key(recipe)
    recent_starches = [_starch_key(item) for item in recent_recipes if _starch_key(item) != "none"]
    if starch != "none" and recent_starches:
        if starch == recent_starches[-1]:
            penalty += 2.35
        if len(recent_starches) >= 2 and starch == recent_starches[-2]:
            penalty += 1.1
        # Oplopend: de derde pasta in een week kost fors meer dan de tweede.
        herhalingen = recent_starches.count(starch)
        penalty += herhalingen * 1.8 + max(0, herhalingen - 1) * 3.0

    # Hoofdgroente, zodat je geen week lang bloemkool eet ook al wisselt de rest.
    vegetable = _vegetable_key(recipe)
    recent_vegetables = [_vegetable_key(item) for item in recent_recipes]
    if vegetable != "none":
        herhalingen = recent_vegetables.count(vegetable)
        if herhalingen:
            penalty += herhalingen * 2.2 + max(0, herhalingen - 1) * 2.5

    if recent_recipes:
        last_recipe = recent_recipes[-1]
        if _has_tag(last_recipe, "zwaar") and _has_tag(recipe, "zwaar"):
            penalty += 1.3
        if _has_tag(last_recipe, "vis") and _has_tag(recipe, "vis"):
            penalty += 1.6

    return penalty


# Richtwaarde voor een avondmaal per persoon. De planner mikt op dit gemiddelde
# over de hele periode, niet per dag: een uitschieter mag, zolang andere dagen
# lichter zijn.
DOEL_KCAL_PER_PORTIE = 700
KCAL_STRAF_PER_100 = 0.9


def _recipe_kcal(recipe):
    try:
        return float((recipe.get("nutrition") or {}).get("calories") or 0)
    except (TypeError, ValueError):
        return 0.0


def _kcal_penalty(recipe, verbruikt, dagen_gepland, totaal_dagen, doel=DOEL_KCAL_PER_PORTIE):
    """Straft gerechten die het weekgemiddelde uit balans trekken.

    Het budget is `doel * totaal_dagen`. Wat er nog over is, gedeeld door de
    resterende dagen, is de ruimte voor vandaag. Een gerecht dat daar ruim
    boven zit krijgt een oplopende straf; eronder blijven kost niets. Zo volgt
    er vanzelf een lichtere dag na een zware, zonder harde regels.
    """
    kcal = _recipe_kcal(recipe)
    if kcal <= 0 or totaal_dagen <= 0:
        return 0.0

    resterend = max(1, totaal_dagen - dagen_gepland)
    ruimte = (doel * totaal_dagen - verbruikt) / resterend
    overschot = kcal - ruimte
    if overschot <= 0:
        return 0.0
    return (overschot / 100.0) * KCAL_STRAF_PER_100


# Hoeveel dagen er minstens tussen twee keer hetzelfde gerecht zitten.
ROTATION_PERIOD_DAYS = {
    "1_per_week": 7,
    "1_per_2_weeks": 14,
    "1_per_month": 30,
    "1_per_2_months": 60,
}


def _max_occurrences(recipe, day_count):
    rotation = (recipe.get("rotation_limit") or "").lower().strip()
    if not rotation:
        # Default diversity guardrails for meals without explicit rotation settings.
        recipe_id = str(recipe.get("id", ""))
        if recipe_id.startswith("ext_"):
            # External AI meals should be rotated aggressively to keep variety high.
            return min(day_count, max(1, int((day_count + 6) // 7)))
        return min(day_count, max(1, int((day_count + 4) // 5)))
    period = ROTATION_PERIOD_DAYS.get(rotation)
    if period is None:
        return None
    # Naar boven afronden: in een periode van 10 dagen mag een weekgerecht 2x.
    return max(1, int((day_count + period - 1) // period))


def _blocked_by_neighbors(recipe, prev_recipe=None, next_recipe=None):
    if prev_recipe is not None and _has_tag(prev_recipe, "vis") and _has_tag(recipe, "vis"):
        return True
    if next_recipe is not None and _has_tag(next_recipe, "vis") and _has_tag(recipe, "vis"):
        return True
    if prev_recipe is not None and _is_pasta_like(prev_recipe) and _is_pasta_like(recipe):
        return True
    if next_recipe is not None and _is_pasta_like(next_recipe) and _is_pasta_like(recipe):
        return True
    return False


def _normalize_token(value):
    return str(value or "").strip().lower()


def _recipe_contains_allergy(recipe, allergy):
    """True als het recept dit allergeen bevat, in welke schrijfwijze ook.

    De herkenning zelf zit in food_matching: die kent de synoniemen, de
    Nederlandse samenstellingen en de EU-allergenen. Hier blijft alleen de
    vraagstelling over.
    """
    return _bevat_ingredient(recipe, allergy)


def _is_allowed(recipe, settings, allergies_override=None):
    if allergies_override is None:
        allergies = {_normalize_token(a) for a in settings["family"].get("allergies", [])}
    else:
        allergies = {_normalize_token(a) for a in allergies_override}

    allergies = {a for a in allergies if a}
    return not any(_recipe_contains_allergy(recipe, allergy) for allergy in allergies)


def bevat_afkeer(recipe, dislikes):
    """True als het recept iets bevat dat deze huishouding niet lust."""
    termen = [t for t in dislikes or [] if _normalize_token(t)]
    if not termen:
        return False
    tekst = _hooiberg_van(recipe)
    return any(_bevat_ingredient(recipe, term, tekst) for term in termen)


def _filter_afkeer(recipes, dislikes, kans=KANS_NIET_LEKKER):
    """Haalt gerechten met iets onsmakelijks eruit, op een enkele uitzondering na.

    Blijft er niets over, dan gaat de afkeer voor op niets kunnen plannen: een
    gerecht dat je matig vindt is beter dan een lege week.
    """
    if not dislikes:
        return list(recipes)

    overgebleven = [r for r in recipes if not bevat_afkeer(r, dislikes) or random.random() < kans]
    return overgebleven or list(recipes)


def generate_plan(
    cook_days,
    settings,
    options,
    allergies_override=None,
    custom_recipes=None,
    include_base_recipes=True,
    dislikes_override=None,
):
    base = list(load_recipes()) if include_base_recipes else []
    all_recipes = base + list(custom_recipes or [])
    recipes = [r for r in all_recipes if _is_allowed(r, settings, allergies_override=allergies_override)]
    if not recipes:
        return []

    afkeer = settings["family"].get("dislikes", []) if dislikes_override is None else dislikes_override
    recipes = _filter_afkeer(recipes, afkeer)

    ranked = sorted(
        recipes,
        key=lambda r: _recipe_score(r, settings, options),
        reverse=True,
    )

    plan = []
    used = {}
    fish_count = 0
    # Loopt mee met de kcal die de week tot nu toe verbruikt heeft, zodat na een
    # zware dag lichtere gerechten voorgaan.
    verbruikte_kcal = 0.0
    doel_kcal = float(settings.get("nutrition", {}).get("target_kcal_per_serving") or DOEL_KCAL_PER_PORTIE)

    custom_pool = [r for r in ranked if str(r.get("id", "")).startswith("custom_")]
    min_fish = options.get("min_fish", settings["nutrition"].get("weekly_min_fish", 0))

    for day_idx, day in enumerate(cook_days):
        best = None
        best_score = float("-inf")
        prev_recipe = None
        if plan:
            prev_id = plan[-1]["meal_id"]
            prev_recipe = next((r for r in recipes if r["id"] == prev_id), None)
        recent_recipes = []
        for item in plan[-6:]:
            recipe = next((r for r in recipes if r["id"] == item["meal_id"]), None)
            if recipe is not None:
                recent_recipes.append(recipe)
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
                score = (
                    _recipe_score(recipe, settings, options)
                    - repeat_penalty
                    - _variety_penalty(recipe, recent_recipes)
                    - _kcal_penalty(recipe, verbruikte_kcal, day_idx, len(cook_days), doel_kcal)
                    + random.uniform(-0.3, 1.0)
                )
                if _has_tag(recipe, "zwaar"):
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
            score = (
                _recipe_score(recipe, settings, options)
                - repeat_penalty
                - _variety_penalty(recipe, recent_recipes)
                - _kcal_penalty(recipe, verbruikte_kcal, day_idx, len(cook_days), doel_kcal)
                + random.uniform(-0.6, 0.6)
            )

            if _has_tag(recipe, "zwaar"):
                score += 0.9 if _day_is_weekend(day) else -0.45

            if min_fish and fish_count < min_fish and _has_tag(recipe, "vis"):
                score += 0.8
            if min_fish and fish_count >= min_fish and _has_tag(recipe, "vis"):
                score -= 0.35

            fish_missing = max(min_fish - fish_count, 0)
            if fish_missing and remaining_days <= fish_missing + 1 and _has_tag(recipe, "vis"):
                score += 1.1

            if score > best_score:
                best = recipe
                best_score = score

        if best is None:
            continue

        plan.append({"date": day, "meal_id": best["id"], "meal_name": best["name"]})
        used[best["id"]] = used.get(best["id"], 0) + 1
        # Een gerecht zonder schatting telt als de richtwaarde. Anders zou het
        # geen budget verbruiken en zouden juist die gerechten voorgetrokken
        # worden omdat ze "gratis" lijken.
        verbruikte_kcal += _recipe_kcal(best) or doel_kcal
        if _has_tag(best, "vis"):
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
    dislikes_override=None,
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
    recipe_by_id = {str(recipe.get("id", "")).strip(): recipe for recipe in all_recipes}
    recent_recipes = [recipe_by_id.get(str(rid or "").strip()) for rid in (recent_ids or [])]
    recent_recipes = [recipe for recipe in recent_recipes if recipe is not None][-6:]
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

    afkeer = settings["family"].get("dislikes", []) if dislikes_override is None else dislikes_override
    candidates = _filter_afkeer(candidates, afkeer)

    if not candidates:
        return None

    def score(recipe):
        value = _recipe_score(recipe, settings, options)
        rating = max(1, min(5, int(recipe.get("rating") or 3)))
        recent_penalty = max(0.65, 1.5 - (rating * 0.12))
        value -= recent_usage.get(recipe.get("id"), 0) * recent_penalty
        value -= _variety_penalty(recipe, recent_recipes)
        if _has_tag(recipe, "zwaar"):
            if day_iso and _day_is_weekend(day_iso):
                value += 0.7
            else:
                value -= 0.35
        return value

    ranked = sorted(candidates, key=score, reverse=True)
    top_k = ranked[: min(6, len(ranked))]
    return random.choice(top_k)
