"""Hoeveelheden en temperaturen naar het metrische stelsel.

Volledig deterministisch: geen taalmodel nodig, dus altijd beschikbaar en
testbaar. Drie dingen gebeuren hier:

  1. Breuktekens (½, ¼) en "1 1/2" worden echte getallen.
  2. Staat er al een metrische waarde tussen haakjes, zoals bij Joshua Weissman
     ("2 lbs (908g) cream cheese"), dan gebruiken we die. Dat is exacter dan zelf
     omrekenen en het haalt de rommel uit de ingredientnaam.
  3. Blijft er imperiaal over, dan rekenen we om: lb en oz naar gram, cups en
     fluid ounces naar milliliter, inches naar centimeter, Fahrenheit naar Celsius.

Eenheden krijgen meteen hun Nederlandse naam: tablespoon wordt el, teaspoon tl.
"""

import re

# Breuktekens die in receptteksten voorkomen.
BREUKEN = {
    "½": 0.5, "⅓": 1 / 3, "⅔": 2 / 3, "¼": 0.25, "¾": 0.75,
    "⅕": 0.2, "⅖": 0.4, "⅗": 0.6, "⅘": 0.8, "⅙": 1 / 6, "⅚": 5 / 6,
    "⅛": 0.125, "⅜": 0.375, "⅝": 0.625, "⅞": 0.875,
}

# Naar gram, milliliter of centimeter.
NAAR_GRAM = {"lb": 453.592, "lbs": 453.592, "pound": 453.592, "pounds": 453.592,
             "oz": 28.3495, "ounce": 28.3495, "ounces": 28.3495}
NAAR_ML = {"cup": 236.588, "cups": 236.588,
           "fl oz": 29.5735, "fluid ounce": 29.5735, "fluid ounces": 29.5735,
           "pint": 473.176, "pints": 473.176, "quart": 946.353, "quarts": 946.353,
           "gallon": 3785.41, "gallons": 3785.41}
NAAR_CM = {"inch": 2.54, "inches": 2.54, '"': 2.54}

# Engelse eenheden die we alleen hernoemen, niet omrekenen.
HERNOEM = {
    "tbsp": "el", "tbs": "el", "tablespoon": "el", "tablespoons": "el",
    "tsp": "tl", "teaspoon": "tl", "teaspoons": "tl",
    "ml": "ml", "milliliter": "ml", "milliliters": "ml",
    "l": "l", "liter": "l", "liters": "l", "litre": "l",
    "g": "g", "gram": "g", "grams": "g", "kg": "kg", "kilogram": "kg",
    "clove": "teentje", "cloves": "teentje",
    "pinch": "snufje", "pinches": "snufje",
    "slice": "sneetje", "slices": "sneetje",
    "piece": "stuk", "pieces": "stuk",
    "bunch": "bosje", "bunches": "bosje",
    "can": "blik", "cans": "blik",
    "handful": "handvol",
}


def parse_getal(tekst):
    """Leest 2, 1.5, 1,5, ½, 1½ en "1 1/2" als getal."""
    ruw = str(tekst or "").strip()
    if not ruw:
        return None

    totaal = 0.0
    gevonden = False

    # Breuktekens los of achter een geheel getal.
    for teken, waarde in BREUKEN.items():
        if teken in ruw:
            totaal += waarde
            gevonden = True
            ruw = ruw.replace(teken, " ")

    # "1 1/2" of "3/4"
    breuk = re.search(r"(\d+)\s*/\s*(\d+)", ruw)
    if breuk:
        noemer = float(breuk.group(2))
        if noemer:
            totaal += float(breuk.group(1)) / noemer
            gevonden = True
        ruw = ruw[: breuk.start()] + " " + ruw[breuk.end():]

    heel = re.search(r"\d+(?:[.,]\d+)?", ruw)
    if heel:
        totaal += float(heel.group(0).replace(",", "."))
        gevonden = True

    return totaal if gevonden else None


def _afronden(waarde, eenheid):
    """Ronden op iets dat een mens zou opschrijven."""
    if eenheid in ("g", "ml"):
        if waarde >= 100:
            return round(waarde / 5) * 5
        return round(waarde)
    return round(waarde, 2)


def metriek_uit_haakjes(tekst):
    """Haalt een metrische waarde tussen haakjes op, zoals "(908g)" of "(480mL)".

    Veel Engelstalige sites zetten die er zelf bij. Dan is omrekenen niet nodig,
    en verdwijnt de rommel meteen uit de ingredientnaam.
    """
    treffer = re.search(
        r"\(\s*(\d+(?:[.,]\d+)?)\s*(kg|g|gram|grams|ml|mL|milliliters?|l|liters?)\s*\)",
        str(tekst or ""),
    )
    if not treffer:
        return None

    waarde = float(treffer.group(1).replace(",", "."))
    eenheid = treffer.group(2).lower()
    if eenheid in ("gram", "grams"):
        eenheid = "g"
    elif eenheid.startswith("milliliter"):
        eenheid = "ml"
    elif eenheid in ("liter", "liters"):
        eenheid = "l"
    schoon = (tekst[: treffer.start()] + " " + tekst[treffer.end():]).strip()
    return waarde, eenheid, re.sub(r"\s{2,}", " ", schoon)


def naar_metriek(hoeveelheid, eenheid):
    """Rekent een imperiale hoeveelheid om; laat metrische waarden ongemoeid."""
    token = str(eenheid or "").strip().lower().rstrip(".")
    getal = float(hoeveelheid or 0)

    if token in NAAR_GRAM:
        return _afronden(getal * NAAR_GRAM[token], "g"), "g"
    if token in NAAR_ML:
        return _afronden(getal * NAAR_ML[token], "ml"), "ml"
    if token in NAAR_CM:
        return round(getal * NAAR_CM[token], 1), "cm"
    if token in HERNOEM:
        return getal, HERNOEM[token]
    return getal, token


_FAHRENHEIT = re.compile(r"(\d{2,3})\s*°?\s*F\b", re.I)
_GRADEN_MET_CELSIUS = re.compile(
    r"(\d{2,3})\s*°?\s*F\s*\(\s*(\d{2,3})\s*°?\s*C\s*\)", re.I
)
_INCHES = re.compile(r"(\d+(?:[.,]\d+)?|[½¼¾⅓⅔⅛])\s*(?:inch(?:es)?|\")", re.I)


def tekst_naar_metriek(tekst):
    """Zet temperaturen en inches in een bereidingsstap om naar metrisch.

    "Preheat the oven to 450°F (232°C)" wordt "... 232 °C": de Celsius-waarde
    stond er al, dus die nemen we over in plaats van zelf te rekenen.
    """
    uit = str(tekst or "")

    # Eerst de gevallen waar Celsius al tussen haakjes staat.
    uit = _GRADEN_MET_CELSIUS.sub(lambda m: f"{m.group(2)} °C", uit)

    # Daarna losse Fahrenheit-waarden omrekenen.
    def _f_naar_c(match):
        celsius = (float(match.group(1)) - 32) * 5 / 9
        return f"{int(round(celsius / 5) * 5)} °C"

    uit = _FAHRENHEIT.sub(_f_naar_c, uit)

    def _inch_naar_cm(match):
        waarde = parse_getal(match.group(1))
        if waarde is None:
            return match.group(0)
        cm = round(waarde * 2.54, 1)
        mooi = str(cm).replace(".", ",").removesuffix(",0")
        return f"{mooi} cm"

    uit = _INCHES.sub(_inch_naar_cm, uit)
    return re.sub(r"\s{2,}", " ", uit).strip()
