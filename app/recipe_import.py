"""Recepten importeren van publieke websites.

Twee vormen, allebei door de gebruiker gestart:

  1. Eén receptpagina: plak de link, krijg het recept.
  2. Een overzichtspagina of site: verzamel de receptlinks die erop staan en
     importeer die in één keer.

De zware parsing komt van `recipe-scrapers`, dat honderden sites kent en per site
weet waar de ingredienten en stappen staan. Waar dat tekortschiet vult
`_SITE_AANVULLINGEN` aan.

Wat de import bewust *niet* doet:

  - Niets opslaan in de repo. Geimporteerde recepten gaan naar de database van de
    gebruiker die ze importeert. Ingredientenlijsten zijn feitelijk, maar
    bereidingsteksten en fotos zijn werk van de auteur; die horen niet in een
    publieke repository terecht te komen.
  - Geen paden ophalen die robots.txt verbiedt bij het verzamelen van links.
  - Niet hameren op een site: één verzoek tegelijk, met pauze ertussen.
"""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser

from .logging_setup import get_logger
from .units import metriek_uit_haakjes, naar_metriek, parse_getal, tekst_naar_metriek

logger = get_logger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122 Safari/537.36"
)
TIMEOUT_SECONDEN = 25
PAUZE_TUSSEN_VERZOEKEN = 1.0
MAX_PER_IMPORT = 20
MAX_PAGINA_BYTES = 4 * 1024 * 1024

# Paden die op een receptpagina wijzen. Bewust breed: liever een pagina te veel
# proberen dan een recept missen; wat geen recept blijkt valt vanzelf af.
RECEPT_PATRONEN = re.compile(r"/(recipes?|recept(en)?|gerecht(en)?|rezept|plat)/", re.I)


class ImportFout(Exception):
    """Import mislukt om een reden die de gebruiker moet zien."""


# --- Ophalen ---


def _haal_pagina(url):
    verzoek = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(verzoek, timeout=TIMEOUT_SECONDEN) as antwoord:
            return antwoord.read(MAX_PAGINA_BYTES)
    except urllib.error.HTTPError as exc:
        raise ImportFout(f"Server gaf HTTP {exc.code} voor {url}") from exc
    except urllib.error.URLError as exc:
        raise ImportFout(f"Kon {url} niet bereiken: {exc.reason}") from exc
    except Exception as exc:
        raise ImportFout(f"Onverwachte fout bij {url}: {exc}") from exc


def _robots_voor(url):
    onderdelen = urllib.parse.urlsplit(url)
    basis = f"{onderdelen.scheme}://{onderdelen.netloc}"
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(f"{basis}/robots.txt")
    try:
        parser.read()
    except Exception:
        return None
    return parser


def _mag_ophalen(parser, url):
    if parser is None:
        return True
    try:
        return parser.can_fetch(USER_AGENT, url)
    except Exception:
        return True


# --- Site-specifieke aanvullingen ---


