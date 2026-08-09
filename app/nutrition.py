"""Calorieën per recept schatten uit de ingredienten.

Werkwijze: een tabel met de energiewaarde per 100 g van veelgebruikte
ingredienten, plus omrekentabellen voor eenheden die geen gewicht zijn (een
eetlepel, een teentje look, een stuk ui). Daarmee is de energie van een recept de
som van zijn ingredienten, gedeeld door het aantal porties.

Het blijft een schatting. Een "middelgrote ui" weegt niet altijd 110 g, en
bereidingsverlies rekenen we niet mee. Voor het doel — zien of een gerecht rond
de 400 of rond de 900 kcal per portie zit — is dat ruim voldoende.

Ingredienten die we niet herkennen tellen als 0 en worden apart geteld, zodat
zichtbaar blijft hoe compleet de schatting is.
"""

import re

from .logging_setup import get_logger

logger = get_logger(__name__)

# Gewicht in gram van eenheden die geen gewicht zijn. Grove gemiddelden.
EENHEID_IN_GRAM = {
    "g": 1.0,
    "gr": 1.0,          # komt veel voor op receptsites
    "grs": 1.0,
    "gram": 1.0,
    "grammen": 1.0,
    "kg": 1000.0,
    "kilo": 1000.0,
    "ml": 1.0,          # water als benadering; voor olie iets te hoog, acceptabel
    "l": 1000.0,
    "dl": 100.0,
    "cl": 10.0,
    "el": 15.0,
    "eetlepel": 15.0,
    "tl": 5.0,
    "theelepel": 5.0,
    "teentje": 3.0,
    "snufje": 0.5,
    "scheut": 10.0,
    "handvol": 30.0,
    "bosje": 25.0,
    "takje": 2.0,
    "blik": 400.0,
    "zak": 300.0,
    "sneetje": 35.0,
    "stronk": 300.0,
}

# Als een ingredient per "stuk" geteld wordt, hoeveel gram is dat dan.
# Staat het er niet bij, dan gebruiken we STUK_STANDAARD.
STUK_STANDAARD = 100.0
# Boven dit aantal is een hoeveelheid zonder bruikbare eenheid vrijwel zeker een
# gewicht in gram, geen aantal stuks.
PORTIE_GRENS = 12
# Bovengrens per ingredient, zodat een verkeerd gelezen regel de hele schatting
# niet onbruikbaar maakt.
MAX_GRAM_PER_INGREDIENT = 5000.0
# Frituurolie blijft grotendeels in de pan; ongeveer dit deel wordt opgenomen.
OLIE_OPNAME = 0.12
_IS_FRITUUROLIE = re.compile(r"frituur|frituren|frying|fryer|deep[- ]?fry", re.I)
GRAM_PER_STUK = {
    "ui": 110, "rode ui": 110, "witte ui": 110, "sjalot": 30, "look": 30,
    "wortel": 80, "wortelen": 80, "prei": 150, "selder": 60, "courgette": 250,
    "aubergine": 300, "paprika": 150, "tomaat": 120, "tomaten": 120,
    "komkommer": 350, "aardappel": 150, "aardappelen": 150, "zoete aardappel": 200,
    "bloemkool": 800, "broccoli": 400, "witloof": 100, "venkel": 250,
    "appel": 180, "peer": 170, "banaan": 120, "sinaasappel": 200, "citroen": 100,
    "limoen": 70, "avocado": 170, "ei": 55, "eieren": 55, "eidooier": 18,
    "kipfilet": 150, "kippenbout": 200, "varkenskotelet": 150, "steak": 200,
    "stokbrood": 250, "brood": 800, "wrap": 60, "tortilla": 30,
    "champignon": 20, "champignons": 20, "peper": 15, "chilipeper": 10,
    "lente-ui": 15, "vanillestokje": 3, "laurierblad": 0.2, "kotelet": 150,
    "briochebroodje": 70, "broodje": 70, "hamburgerbroodje": 70,
    # Sneden tellen als snede, niet als heel brood: "4 sneden witbrood" is geen
    # 3,2 kilo brood.
    "snede": 35, "sneden": 35, "sneetje": 35, "sneetjes": 35, "toast": 35,
    "braadkip": 1200, "braadkippen": 1200, "hele kip": 1200, "kippenbouten": 200,
    "kipfilets": 150, "varkenskoteletten": 150, "stokbroden": 250,
    "tortillas": 30, "maistortilla": 30, "vel bladerdeeg": 60, "vel": 60,
    "blaadje": 0.2, "blaadjes": 0.2, "takjes": 2, "steranijs": 1,
}

