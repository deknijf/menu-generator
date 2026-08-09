import hashlib
import json
import re
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import dotenv_values, set_key

from .logging_setup import get_logger

logger = get_logger(__name__)

ENV_PATH = Path(".env")
CACHE_PATH = Path("data/openrouter_menu_cache.json")
CACHE_SCHEMA_VERSION = 1
CACHE_TTL_SECONDS = 6 * 60 * 60
DEFAULT_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_OPENROUTER_MODEL = "openai/gpt-4o-mini"
DEFAULT_MENU_PROMPT = (
    "Genereer praktische avondmaaltijden met een Europese insteek. "
    "Hou recepten haalbaar voor thuis, met beperkte ingrediënten, duidelijke bereidingsstappen "
    "en boodschappen die makkelijk in een Belgische supermarkt te vinden zijn. "
    "Vermijd extreme diëten, exotische ingrediënten en onrealistische bereidingen."
)
DEFAULT_BLOCKED_ALLERGIES = []
ALLOWED_ROTATION_LIMITS = {"1_per_week", "1_per_2_weeks", "1_per_month", "1_per_2_months"}
# "2_per_week" bestond vroeger en zit nog in oude caches.
LEGACY_ROTATION_LIMITS = {"2_per_week": "1_per_week"}
DEFAULT_SERVINGS = 2
MEAT_TAGS = {
    "fish": ["fish", "vis", "zalm", "kabeljauw", "tonijn", "salmon", "cod", "tuna"],
    "chicken": ["kip", "chicken", "kalkoen", "turkey"],
    "beef": ["rund", "beef", "gehakt", "steak", "hamburger", "bolognese"],
    "pasta": ["pasta", "spaghetti", "penne", "tagliatelle", "lasagne"],
    "rice": ["rijst", "rice", "risotto"],
    "potato": ["aardappel", "aardappelen", "krieltjes", "patat", "potato"],
    "west-europe": [
        "belgisch",
        "nederlands",
        "frans",
        "italiaans",
        "spaans",
        "grieks",
        "duits",
        "portugees",
        "europees",
    ],
}
ALLERGEN_MARKERS = {
    "fish": ["fish", "vis", "zalm", "kabeljauw", "tonijn", "salmon", "cod", "tuna"],
    "gluten": ["bloem", "pasta", "spaghetti", "brood", "paneermeel", "wrap", "noedels"],
    "lactose": ["melk", "room", "kaas", "boter", "parmezaan", "mozzarella", "yoghurt"],
    "soy": ["soja", "soy"],
    "peanut": ["pinda", "peanut"],
    "shellfish": ["garnaal", "garnalen", "scampi", "mossel", "krab", "kreeft"],
    "egg": ["ei", "eieren"],
}


def _decode_multiline(value):
    return str(value or "").replace("\\n", "\n").strip()


def _encode_multiline(value):
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n").strip()


def _split_tokens(value):
    items = re.split(r"[\n,;]+", str(value or ""))
    out = []
    for item in items:
        token = item.strip().lower()
        if token and token not in out:
            out.append(token)
    return out


def _load_env_values():
    if not ENV_PATH.exists():
        return {}
    return {key: "" if value is None else str(value) for key, value in dotenv_values(ENV_PATH).items()}


def get_admin_ai_config():
    env_values = _load_env_values()
    blocked_text = env_values.get("MENU_AI_BLOCKED_ALLERGIES", "")
    return {
        "url": (env_values.get("OPENROUTER_URL") or DEFAULT_OPENROUTER_URL).strip(),
        "api_token": (env_values.get("OPENROUTER_API_KEY") or "").strip(),
        "model": (env_values.get("OPENROUTER_MODEL") or DEFAULT_OPENROUTER_MODEL).strip(),
        "prompt": _decode_multiline(env_values.get("MENU_AI_PROMPT") or DEFAULT_MENU_PROMPT),
        "blocked_allergies": _split_tokens(blocked_text or ",".join(DEFAULT_BLOCKED_ALLERGIES)),
        "configured": bool((env_values.get("OPENROUTER_API_KEY") or "").strip()),
    }


def _save_env_value(key, value):
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not ENV_PATH.exists():
        ENV_PATH.write_text("", encoding="utf-8")
    set_key(str(ENV_PATH), key, value, quote_mode="auto")


def clear_admin_ai_cache():
    if CACHE_PATH.exists():
        CACHE_PATH.unlink()


