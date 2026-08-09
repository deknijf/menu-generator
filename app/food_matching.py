"""Herkent of een recept iets bevat dat iemand niet lust of niet verdraagt.

Drie dingen maken dit lastiger dan een simpele zoekopdracht:

1. Nederlandse ingredientnamen plakken aan elkaar. "Kastanjechampignons" en
   "paddenstoelenmix" horen allebei bij champignons, maar geen van beide is
   letterlijk gelijk aan wat de gebruiker intypt.
2. Dezelfde zaak heeft meerdere namen: ui en ajuin, witloof en chicon.
3. Wie "paddenstoelen" opgeeft bedoelt ook shiitake. Maar wie "zalm" opgeeft
   bedoelt daarom nog geen kabeljauw. Overkoepelende termen breiden dus uit
   naar hun soorten, soortnamen niet terug naar hun groep.

De EU-allergenen komen uit tagging.py, zodat "noten" hier hetzelfde betekent
als bij het labelen van een recept.
"""

import re

from .tagging import _ALLERGEEN_REGELS, vernederlands

# Zelfde zaak, andere naam. Wederzijds uitwisselbaar.
SYNONIEMEN = [
    # De Engelse schrijfwijzen staan erbij omdat ze in profielen voorkomen: wie
    # ooit "soya" of "peanut" intypte, hoort dezelfde bescherming te krijgen als
    # wie "soja" of "pinda" schreef.
    {"soja", "soya"},
    {"pinda", "peanut", "aardnoot", "arachide"},
    {"noten", "nuts"},
    {"vis", "fish"},
    {"schaaldieren", "shellfish"},
    {"selderij", "selder", "celery"},
    {"mosterd", "mustard"},
    {"sesam", "sesame"},
    # Citrus is de uitzondering op de regel hieronder dat een soortnaam bij
    # zichzelf blijft: wie citroen niet verdraagt, verdraagt limoen doorgaans
    # evenmin. Daarom werkt deze groep wel in beide richtingen.
    {"citrus", "citroen", "citroensap", "citroenzeste", "lemon",
     "limoen", "limoensap", "limoenzeste", "lime"},
    {"paddenstoel", "paddestoel"},
    {"ui", "ajuin"},
    {"witloof", "witlof", "chicon"},
    {"look", "knoflook"},
    {"courgette", "zucchini"},
    {"aubergine", "eierplant"},
    {"mais", "maiskorrel"},
    {"kikkererwt", "chickpea"},
    {"koriander", "cilantro"},
    {"pompelmoes", "grapefruit"},
    {"pladijs", "schol"},
    {"prei", "preistengel"},
    {"rode biet", "rode kroot"},
    {"spruit", "spruitje"},
]

# Overkoepelende termen en wat eronder valt. Eenrichtingsverkeer: de groepsnaam
# vindt de soorten, de soortnaam blijft bij zichzelf.
SOORTEN = {
    "paddenstoel": {
        "champignon", "kastanjechampignon", "boschampignon", "shiitake",
        "oesterzwam", "portobello", "cantharel", "eekhoorntjesbrood",
        "morille", "truffel",
    },
    "orgaanvlees": {"lever", "nier", "zwezerik", "niertjes", "hart"},
    "wild": {"hert", "ree", "everzwijn", "fazant", "haas", "konijn", "duif"},
    "peulvrucht": {
        "linze", "kikkererwt", "witte boon", "bruine boon", "kidneyboon",
        "sojaboon", "spliterwt", "kapucijner",
    },
    "zeevruchten": {
        "garnaal", "scampi", "gamba", "krab", "kreeft", "langoustine",
        "mossel", "oester", "inktvis", "calamari", "coquille",
    },
    "gevogelte": {"kip", "kalkoen", "eend", "parelhoen", "kwartel"},
    "pittig": {"chili", "sambal", "peperoncino", "harissa", "cayenne", "jalapeno"},
}

