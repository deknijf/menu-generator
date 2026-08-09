"""Tags en allergenen afleiden uit een recept.

Tags dienen twee doelen tegelijk. Voor jou zijn ze een filter en een geheugensteun
("waar zit ook alweer kip in"), voor de planner zijn ze scoringsmateriaal:
`meal_engine` kijkt naar `vis`, `pasta` en `zwaar` om variatie te bewaken en
voorkeuren te wegen.

Daarom leveren we per gerecht zowel een grove categorie (vlees, vis, aardappel)
als de concrete hoofdingredienten (kip, tomaat, wortel). Minimaal
`MIN_TAGS`, maximaal `MAX_TAGS`, in volgorde van belangrijkheid zodat het
afkappen de nuttigste tags overhoudt.

Allergenen volgen de veertien die in de EU verplicht vermeld moeten worden, plus
citrus omdat dat in dit huishouden speelt. Ze worden afgeleid uit de
ingredientnamen; bij twijfel liever een allergeen te veel dan te weinig, want de
planner gebruikt ze als harde uitsluiting.
"""

import re

MIN_TAGS = 6
MAX_TAGS = 10

# Volgorde bepaalt de prioriteit bij afkappen: eerst wat een gerecht typeert,
# daarna de bijrollen. Elke regel is (tag, patronen).
_INGREDIENT_TAGS = [
    # --- eiwitbron, concreet ---
    ("kip", r"\bkip|kipfilet|kippenbout|hoevekip|braadkip|chicken"),
    ("kalkoen", r"kalkoen|turkey"),
    ("rund", r"rund|biefstuk|entrecote|steak|brisket|rosbief|beef"),
    ("varken", r"varken|spek|ham\b|kotelet|pork|mortadella"),
    ("lam", r"\blam(s|svlees|schenkel)?\b"),
    ("gehakt", r"gehakt|balletjes|mince"),
    ("worst", r"worst|chorizo|merguez|salami"),
    ("zalm", r"zalm|salmon"),
    ("kabeljauw", r"kabeljauw|cod\b"),
    ("tonijn", r"tonijn|tuna"),
    ("garnalen", r"garnaal|garnalen|scampi|gamba|shrimp|prawn"),
    ("mosselen", r"mossel|oester|weekdier"),
    ("ei", r"\bei\b|eieren|eidooier|omelet|frittata"),
    ("tofu", r"tofu|tempeh|seitan"),
    # --- koolhydraatbron ---
    ("aardappel", r"aardappel|krieltje|puree|friet|stoemp|ratte"),
    ("rijst", r"\brijst\b|risotto|basmati|paella"),
    ("pasta", r"pasta|spaghetti|penne|rigatoni|tagliatelle|lasagne|spirelli|orzo|noedel|macaroni"),
    ("brood", r"brood|stokbrood|baguette|toast|sandwich|wrap|tortilla|pita|focaccia"),
    ("couscous", r"couscous|bulgur|quinoa"),
    ("peulvruchten", r"linzen|kikkererwt|bonen|erwten|split"),
    # --- groenten ---
    ("tomaat", r"tomaat|tomaten|passata|tomatillo"),
    ("wortel", r"wortel|peen\b"),
    ("ui", r"\bui\b|uien|sjalot|lente-ui"),
    ("look", r"\blook\b|knoflook|garlic"),
    # Alleen de groente. "peper" hoort hier niet bij: dat is zwarte peper, en die
    # zit in bijna elk recept — daardoor kreeg de helft van de bibliotheek
    # onterecht de tag paprika. "paprikapoeder" valt af door de woordgrens.
    ("paprika", r"paprika\b"),
    ("champignon", r"champignon|paddenstoel|shiitake|oesterzwam"),
    ("courgette", r"courgette|zucchini"),
    ("aubergine", r"aubergine"),
    ("broccoli", r"broccoli"),
    ("bloemkool", r"bloemkool"),
    ("spinazie", r"spinazie"),
    ("prei", r"\bprei\b"),
    ("kool", r"\bkool\b|spitskool|boerenkool|witte kool|rode kool|spruit"),
    ("selder", r"selder|selderij"),
    ("witloof", r"witloof|chicon"),
    ("venkel", r"venkel"),
    ("pompoen", r"pompoen"),
    ("sla", r"\bsla\b|rucola|veldsla|kropsla"),
    ("erwten", r"erwten|doperwten"),
    # --- zuivel en vet ---
    ("kaas", r"kaas|feta|mozzarella|parmezaan|pecorino|gruyere|cheddar|provolone|roquefort"),
    ("room", r"\broom\b|slagroom|kookroom|creme fraiche|mascarpone"),
    ("boter", r"\bboter\b"),
]