def save_admin_ai_config(url, api_token, model, prompt, blocked_allergies):
    normalized_blocked = _split_tokens(blocked_allergies)
    _save_env_value("OPENROUTER_URL", str(url or DEFAULT_OPENROUTER_URL).strip() or DEFAULT_OPENROUTER_URL)
    _save_env_value("OPENROUTER_API_KEY", str(api_token or "").strip())
    _save_env_value("OPENROUTER_MODEL", str(model or DEFAULT_OPENROUTER_MODEL).strip() or DEFAULT_OPENROUTER_MODEL)
    _save_env_value("MENU_AI_PROMPT", _encode_multiline(prompt or DEFAULT_MENU_PROMPT))
    _save_env_value("MENU_AI_BLOCKED_ALLERGIES", ",".join(normalized_blocked))
    clear_admin_ai_cache()
    return get_admin_ai_config()


def _slugify(value):
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    return slug or "meal"


def _safe_float(value, fallback):
    try:
        return float(value)
    except Exception:
        return float(fallback)


def _normalize_tags(tags, name, description, ingredients):
    out = []
    for tag in tags or []:
        token = str(tag or "").strip().lower()
        if token and token not in out:
            out.append(token)
    haystack = " ".join(
        [
            str(name or "").lower(),
            str(description or "").lower(),
            *[str((ingredient or {}).get("name") or "").lower() for ingredient in ingredients or []],
        ]
    )
    for tag, markers in MEAT_TAGS.items():
        if any(marker in haystack for marker in markers) and tag not in out:
            out.append(tag)
    if not out:
        out.append("balanced")
    return out


def _normalize_allergens(allergens, ingredients):
    out = []
    for token in allergens or []:
        value = str(token or "").strip().lower()
        if value and value not in out:
            out.append(value)
    haystack = " ".join(str((ingredient or {}).get("name") or "").lower() for ingredient in ingredients or [])
    for allergen, markers in ALLERGEN_MARKERS.items():
        if allergen not in out and any(marker in haystack for marker in markers):
            out.append(allergen)
    return out


def _normalize_ingredients(items):
    output = []
    for item in items or []:
        name = str((item or {}).get("name") or "").strip().lower()
        if not name:
            continue
        output.append(
            {
                "name": name,
                "quantity": _safe_float((item or {}).get("quantity"), 1),
                "unit": str((item or {}).get("unit") or "stuk").strip().lower(),
            }
        )
    return output


def _normalize_preparation(steps, name):
    output = [str(step or "").strip() for step in (steps or []) if str(step or "").strip()]
    if output:
        return output
    recipe_name = str(name or "dit gerecht").strip().lower()
    return [
        "Bereid alle ingrediënten voor en meet alles af.",
        f"Bak of gaar {recipe_name} tot alles mooi gaar is.",
        "Werk af op smaak en serveer direct.",
    ]


def _normalize_rotation_limit(value):
    token = str(value or "1_per_week").strip().lower()
    token = LEGACY_ROTATION_LIMITS.get(token, token)
    return token if token in ALLOWED_ROTATION_LIMITS else "1_per_week"


def _extract_json_array(text):
    raw = str(text or "").strip()
    if raw.startswith("[") and raw.endswith("]"):
        return json.loads(raw)
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        return []
    return json.loads(match.group(0))


def _planner_context_payload(planner_context):
    context = planner_context or {}
    return {
        "high_protein": bool(context.get("high_protein")),
        "low_carb": bool(context.get("low_carb")),
        "prefer_fish": bool(context.get("prefer_fish")),
        "person_count": int(context.get("person_count") or 2),
        "base_servings": int(context.get("base_servings") or 2),
    }