# Energie per 100 g. Genoeg om de meeste recepten te dekken; wat ontbreekt
# telt als 0 en wordt gerapporteerd.
KCAL_PER_100G = {
    # --- vlees en gevogelte ---
    "kipfilet": 165, "kip": 190, "kippenbout": 215, "kippendijfilet": 210,
    "kalkoen": 150, "kalkoenfilet": 135, "rundvlees": 250, "rundergehakt": 250,
    "gehakt": 260, "biefstuk": 200, "steak": 220, "runderborst": 290,
    "runderschenkel": 200, "rosbief": 190, "ribrollade": 290, "brisket": 290,
    "varkensvlees": 240, "varkenskotelet": 230, "varkenshaas": 145, "spek": 540,
    "ham": 145, "salami": 400, "worst": 300, "chorizo": 455, "merguez": 320,
    "lamsvlees": 260, "kalfsvlees": 170, "eend": 340, "konijn": 175,
    # --- vis en zeevruchten ---
    "zalm": 210, "kabeljauw": 82, "tonijn": 130, "witte vis": 90, "pangasius": 90,
    "koolvis": 85, "schol": 90, "forel": 150, "makreel": 260, "haring": 210,
    "garnalen": 100, "scampi": 100, "mosselen": 85, "inktvis": 90, "ansjovis": 210,
    # --- zuivel en eieren ---
    "melk": 64, "volle melk": 64, "halfvolle melk": 47, "room": 340,
    "volle room": 340, "slagroom": 340, "kookroom": 195, "zure room": 195,
    "creme fraiche": 300, "yoghurt": 60, "griekse yoghurt": 115, "boter": 745,
    "ongezouten boter": 745, "geklaarde boter": 890, "ghee": 890, "margarine": 720,
    "kaas": 380, "geraspte kaas": 400, "parmezaan": 400, "parmigiano reggiano": 400,
    "pecorino": 390, "pecorino romano": 390, "mozzarella": 280, "feta": 265,
    "roomkaas": 340, "mascarpone": 430, "gruyere": 410, "cheddar": 400,
    "provolone": 350, "oaxaca-kaas": 330, "halloumi": 320, "ricotta": 170,
    "ei": 145, "eieren": 145, "eidooier": 320, "eiwit": 52,
    # --- granen, pasta, rijst, brood ---
    "pasta": 355, "spaghetti": 355, "rigatoni": 355, "penne": 355,
    "tagliatelle": 355, "lasagnebladen": 355, "noedels": 350, "orzo": 355,
    "rijst": 350, "witte rijst": 350, "risottorijst": 350, "basmatirijst": 350,
    "bloem": 345, "maizena": 380, "aardappelzetmeel": 340, "panko": 380,
    "paneermeel": 380, "brood": 265, "stokbrood": 270, "melkbrood": 300,
    "wit brood": 265, "tortilla": 310, "maistortilla": 220, "wrap": 300,
    "couscous": 350, "quinoa": 370, "bulgur": 340, "havermout": 375,
    "briochebroodje": 330, "broodje": 280, "popcornmais": 380,
    # --- groenten ---
    "aardappel": 77, "aardappelen": 77, "frietaardappelen": 77, "krieltjes": 77,
    "zoete aardappel": 86, "ui": 40, "rode ui": 40, "sjalot": 72, "look": 149,
    "prei": 61, "wortel": 41, "wortelen": 41, "selder": 16, "bleekselder": 16,
    "knolselder": 42, "pastinaak": 75, "raap": 28, "koolraap": 37,
    "tomaat": 18, "tomaten": 18, "cherrytomaten": 18, "tomatenblokjes": 20,
    "tomatenpuree": 82, "passata": 30, "paprika": 31, "chilipeper": 40,
    "courgette": 17, "aubergine": 25, "komkommer": 15, "broccoli": 34,
    "bloemkool": 25, "bloemkoolrijst": 25, "spruitjes": 43, "witte kool": 25,
    "groene kool": 25, "rode kool": 31, "spitskool": 25, "boerenkool": 49,
    "spinazie": 23, "sla": 15, "veldsla": 21, "rucola": 25, "witloof": 17,
    "venkel": 31, "asperges": 20, "erwten": 81, "doperwten": 81,
    "sperziebonen": 31, "prinsessenbonen": 31, "maïs": 86, "mais": 86,
    "champignon": 22, "champignons": 22, "paddenstoelen": 22, "artisjok": 47,
    "pompoen": 26, "tomatillo": 32, "lente-ui": 32, "bieslook": 30,
    "peterselie": 36, "koriander": 23, "basilicum": 23, "tijm": 100,
    "rozemarijn": 130, "munt": 45, "dille": 43, "oregano": 265, "laurierblad": 310,
    # --- peulvruchten en noten ---
    "linzen": 350, "kikkererwten": 360, "witte bonen": 330, "kidneybonen": 330,
    "bonen": 330, "tofu": 76, "amandelen": 580, "walnoten": 650, "hazelnoten": 630,
    "cashewnoten": 550, "pinda": 570, "sesamzaad": 570, "zonnebloempitten": 580,
    # --- vetten, sauzen, kruiden ---
    "olijfolie": 884, "extra vierge olijfolie": 884, "zonnebloemolie": 884,
    "neutrale olie": 884, "arachideolie": 884, "sesamolie": 884, "frituurolie": 884,
    "mayonaise": 680, "kewpie-mayonaise": 700, "ketchup": 110, "mosterd": 100,
    "dijonmosterd": 100, "sojasaus": 60, "vissaus": 35, "oestersaus": 130,
    "worcestershiresaus": 80, "azijn": 20, "appelciderazijn": 22, "rijstazijn": 20,
    "balsamico": 90, "gochujang": 220, "sambal": 90, "hotsaus": 30,
    "bouillon": 5, "kippenbouillon": 5, "groentebouillon": 5, "runderbouillon": 5,
    "bouillonpoeder": 220, "kippenbouillonpoeder": 220, "runderbouillonpoeder": 220,
    "zout": 0, "grof zout": 0, "zeezout": 0, "peper": 250, "zwarte peper": 250,
    "witte peper": 300, "paprikapoeder": 280, "gerookt paprikapoeder": 280,
    "cayennepeper": 320, "komijn": 375, "kurkuma": 310, "kaneel": 250,
    "kruidnagel": 275, "nootmuskaat": 525, "lookpoeder": 330, "uienpoeder": 340,
    "mosterdpoeder": 500, "ve-tsin": 0, "msg": 0, "baksoda": 0, "bakpoeder": 100,
    "gist": 105, "vanille-extract": 290, "vanillepasta": 290, "vanillestokje": 290,
    # --- zoet ---
    "suiker": 400, "kristalsuiker": 400, "bloemsuiker": 400, "basterdsuiker": 380,
    "bruine suiker": 380, "honing": 304, "ahornsiroop": 260, "chocolade": 545,
    "pure chocolade": 545, "melkchocolade": 535, "cacao": 230, "cacaopoeder": 230,
    "jam": 250, "confituur": 250, "appelmoes": 45,
    # --- aanvullingen op basis van de eigen bibliotheek ---
    "gember": 80, "kappertjes": 23, "laurier": 310, "laurierblaadjes": 310,
    "amandelschilfers": 580, "amandelpoeder": 580, "amandelextract": 260,
    "pijnboompitten": 675, "vanillestok": 290, "vanillepoeder": 290,
    "maïzena": 380, "steranijs": 337, "steranijsje": 337, "saffraan": 310,
    "currypoeder": 325, "kervel": 40, "dragon": 295, "peterselieblad": 36,
    "bladerdeeg": 380, "filodeeg": 300, "wontonvellen": 320, "norivellen": 350,
    "gelatine": 335, "dooier": 320, "dooiers": 320, "peren": 57,
    "augurken": 15, "zure augurken": 15, "spirelli": 355, "gamba": 100,
    "gamba s": 100, "pladijs": 90, "pladijsfilets": 90, "zeetong": 85,
    "entrecote": 240, "platte bil": 130, "tagliata": 220, "prij": 61,
    "sriracha": 100, "sweet chilisaus": 230, "chiliolie": 884,
    "sojascheuten": 30, "chinese kool": 16, "zeekraal": 25,
    "emmental": 380, "roquefort": 370, "mortadella": 310, "notenmix": 600,
    "grand marnier": 320, "whisky": 250, "calvados": 250, "cider": 45,
    "focaccia": 280, "foccacia": 280, "ratte": 77, "ratte de touquet": 77,
    "chiles de arbol": 320, "chipotle": 40, "adobo": 90, "bakspray": 884,
    "flandrien": 380, "mozarella": 280,
    # --- fruit ---
    "appel": 52, "peer": 57, "banaan": 89, "sinaasappel": 47, "citroen": 29,
    "citroensap": 22, "limoen": 30, "limoensap": 25, "aardbeien": 32,
    "frambozen": 52, "bosbessen": 57, "druiven": 69, "mango": 60, "kiwi": 61,
    "ananas": 50, "perzik": 39, "abrikoos": 48, "rozijnen": 300, "dadels": 280,
    "avocado": 160, "olijven": 145,
    # --- dranken in recepten ---
    "wijn": 82, "rode wijn": 85, "witte wijn": 82, "bier": 43, "wodka": 231,
    "shaoxing-wijn": 130, "water": 0, "karnemelk": 40, "shirodashi": 50,
}