# Grove categorie die uit de concrete tags volgt.
_CATEGORIE_UIT_TAG = {
    "kip": "gevogelte", "kalkoen": "gevogelte",
    "rund": "vlees", "varken": "vlees", "lam": "vlees", "gehakt": "vlees", "worst": "vlees",
    "zalm": "vis", "kabeljauw": "vis", "tonijn": "vis",
    "garnalen": "schaaldieren", "mosselen": "schaaldieren",
}

# Bereidingswijze uit de stappen.
_STIJL_TAGS = [
    ("oven", r"\boven\b|ovenschaal|bak(?:ken)? in de oven|gratineer"),
    ("gefrituurd", r"frituur|frituren|frituurpan"),
    ("soep", r"\bsoep\b|bouillon.*(?:pureer|mix)|gazpacho"),
    ("salade", r"salade|sla aanmaken"),
    ("stoofpot", r"stoof|sudder|braiseer|laat.*uur.*garen"),
    ("wok", r"\bwok\b|roerbak"),
    ("gegrild", r"\bgril|barbecue|grillpan|plancha"),
]

_ALLERGEEN_REGELS = [
    ("gluten", r"bloem|tarwe|brood|pasta|spaghetti|penne|rigatoni|tagliatelle|lasagne|"
               r"couscous|bulgur|paneermeel|panko|bladerdeeg|filodeeg|wontonvel|noedel|"
               r"stokbrood|toast|wrap|tortilla|beschuit|griesmeel|spirelli|orzo|"
               r"sojasaus|bier\b|macaroni|cracker|koek|cake|taart"),
    ("lactose", r"melk|room\b|slagroom|kookroom|boter\b|kaas|yoghurt|mascarpone|"
                r"creme fraiche|mozzarella|feta|parmezaan|pecorino|gruyere|cheddar|"
                r"provolone|roquefort|ricotta|halloumi|karnemelk|ghee"),
    ("ei", r"\bei\b|eieren|eidooier|eiwit\b|mayonaise|sabayon|omelet|frittata|meringue"),
    ("vis", r"\bvis\b|zalm|kabeljauw|tonijn|forel|makreel|haring|ansjovis|pladijs|"
            r"zeetong|heek|koolvis|schol|pangasius|vissaus|worcestershire"),
    ("schaaldieren", r"garnaal|garnalen|scampi|gamba|krab|kreeft|langoustine"),
    ("weekdieren", r"mossel|oester|inktvis|calamari|sint-jakobs|coquille|slak"),
    ("noten", r"amandel|walnoot|hazelnoot|cashew|pistache|pecan|macadamia|notenmix|"
              r"praline|marsepein"),
    ("pinda", r"pinda|peanut|arachide"),
    ("soja", r"soja|soya|tofu|tempeh|edamame|miso"),
    ("selderij", r"selder|selderij|knolselder"),
    ("mosterd", r"mosterd|dijon"),
    ("sesam", r"sesam|tahin|tahini|hummus"),
    ("sulfiet", r"\bwijn\b|azijn|gedroogde abrikoos|gedroogde vijg"),
    ("lupine", r"lupine"),
    # Geen officieel allergeen, maar wel een intolerantie die hier speelt.
    ("citrus", r"citroen|limoen|sinaasappel|mandarijn|pomelo|grapefruit|zeste|lemon|lime|orange"),
]