def _cache_key(limit, config, planner_context=None):
    payload = {
        "limit": int(limit or 0),
        "url": config.get("url", ""),
        "model": config.get("model", ""),
        "prompt": config.get("prompt", ""),
        "blocked_allergies": config.get("blocked_allergies", []),
        "planner_context": _planner_context_payload(planner_context),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _load_cache():
    if not CACHE_PATH.exists():
        return {}
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(payload):
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_cached_items(key, limit):
    payload = _load_cache()
    if int(payload.get("schema_version") or 0) != CACHE_SCHEMA_VERSION:
        return []
    entries = payload.get("entries") or {}
    entry = entries.get(key) or {}
    fetched_at = int(entry.get("fetched_at") or 0)
    if not fetched_at or (int(time.time()) - fetched_at) >= CACHE_TTL_SECONDS:
        return []
    return list(entry.get("items") or [])[:limit]


def _store_cached_items(key, items):
    payload = _load_cache()
    if int(payload.get("schema_version") or 0) != CACHE_SCHEMA_VERSION:
        payload = {"schema_version": CACHE_SCHEMA_VERSION, "entries": {}}
    payload.setdefault("entries", {})
    payload["entries"][key] = {
        "fetched_at": int(time.time()),
        "items": items,
    }
    _save_cache(payload)


def _build_prompt(config, limit, planner_context=None):
    blocked = config.get("blocked_allergies") or []
    blocked_text = ", ".join(blocked) if blocked else "geen extra allergieën"
    admin_prompt = (config.get("prompt") or DEFAULT_MENU_PROMPT).strip()
    context = _planner_context_payload(planner_context)
    person_count = int(context.get("person_count") or 2)
    base_servings = int(context.get("base_servings") or 2)
    if context.get("high_protein") and context.get("low_carb"):
        planner_rules = (
            "De planner staat op meer proteïnen én minder koolhydraten. "
            "Kies dus vooral lichtere, eiwitrijke recepten. "
            "Streef per portie ongeveer naar 35-55g proteïne en meestal 15-40g koolhydraten."
        )
    elif context.get("high_protein"):
        planner_rules = (
            "De planner staat op meer proteïnen. "
            "Kies dus vooral eiwitrijke recepten, maar je mag iets vrijer omgaan met koolhydraten. "
            "Streef per portie ongeveer naar 35-55g proteïne."
        )
    elif context.get("low_carb"):
        planner_rules = (
            "De planner staat op minder koolhydraten. "
            "Beperk daarom aardappelen, rijst en pasta tot bescheiden porties, maar verbied ze niet volledig. "
            "Streef per portie meestal naar 15-35g koolhydraten."
        )
    else:
        planner_rules = (
            "De opties meer proteïnen en minder koolhydraten staan niet actief. "
            "Je mag dus vrijer kiezen binnen de West-Europese keuken, zolang de gerechten evenwichtig en praktisch blijven."
        )
    servings_rule = (
        f"De gebruiker plant nu voor {person_count} personen. "
        f"Noteer de JSON-ingrediëntenhoeveelheden altijd voor {DEFAULT_SERVINGS} personen en zet "
        f'"servings": {DEFAULT_SERVINGS} in elk item. De app schaalt die hoeveelheden zelf naar het '
        "gekozen aantal personen, dus reken ze niet vooraf om."
    )
    return f"""
Je bent een meal planner assistent.
Genereer exact {int(limit)} bruikbare avondmaaltijden voor een meal planner app.

Belangrijke regels:
- Geef uitsluitend geldige JSON terug.
- Geef een JSON-array terug, zonder markdown of extra tekst.
- Elk item volgt exact dit schema:
  {{
    "name": "string",
    "description": "string",
    "rating": 1-5,
    "tags": ["string"],
    "allergens": ["string"],
    "ingredients": [
      {{"name": "string", "quantity": number, "unit": "string"}}
    ],
    "preparation": ["string"],
    "protein": number,
    "carbs": number,
    "calories": number,
    "servings": 2,
    "rotation_limit": "1_per_week|1_per_2_weeks|1_per_month|1_per_2_months"
  }}
- Gebruik Nederlandse namen voor gerechten, ingrediënten en stappen.
- Maak realistische recepten voor een Belgische/Nederlandse supermarkt.
- Vermijd ingrediënten uit deze allergielijst absoluut: {blocked_text}.
- Gebruik maximaal 5 volwaardige hoofdingrediënten per recept.
- Kruiden, look, ui, peper, zout, citroensap, paprikapoeder, oregano en vergelijkbare smaakmakers tellen niet mee als volwaardig ingrediënt.
- Hou de recepten praktisch, duidelijk en niet te exotisch.
- Genereer de volledige set als een gevarieerd menu voor een periode: vermijd dubbele of bijna gelijke gerechten.
- Wissel binnen de set bewust af in eiwitbron, groente, kookstijl, sausstijl en koolhydraatbron.
- Zet niet te vaak hetzelfde type gerecht vlak na elkaar: varieer tussen kip, rund, vis, vegetarisch, aardappel, rijst, pasta en lichtere groentegerechten.
- {planner_rules}
- {servings_rule}

Extra richtlijnen van de admin:
{admin_prompt}
""".strip()


def _normalize_recipe(item, index, blocked_allergies):
    name = str((item or {}).get("name") or "").strip()
    if not name:
        return None
    description = str((item or {}).get("description") or "").strip()
    ingredients = _normalize_ingredients((item or {}).get("ingredients") or [])
    if not ingredients:
        return None
    tags = _normalize_tags((item or {}).get("tags") or [], name, description, ingredients)
    allergens = _normalize_allergens((item or {}).get("allergens") or [], ingredients)
    blocked = set(blocked_allergies or [])
    if blocked.intersection(allergens):
        return None
    rating = max(1, min(5, int(_safe_float((item or {}).get("rating"), 4))))
    nutrition = {
        "protein": _safe_float((item or {}).get("protein"), 30),
        "carbs": _safe_float((item or {}).get("carbs"), 28),
        "calories": _safe_float((item or {}).get("calories"), 520),
    }
    slug = _slugify(name)
    digest = hashlib.sha256(
        json.dumps(
            {
                "name": name,
                "ingredients": ingredients,
                "nutrition": nutrition,
                "rotation_limit": _normalize_rotation_limit((item or {}).get("rotation_limit") or "1_per_week"),
            },
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()[:10]
    return {
        "id": f"ext_llm_{slug}_{digest}_{index}",
        "name": name,
        "description": description or "AI gegenereerde maaltijdvariatie.",
        "image_url": "",
        "rating": rating,
        "tags": tags,
        "allergens": allergens,
        "ingredients": ingredients,
        "preparation": _normalize_preparation((item or {}).get("preparation") or [], name),
        "nutrition": nutrition,
        "rotation_limit": _normalize_rotation_limit((item or {}).get("rotation_limit") or "1_per_week"),
        "servings": DEFAULT_SERVINGS,
    }


def _request_openrouter(config, limit, planner_context=None):
    payload = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": "Je retourneert alleen JSON."},
            {"role": "user", "content": _build_prompt(config, limit, planner_context)},
        ],
        "temperature": 0.3,
    }
    data = json.dumps(payload).encode("utf-8")
    request = Request(
        config["url"],
        data=data,
        headers={
            "Authorization": f"Bearer {config['api_token']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=90) as response:
        raw = json.loads(response.read().decode("utf-8"))
    return str((((raw.get("choices") or [{}])[0]).get("message") or {}).get("content") or "")


def get_ai_menu_recipes(limit=16, force_refresh=False, planner_context=None):
    """Haalt maaltijden bij OpenRouter, met de cache als vangnet.

    Faalt de call, dan vallen we terug op de cache in plaats van de gebruiker met
    een lege planner achter te laten. Dat mag alleen niet stil gebeuren: een
    verlopen API-key of een gewijzigd model is anders onzichtbaar tot iemand het
    toevallig merkt. Elke terugval logt daarom waarom ze plaatsvond.
    """
    config = get_admin_ai_config()
    if not config.get("api_token"):
        logger.warning("Geen OpenRouter API-key geconfigureerd; AI-maaltijden overgeslagen.")
        return []

    key = _cache_key(limit, config, planner_context)
    if not force_refresh:
        cached = _load_cached_items(key, limit)
        if cached:
            logger.debug("AI-maaltijden uit cache (%d items).", len(cached))
            return cached

    try:
        content = _request_openrouter(config, limit, planner_context)
        raw_items = _extract_json_array(content)
    except HTTPError as exc:
        # 401/402/429 zijn de gevallen die je echt wil zien: key ongeldig,
        # krediet op, of rate limit bereikt.
        logger.error(
            "OpenRouter gaf HTTP %s (%s) voor model %s; terugval op cache.",
            exc.code, exc.reason, config.get("model"),
        )
        return _load_cached_items(key, limit)
    except (TimeoutError, URLError) as exc:
        logger.error("OpenRouter onbereikbaar (%s); terugval op cache.", exc)
        return _load_cached_items(key, limit)
    except (ValueError, json.JSONDecodeError) as exc:
        logger.error("OpenRouter gaf onleesbare JSON (%s); terugval op cache.", exc)
        return _load_cached_items(key, limit)
    except Exception:
        logger.exception("Onverwachte fout bij het ophalen van AI-maaltijden; terugval op cache.")
        return _load_cached_items(key, limit)

    if not isinstance(raw_items, list):
        logger.error("OpenRouter gaf geen JSON-array terug; terugval op cache.")
        return _load_cached_items(key, limit)

    blocked_allergies = config.get("blocked_allergies") or []
    recipes = []
    for index, item in enumerate(raw_items, start=1):
        recipe = _normalize_recipe(item, index, blocked_allergies)
        if recipe:
            recipes.append(recipe)

    afgekeurd = len(raw_items) - len(recipes)
    if afgekeurd:
        logger.info("%d van %d AI-recepten afgekeurd bij normalisatie.", afgekeurd, len(raw_items))

    if not recipes:
        logger.error("Alle %d AI-recepten afgekeurd; terugval op cache.", len(raw_items))
        return _load_cached_items(key, limit)

    _store_cached_items(key, recipes)
    logger.info("%d AI-maaltijden opgehaald via model %s.", len(recipes), config.get("model"))
    return recipes[:limit]