def _dagelijksekost_stappen(html):
    """Haalt de volledige bereidingswijze uit de paginadata van Dagelijkse Kost.

    Hun schema.org-blok bevat maar twee stappen (de voorverwarm-instructies); de
    echte bereiding zit in de React-payload van dezelfde pagina. Die lezen we hier
    uit, zodat we niets hoeven op te halen wat hun robots.txt afschermt.
    """
    tekst = html.decode("utf-8", "replace") if isinstance(html, bytes) else html
    payload = ""
    for blok in re.finditer(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', tekst, re.S):
        try:
            payload += json.loads(blok.group(1))
        except Exception:
            continue
    if not payload:
        return []

    stappen = {}
    for treffer in re.finditer(r'"step":(\d+)', payload):
        venster = payload[treffer.end(): treffer.end() + 800]
        beschrijving = re.search(r'"description":"((?:[^"\\]|\\.)*)"', venster)
        if not beschrijving:
            continue
        try:
            inhoud = json.loads(f'"{beschrijving.group(1)}"').strip()
        except Exception:
            continue
        nummer = int(treffer.group(1))
        if inhoud and nummer not in stappen:
            stappen[nummer] = inhoud
    return [stappen[nummer] for nummer in sorted(stappen)]


_SITE_AANVULLINGEN = {
    "dagelijksekost.vrt.be": {"preparation": _dagelijksekost_stappen},
}


# --- Omzetten naar het model van de app ---


def _porties_uit(waarde, standaard=2):
    """recipeYield is van alles: 4, "4 servings", "4-6 personen"."""
    if waarde is None:
        return standaard
    getallen = re.findall(r"\d+", str(waarde))
    if not getallen:
        return standaard
    return min(6, max(1, int(getallen[0])))


def _porties_uit_jsonld(html):
    """Leest recipeYield rechtstreeks uit de schema.org-data van de pagina.

    recipe-scrapers gooit voor sommige sites een fout op yields() terwijl de
    waarde gewoon in de JSON-LD staat. Zonder deze terugval kregen die recepten
    de standaard van 2 porties, wat de kcal-schatting per portie verdubbelt.
    """
    tekst = html.decode("utf-8", "replace") if isinstance(html, bytes) else str(html or "")
    for blok in re.finditer(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', tekst, re.S
    ):
        try:
            data = json.loads(blok.group(1).strip())
        except Exception:
            continue
        kandidaten = data if isinstance(data, list) else (data.get("@graph") or [data])
        for kandidaat in kandidaten:
            if not isinstance(kandidaat, dict):
                continue
            soort = kandidaat.get("@type")
            soort = soort if isinstance(soort, list) else [soort]
            if "Recipe" not in soort:
                continue
            opbrengst = kandidaat.get("recipeYield")
            if isinstance(opbrengst, list):
                opbrengst = opbrengst[0] if opbrengst else None
            if opbrengst is not None and re.search(r"\d", str(opbrengst)):
                return opbrengst
    return None


_EENHEDEN = (
    r"kg|g|gram|grams|l|liter|liters|dl|cl|ml|milliliters?|el|tl|eetlepels?|theelepels?|"
    r"snuf(?:je)?|teen(?:tje)?s?|stuks?|blik(?:je)?|zak(?:je)?|bosje|takje|handvol|"
    r"cups?|tbsp|tbs|tablespoons?|tsp|teaspoons?|oz|ounces?|lbs?|pounds?|"
    r"cloves?|pinch(?:es)?|slices?|pieces?|bunch(?:es)?|cans?|handful"
)


def _ingredient_ontleden(regel):
    """Splitst een ingredientregel in hoeveelheid, eenheid en naam, metrisch.

    Volgorde is belangrijk. Staat er al een metrische waarde tussen haakjes
    ("2 lbs (908g) cream cheese"), dan wint die: exacter dan zelf omrekenen, en
    het haalt de haakjes uit de naam. Anders lezen we de imperiale hoeveelheid en
    rekenen die om.

    Lukt ontleden niet, dan komt de hele regel als naam binnen. Dat is beter dan
    raden: de gebruiker ziet het staan en kan het corrigeren.
    """
    tekst = re.sub(r"\s+", " ", str(regel or "")).strip()
    if not tekst:
        return None

    # 1. Metrische waarde die de site zelf al meegaf.
    uit_haakjes = metriek_uit_haakjes(tekst)
    if uit_haakjes:
        hoeveelheid, eenheid, rest = uit_haakjes
        # De imperiale hoeveelheid vooraan is nu overbodig.
        rest = re.sub(rf"^\s*[\d\s./½¼¾⅓⅔⅛⅜⅝⅞,-]*\s*(?:(?:{_EENHEDEN})\b)?\.?\s*", "", rest, flags=re.I)
        naam = rest.strip(" ,-")
        if naam:
            return {"name": naam, "quantity": hoeveelheid, "unit": eenheid}

    # 2. Zelf ontleden en omrekenen.
    treffer = re.match(
        rf"^([\d.,/½¼¾⅓⅔⅛⅜⅝⅞\s]+?)\s*(?:({_EENHEDEN})\b)?\.?\s+(.*)$",
        tekst,
        re.I,
    )
    if treffer:
        hoeveelheid = parse_getal(treffer.group(1))
        naam = treffer.group(3).strip(" ,-")
        if hoeveelheid is not None and naam:
            hoeveelheid, eenheid = naar_metriek(hoeveelheid, treffer.group(2) or "")
            return {"name": naam, "quantity": hoeveelheid, "unit": eenheid}

    return {"name": tekst, "quantity": 0, "unit": ""}


# Woorden die een gang verraden. Dagelijkse Kost geeft de gang zelf mee in
# recipeCategory; voor sites die dat niet doen leiden we hem af uit naam en
# trefwoorden. Bij twijfel wordt het hoofdgerecht: dat is wat de planner plant.
_DESSERT_WOORDEN = (
    "dessert", "nagerecht", "taart", "cake", "koek", "cookie", "brownie", "muffin",
    # "ijs" staat er bewust niet als los woord in: dat zit ook in "prijs".
    "roomijs", "ijsje", "softijs", "ice cream", "sorbet", "mousse", "pudding",
    "vlaai", "tiramisu", "cheesecake",
    "crumble", "clafoutis", "wafel", "waffle", "pannenkoek", "pancake", "gebak",
    "chocolademousse", "creme brulee", "panna cotta", "milkshake", "smoothie",
    # "compote" en "confituur" staan er bewust niet in: die horen even vaak bij
    # een hartig gerecht ("artisjok met tomatencompote") als bij een nagerecht.
    "candy", "donut", "eclair", "macaron",
)
_VOORGERECHT_WOORDEN = (
    "voorgerecht", "appetizer", "starter", "amuse", "tapas", "hapje", "hapjes",
    "soep", "soup", "bouillon", "gazpacho", "carpaccio", "bruschetta", "croquette",
    "kroket", "borrelhapje",
)


# Gerechten die op zichzelf geen avondmaal zijn. Worden alleen toegepast als de
# hele naam erover gaat, anders zou "Kipfilet met champignonsaus" ook afvallen.
# "dip" staat er bewust niet in: dat zit ook in "French dip-sandwich", een
# volwaardig hoofdgerecht.
_BIJGERECHT_WOORDEN = (
    "saus", "salsa", "pesto", "mayonaise", "dressing", "vinaigrette",
    "marinade", "kruidenboter", "popcorn", "chips", "snack", "borrelhapje",
    "bouillon", "fond", "tapenade", "hummus", "confituur", "chutney",
)


def _bevat_woord(tekst, woorden):
    """Zoekt het woord als einde van een woord, eventueel met meervoud.

    Nederlands plakt samenstellingen aan elkaar: "appeltaart" en "tomatensoep"
    moeten meetellen, dus letters ervoor zijn toegestaan. Maar letters erna niet,
    anders maakt "ijs" van "rijst" een dessert en "vla" van "Vlaamse" een nagerecht.
    """
    return any(
        re.search(rf"{re.escape(w)}(?:s|en|je|jes|ten)?(?![a-z])", tekst) for w in woorden
    )


def _classificeer_gang(naam, categorie=None, trefwoorden=None, beschrijving=""):
    """Bepaalt of iets een voorgerecht, hoofdgerecht of dessert is."""
    # 1. De site zegt het zelf: dat wint altijd.
    expliciet = str(categorie or "").strip().lower()
    for tekst in [expliciet, *[str(t).strip().lower() for t in (trefwoorden or [])]]:
        if not tekst:
            continue
        if "dessert" in tekst or "nagerecht" in tekst:
            return "dessert"
        if "voorgerecht" in tekst or "appetizer" in tekst or "starter" in tekst:
            return "voorgerecht"
        if "hoofdgerecht" in tekst or "main" in tekst:
            return "hoofdgerecht"

    # 2. Sauzen, dips en snacks zijn geen avondmaal. Alleen als de hele naam
    #    erover gaat: "Salsa verde" wel, "Kipfilet met champignonsaus" niet.
    #    Hoogstens twee woorden: "Zigeunersaus" is een saus, "Balletjes in
    #    seldersaus" is een avondmaal.
    korte_naam = re.sub(r"\([^)]*\)", " ", str(naam or "").lower()).strip()
    if len(korte_naam.split()) <= 2 and _bevat_woord(korte_naam, _BIJGERECHT_WOORDEN):
        return "voorgerecht"

    # 2. Anders afleiden uit naam en beschrijving.
    # Alleen de naam: beschrijvingen noemen vaak een bijgerecht of nagerecht
    # dat niets zegt over het gerecht zelf.
    hooiberg = str(naam or "").lower()
    if _bevat_woord(hooiberg, _DESSERT_WOORDEN):
        return "dessert"
    if _bevat_woord(hooiberg, _VOORGERECHT_WOORDEN):
        return "voorgerecht"
    return "hoofdgerecht"


def _stappen_opschonen(stappen):
    """Schoont stappen op en zet temperaturen en inches om naar metrisch."""
    uit = []
    for stap in stappen or []:
        tekst = re.sub(r"\s+", " ", str(stap or "")).strip()
        if tekst:
            uit.append(tekst_naar_metriek(tekst))
    return uit


def _naar_maaltijd(scraper, url, html):
    from recipe_scrapers._exceptions import SchemaOrgException  # lokaal: optionele dependency

    def veilig(functie, standaard=None):
        try:
            return functie()
        except (SchemaOrgException, Exception):
            return standaard

    naam = veilig(scraper.title) or ""
    if not naam:
        raise ImportFout("Geen recepttitel gevonden op deze pagina.")

    ingredienten = []
    for regel in veilig(scraper.ingredients, []) or []:
        ontleed = _ingredient_ontleden(regel)
        if ontleed:
            ingredienten.append(ontleed)

    stappen = _stappen_opschonen(veilig(scraper.instructions_list, []) or [])

    host = urllib.parse.urlsplit(url).netloc.lower().removeprefix("www.")
    aanvulling = _SITE_AANVULLINGEN.get(host, {})
    if "preparation" in aanvulling:
        extra = _stappen_opschonen(aanvulling["preparation"](html))
        # Alleen overnemen als het duidelijk vollediger is dan wat we al hadden.
        if len(extra) > len(stappen):
            stappen = extra

    beschrijving = (veilig(scraper.description, "") or "")[:400]
    gang = _classificeer_gang(
        naam,
        categorie=veilig(scraper.category),
        trefwoorden=veilig(scraper.keywords, []) or [],
        beschrijving=beschrijving,
    )

    return {
        "name": naam,
        "description": beschrijving,
        "image_url": veilig(scraper.image, "") or "",
        "course": gang,
        "servings": _porties_uit(veilig(scraper.yields) or _porties_uit_jsonld(html)),
        "ingredients": ingredienten,
        "preparation": stappen,
        "tags": [],
        "allergens": [],
        "rating": 3,
        "rotation_limit": "1_per_month",
        "protein": 0,
        "carbs": 0,
        "calories": 0,
        "source_url": url,
    }


def importeer_recept(url, html=None):
    """Haalt één receptpagina op en zet die om naar een maaltijd-payload."""
    try:
        from recipe_scrapers import scrape_html
    except ImportError as exc:  # pragma: no cover - alleen zonder dependency
        raise ImportFout(
            "De import-bibliotheek ontbreekt. Installeer recipe-scrapers."
        ) from exc

    if html is None:
        html = _haal_pagina(url)

    try:
        scraper = scrape_html(html, org_url=url)
    except Exception as exc:
        raise ImportFout(f"Deze pagina kon niet als recept gelezen worden: {exc}") from exc

    return _naar_maaltijd(scraper, url, html)


# --- Meerdere recepten van één site ---


# Losse paden in de paginabron, bijvoorbeeld /gerechten/kip-met-appelmoes. Veel
# sites zijn tegenwoordig JavaScript-apps waar de links niet als href in de HTML
# staan maar in een JSON-payload; die vinden we hiermee alsnog.
_KAAL_PAD = re.compile(
    r"/(?:recipes?|recept(?:en)?|gerecht(?:en)?|rezept|plat)/[a-z0-9][a-z0-9\-_]{4,120}",
    re.I,
)


# Slugs die op een receptpad lijken maar het niet zijn.
_GEEN_RECEPT = {
    "zoeken", "search", "index", "alle", "all", "overzicht", "categorie",
    "categorieen", "themas", "nieuw", "populair", "favorieten",
}


def _links_op_pagina(html, basis_url):
    tekst = html.decode("utf-8", "replace") if isinstance(html, bytes) else html
    onderdelen_basis = urllib.parse.urlsplit(basis_url)
    host = onderdelen_basis.netloc.lower()
    gevonden = []
    gezien_slug = set()

    def toevoegen(kandidaat):
        volledig = urllib.parse.urljoin(basis_url, kandidaat)
        onderdelen = urllib.parse.urlsplit(volledig)
        if onderdelen.netloc.lower() != host:
            return
        if not RECEPT_PATRONEN.search(onderdelen.path):
            return
        # Overzichtspaden zoals /recipes zelf zijn geen recept.
        if onderdelen.path.rstrip("/").count("/") < 2:
            return
        slug = onderdelen.path.rstrip("/").rsplit("/", 1)[-1].lower()
        if slug in _GEEN_RECEPT:
            return
        # Sommige sites linken hetzelfde recept via /gerechten/<id> en /recipes/<id>;
        # de slug is dan identiek, dus één keer volstaat.
        if slug in gezien_slug:
            return
        schoon = urllib.parse.urlunsplit((onderdelen.scheme, onderdelen.netloc, onderdelen.path, "", ""))
        if schoon.rstrip("/") == basis_url.rstrip("/"):
            return
        gezien_slug.add(slug)
        gevonden.append(schoon)

    for treffer in re.finditer(r'href=["\']([^"\'#]+)["\']', tekst, re.I):
        toevoegen(treffer.group(1))
    for treffer in _KAAL_PAD.finditer(tekst):
        toevoegen(treffer.group(0))

    return gevonden


def verzamel_recept_urls(start_url, limiet=MAX_PER_IMPORT, robots=None):
    """Zoekt receptlinks op een overzichts- of themapagina.

    Alleen links op de opgegeven pagina zelf; er wordt niet dieper doorgeklikt.
    Zo blijft het voorspelbaar voor de gebruiker en licht voor de site.
    """
    parser = robots if robots is not None else _robots_voor(start_url)
    if not _mag_ophalen(parser, start_url):
        raise ImportFout("De robots.txt van deze site verbiedt het ophalen van deze pagina.")

    html = _haal_pagina(start_url)
    urls = [u for u in _links_op_pagina(html, start_url) if _mag_ophalen(parser, u)]
    return urls[:limiet], html


def importeer_van_url(url, limiet=MAX_PER_IMPORT):
    """Importeert één recept, of alle recepten waar de pagina naar linkt.

    Geeft (maaltijden, fouten) terug. Fouten zijn per URL, zodat één kapotte
    pagina de rest van de batch niet tegenhoudt.
    """
    url = str(url or "").strip()
    if not url.startswith(("http://", "https://")):
        raise ImportFout("Geef een volledige link op, beginnend met https://")

    limiet = max(1, min(MAX_PER_IMPORT, int(limiet or MAX_PER_IMPORT)))
    robots = _robots_voor(url)
    if not _mag_ophalen(robots, url):
        raise ImportFout("De robots.txt van deze site verbiedt het ophalen van deze pagina.")

    html = _haal_pagina(url)

    # Eerst proberen als losse receptpagina.
    try:
        maaltijd = importeer_recept(url, html=html)
        if maaltijd["ingredients"]:
            logger.info("Recept geimporteerd: %s (%s)", maaltijd["name"], url)
            return [maaltijd], []
    except ImportFout:
        pass

    # Anders: de receptlinks op deze pagina aflopen.
    kandidaten = [u for u in _links_op_pagina(html, url) if _mag_ophalen(robots, u)][:limiet]
    if not kandidaten:
        raise ImportFout(
            "Geen recept gevonden op deze pagina, en ook geen links naar recepten. "
            "Probeer een receptpagina of een overzichtspagina met recepten."
        )

    maaltijden, fouten = [], []
    for index, kandidaat in enumerate(kandidaten):
        if index:
            time.sleep(PAUZE_TUSSEN_VERZOEKEN)
        try:
            maaltijd = importeer_recept(kandidaat)
            if maaltijd["ingredients"]:
                maaltijden.append(maaltijd)
            else:
                fouten.append({"url": kandidaat, "reden": "geen ingredienten gevonden"})
        except ImportFout as exc:
            fouten.append({"url": kandidaat, "reden": str(exc)})
        except Exception as exc:
            logger.exception("Onverwachte fout bij importeren van %s", kandidaat)
            fouten.append({"url": kandidaat, "reden": f"onverwachte fout: {exc}"})

    logger.info("Import van %s: %d recepten, %d fouten", url, len(maaltijden), len(fouten))
    return maaltijden, fouten