# Woorden die niets over het ingredient zeggen en het matchen in de weg zitten.
_RUIS = re.compile(
    r"\b(vers(e)?|fijn(gesneden|gehakt)?|grof(gesneden)?|geraspt(e)?|gesneden|gehakt|"
    r"gepeld(e)?|geschild(e)?|gewassen|gekookt(e)?|rauw(e)?|gedroogd(e)?|"
    r"in blokjes|in reepjes|in plakjes|naar smaak|optioneel|om te|voor de|voor het|"
    r"op kamertemperatuur|ongezouten|gezouten|extra|groot|grote|klein(e)?|middelgrote)\b",
    re.I,
)


def seed_database():
    """Zet de ingebouwde tabel in de database, zonder eigen correcties te overschrijven."""
    from .db import upsert_ingredient_energy

    items = {naam: (kcal, GRAM_PER_STUK.get(naam)) for naam, kcal in KCAL_PER_100G.items()}
    toegevoegd = upsert_ingredient_energy(items, source="seed")
    logger.info("Energietabel: %d nieuwe ingredienten toegevoegd.", toegevoegd)
    return toegevoegd


def tabel_uit_database():
    """Leest de energietabel uit de database; valt terug op de ingebouwde tabel."""
    from .db import list_ingredient_energy

    try:
        rijen = list_ingredient_energy()
    except Exception:
        logger.exception("Energietabel niet leesbaar; ingebouwde waarden gebruikt.")
        return dict(KCAL_PER_100G), dict(GRAM_PER_STUK)

    if not rijen:
        return dict(KCAL_PER_100G), dict(GRAM_PER_STUK)

    kcal = {naam: waarde[0] for naam, waarde in rijen.items()}
    # Stukgewichten zijn omrekening, geen voedingsdata: die blijven in code staan.
    # Wat in de database is ingevuld gaat er wel overheen.
    gram = dict(GRAM_PER_STUK)
    gram.update({naam: waarde[1] for naam, waarde in rijen.items() if waarde[1]})
    return kcal, gram