def _hooiberg(recept):
    """Alle tekst waar we tags uit kunnen afleiden, als één doorzoekbare string."""
    delen = [str((recept or {}).get("name") or ""), str((recept or {}).get("description") or "")]
    for ingredient in (recept or {}).get("ingredients") or []:
        delen.append(str((ingredient or {}).get("name") or ""))
    return re.sub(r"\s+", " ", " ".join(delen)).lower()


def _stappen_tekst(recept):
    return " ".join(str(stap) for stap in ((recept or {}).get("preparation") or [])).lower()


def bepaal_tags(recept, bestaande=None):
    """Leidt tussen MIN_TAGS en MAX_TAGS tags af uit het recept.

    Bestaande tags blijven vooraan staan: wat jij zelf invulde weegt zwaarder dan
    wat wij raden.
    """
    tekst = _hooiberg(recept)
    stappen = _stappen_tekst(recept)

    tags = []

    def voeg_toe(tag):
        if tag and tag not in tags:
            tags.append(tag)

    for tag in bestaande or []:
        voeg_toe(str(tag).strip().lower())

    # 1. Concrete ingredienten, in volgorde van de regels.
    gevonden = []
    for tag, patroon in _INGREDIENT_TAGS:
        if re.search(patroon, tekst, re.I):
            gevonden.append(tag)

    # 2. Grove categorie erbij; die zet de planner op het juiste spoor.
    categorieen = []
    for tag in gevonden:
        categorie = _CATEGORIE_UIT_TAG.get(tag)
        if categorie and categorie not in categorieen:
            categorieen.append(categorie)
    if not categorieen and not any(t in gevonden for t in ("ei", "tofu")):
        categorieen.append("vegetarisch")

    for tag in categorieen:
        voeg_toe(tag)
    for tag in gevonden:
        voeg_toe(tag)

    # 3. Bereidingswijze.
    for tag, patroon in _STIJL_TAGS:
        if re.search(patroon, stappen or tekst, re.I):
            voeg_toe(tag)

    # 4. Voedingsprofiel, als we de waarden hebben.
    voeding = (recept or {}).get("nutrition") or {}
    eiwit = float(voeding.get("protein") or (recept or {}).get("protein") or 0)
    koolhydraten = float(voeding.get("carbs") or (recept or {}).get("carbs") or 0)
    calorieen = float(voeding.get("calories") or (recept or {}).get("calories") or 0)
    if eiwit >= 30:
        voeg_toe("eiwitrijk")
    if koolhydraten and koolhydraten <= 25:
        voeg_toe("koolhydraatarm")
    if calorieen >= 900:
        voeg_toe("zwaar")
    elif calorieen and calorieen <= 500:
        voeg_toe("licht")

    # 5. Gang, zodat er altijd iets bruikbaars staat.
    voeg_toe(str((recept or {}).get("course") or "hoofdgerecht"))

    # Aanvullen tot het minimum met wat we nog weten.
    if len(tags) < MIN_TAGS:
        for reserve in ("west-europees", "doordeweeks", "familie", "eenvoudig"):
            if len(tags) >= MIN_TAGS:
                break
            voeg_toe(reserve)

    return tags[:MAX_TAGS]


def bepaal_allergenen(recept, bestaande=None):
    """Leidt allergenen af uit de ingredienten.

    Bewust ruim: de planner gebruikt allergenen als harde uitsluiting, dus een
    gemist allergeen is erger dan een overbodige waarschuwing.
    """
    tekst = _hooiberg(recept)
    uit = []
    for allergeen in bestaande or []:
        token = str(allergeen).strip().lower()
        if token and token not in uit:
            uit.append(token)
    for allergeen, patroon in _ALLERGEEN_REGELS:
        if allergeen not in uit and re.search(patroon, tekst, re.I):
            uit.append(allergeen)
    return uit


def verrijk(recept):
    """Vult tags en allergenen aan op een receptdict. Wijzigt en geeft terug."""
    recept["tags"] = bepaal_tags(recept, recept.get("tags"))
    recept["allergens"] = bepaal_allergenen(recept, recept.get("allergens"))
    return recept