_ALLERGEEN_PATRONEN = dict(_ALLERGEEN_REGELS)


def normaliseer(term):
    """Kleine letters, geen dubbele spaties, meervoud eraf waar dat veilig kan."""
    token = re.sub(r"\s+", " ", str(term or "").strip().lower())
    # "soya" en "chicken" komen nog uit oudere profielen.
    return vernederlands(token)


def _synoniemen_van(token):
    for groep in SYNONIEMEN:
        if token in groep:
            return set(groep)
    return {token}


def expandeer(term):
    """Alle namen waaronder deze term in een receptenlijst kan opduiken."""
    token = normaliseer(term)
    if not token:
        return set()

    tokens = _synoniemen_van(token)
    # Ook het enkelvoud meenemen: gebruikers typen "paddenstoelen".
    for enkelvoud in {re.sub(r"(en|s)$", "", t) for t in list(tokens)}:
        if len(enkelvoud) >= 4:
            tokens |= _synoniemen_van(enkelvoud)

    for naam in list(tokens):
        for groep, leden in SOORTEN.items():
            if naam == groep or naam in _synoniemen_van(groep):
                tokens |= leden
    return {t for t in tokens if t}


def _past_in_tekst(token, tekst):
    """True als het woord in de tekst voorkomt, ook als deel van een samenstelling.

    Samenstellingen plakken langs twee kanten: "kastanjechampignons" heeft het
    woord achteraan, "kipfilet" vooraan. Allebei tellen mee, maar hoe korter het
    woord hoe strenger, anders vindt "ui" ook "uitsmijter" en "bruine bonen".
    Twee letters moeten dus exact op een woord vallen, en pas vanaf vier letters
    mag er ook nog iets voor staan.
    """
    voorkant = "" if len(token) >= 4 else r"\b"
    achterkant = r"[a-z]*" if len(token) >= 3 else r"(?:s|en|es|je|jes|tje|tjes)?"
    return re.search(rf"{voorkant}{re.escape(token)}{achterkant}(?![a-z])", tekst) is not None


def maak_hooiberg(recept):
    """De doorzoekbare tekst van een recept: naam, tags en ingredienten.

    Wie meerdere termen tegen hetzelfde recept houdt, bouwt dit beter een keer
    en geeft het mee aan `bevat`. Bij het plannen scheelt dat een factor drie.
    """
    delen = [normaliseer(recept.get("name", ""))]
    delen.extend(normaliseer(tag) for tag in recept.get("tags") or [])
    for ingredient in recept.get("ingredients") or []:
        delen.append(normaliseer(ingredient.get("name", "")))
    return " ".join(deel for deel in delen if deel)


def bevat(recept, term, tekst=None):
    """True als het recept deze term bevat, in welke gedaante ook."""
    token = normaliseer(term)
    if not token:
        return False

    # Een EU-allergeen staat al als label op het recept; dat is het betrouwbaarst.
    labels = {normaliseer(a) for a in recept.get("allergens") or []}
    if token in labels:
        return True

    tekst = maak_hooiberg(recept) if tekst is None else tekst
    if not tekst:
        return False

    # Voor de veertien allergenen gebruiken we dezelfde regels als bij het
    # labelen, zodat "noten" hier net zo breed telt als daar. Ook de synoniemen
    # krijgen die behandeling: anders zoekt "soya" letterlijk naar "soya" en
    # glipt sojasaus erdoor.
    varianten = expandeer(token)
    for naam in varianten:
        patroon = _ALLERGEEN_PATRONEN.get(naam)
        if patroon and re.search(patroon, tekst, re.I):
            return True

    return any(_past_in_tekst(t, tekst) for t in varianten)


def welke_komen_voor(recept, termen):
    """De termen uit de lijst die dit recept daadwerkelijk bevat."""
    return [term for term in termen or [] if bevat(recept, term)]