def normaliseer(naam):
    """Maakt van een ingredientregel een naam die we kunnen opzoeken."""
    tekst = str(naam or "").lower()
    tekst = re.sub(r"\([^)]*\)", " ", tekst)      # haakjes weg
    tekst = tekst.split(",")[0]                    # alles na de eerste komma weg
    tekst = _RUIS.sub(" ", tekst)
    tekst = re.sub(r"[^a-zà-ÿ\s-]", " ", tekst)
    return re.sub(r"\s+", " ", tekst).strip()


def _past_als_woord(sleutel, tekst):
    """True als de sleutel als (deel van een) woord eindigt in de tekst.

    Nederlands plakt samenstellingen aan elkaar, dus "frietaardappelen" mag op
    "aardappel" matchen. Maar letters erna zijn niet toegestaan, anders vindt de
    sleutel "ui" ook "ruimtevaartsoep".
    """
    return re.search(rf"{re.escape(sleutel)}(?:s|en|es|je|jes|tje|tjes)?(?![a-z])", tekst) is not None


def kcal_per_100g(naam, tabel=None):
    """Zoekt de energiewaarde op; None als we het ingredient niet kennen."""
    tabel = KCAL_PER_100G if tabel is None else tabel
    schoon = normaliseer(naam)
    if not schoon:
        return None

    if schoon in tabel:
        return tabel[schoon]

    # Samenstellingen: "frietaardappelen" bevat "aardappel", "kipfilets" bevat
    # "kipfilet". Langste treffer wint, zodat "zoete aardappel" niet op
    # "aardappel" uitkomt.
    beste = None
    for sleutel, waarde in tabel.items():
        if _past_als_woord(sleutel, schoon) and (beste is None or len(sleutel) > len(beste[0])):
            beste = (sleutel, waarde)
    if beste:
        return beste[1]

    # Laatste poging op het hoofdwoord.
    woorden = schoon.split()
    for woord in reversed(woorden):
        if woord in tabel:
            return tabel[woord]
    return None


def gram_van(ingredient, gram_tabel=None):
    """Zet hoeveelheid + eenheid om naar gram."""
    hoeveelheid = float((ingredient or {}).get("quantity") or 0)
    if hoeveelheid <= 0:
        return 0.0
    eenheid = str((ingredient or {}).get("unit") or "").strip().lower()

    if eenheid in EENHEID_IN_GRAM:
        return min(hoeveelheid * EENHEID_IN_GRAM[eenheid], MAX_GRAM_PER_INGREDIENT)

    # Onbekende of ontbrekende eenheid. Een getal boven de PORTIE_GRENS is vrijwel
    # zeker een gewicht in gram ("500 gr gehakt" met een eenheid die we niet
    # kennen), want niemand gebruikt 500 stuks van iets. Zonder deze regel werd
    # 500 gehakt 500 x 100 g = 50 kilo.
    if hoeveelheid > PORTIE_GRENS:
        return min(hoeveelheid, MAX_GRAM_PER_INGREDIENT)

    # Langste treffer wint, net als bij het opzoeken van de energiewaarde.
    # Anders matcht "briochebroodjes" op "brood" (een heel brood van 800 g)
    # in plaats van op "briochebroodje" (70 g).
    schoon = normaliseer((ingredient or {}).get("name"))
    tabel = gram_tabel if gram_tabel is not None else GRAM_PER_STUK
    beste = None
    for sleutel, gram in tabel.items():
        if not gram:
            continue
        if sleutel == schoon:
            beste = (sleutel, gram)
            break
        if _past_als_woord(sleutel, schoon) and (beste is None or len(sleutel) > len(beste[0])):
            beste = (sleutel, gram)
    per_stuk = beste[1] if beste else STUK_STANDAARD
    return min(hoeveelheid * per_stuk, MAX_GRAM_PER_INGREDIENT)


def bereken_kcal(recept, tabel=None, gram_tabel=None):
    """Energie per portie voor één recept.

    Geeft (kcal_per_portie, dekking) terug, waarbij dekking het aandeel
    ingredienten is dat we konden opzoeken. Bij een lage dekking is de schatting
    weinig waard en kan de caller besluiten hem niet te gebruiken.
    """
    ingredienten = (recept or {}).get("ingredients") or []
    porties = int((recept or {}).get("servings") or 2)
    porties = max(1, porties)

    totaal = 0.0
    herkend = 0
    meetbaar = 0

    for item in ingredienten:
        naam = (item or {}).get("name") or ""
        if not naam.strip():
            continue
        meetbaar += 1
        per100 = kcal_per_100g(naam, tabel)
        if per100 is None:
            continue
        herkend += 1
        bijdrage = gram_van(item, gram_tabel) * per100 / 100.0
        # Frituurolie gaat grotendeels de vuilbak in; alleen wat het gerecht
        # opneemt telt mee. Zonder deze correctie is gefrituurd eten goed voor
        # duizenden kcal per portie.
        if _IS_FRITUUROLIE.search(naam):
            bijdrage *= OLIE_OPNAME
        totaal += bijdrage

    dekking = (herkend / meetbaar) if meetbaar else 0.0
    return round(totaal / porties), round(dekking, 3)
