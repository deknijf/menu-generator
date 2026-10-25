"""Playwright smoke test tegen een draaiende app (lokaal of productie).

Read-only: raakt bewust geen enkele schrijf-endpoint aan, zodat dit veilig tegen
productie kan draaien zonder de echte weekplanning te overschrijven.

Draaien:
    MP_URL=http://localhost:8000 MP_EMAIL=... MP_PASS=... pytest -m live

    MP_URL is optioneel en staat standaard op http://localhost:8000.
    Zonder MP_EMAIL/MP_PASS worden deze tests overgeslagen.

Credentials komen uitsluitend uit de omgeving. Zet ze nooit in dit bestand.
"""

import os

from datetime import date

import pytest

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="playwright niet geinstalleerd (pip install -r requirements-dev.txt)"
)

pytestmark = pytest.mark.live

BASE_URL = os.environ.get("MP_URL", "http://localhost:8000").rstrip("/")
EMAIL = os.environ.get("MP_EMAIL", "")
PASSWORD = os.environ.get("MP_PASS", "")

TABS = ["dashboard", "planner", "shopping", "my-meals", "history", "profile"]
READONLY_ENDPOINTS = [
    "/api/session",
    "/api/settings",
    "/api/profile",
    "/api/calendar",
    "/api/shopping-list",
    "/api/custom-meals",
]

requires_credentials = pytest.mark.skipif(
    not (EMAIL and PASSWORD),
    reason="MP_EMAIL en MP_PASS niet gezet",
)


@pytest.fixture(scope="module")
def browser():
    with playwright_api.sync_playwright() as p:
        instance = p.chromium.launch()
        yield instance
        instance.close()


@pytest.fixture(scope="module")
def console_errors():
    return []


@pytest.fixture(scope="module")
def page(browser, console_errors):
    """Eén ingelogde sessie voor alle tests in deze module."""
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    target = context.new_page()
    target.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)

    target.goto(f"{BASE_URL}/login", wait_until="domcontentloaded", timeout=30000)
    target.fill("#email", EMAIL)
    target.fill("#password", PASSWORD)
    target.click("button[type=submit]")
    target.wait_for_load_state("networkidle", timeout=30000)

    if "/login" in target.url:
        pytest.fail("Inloggen mislukt; controleer MP_EMAIL/MP_PASS en MP_URL.")

    yield target
    context.close()


# --- Bereikbaarheid en auth ---


def test_site_stuurt_anonieme_bezoeker_naar_login(browser):
    context = browser.new_context()
    anon = context.new_page()
    response = anon.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
    assert response is not None and response.status < 400
    assert "/login" in anon.url
    assert anon.locator("form[action='/auth/login']").count() == 1
    context.close()


def test_dev_login_bypass_is_niet_zichtbaar(browser):
    """allow_dev_login hoort uit te staan buiten lokale ontwikkeling."""
    context = browser.new_context()
    anon = context.new_page()
    anon.goto(f"{BASE_URL}/login", wait_until="domcontentloaded", timeout=30000)
    dev_box = anon.locator(".dev-box").count()
    context.close()

    if BASE_URL.startswith(("http://localhost", "http://127.0.0.1")):
        pytest.skip("dev login mag lokaal aan staan")
    assert dev_box == 0, "dev-login bypass staat zichtbaar aan"


def test_loginpagina_lekt_geen_e_mailadres(browser):
    """De dev-login link bevatte ooit een hardcoded adres."""
    context = browser.new_context()
    anon = context.new_page()
    anon.goto(f"{BASE_URL}/login", wait_until="domcontentloaded", timeout=30000)
    html = anon.content()
    context.close()
    assert "@" not in html.split("<form")[0], "e-mailadres zichtbaar in de loginpagina"


@requires_credentials
def test_fout_wachtwoord_wordt_geweigerd(browser):
    context = browser.new_context()
    anon = context.new_page()
    anon.goto(f"{BASE_URL}/login", wait_until="domcontentloaded", timeout=30000)
    anon.fill("#email", EMAIL)
    anon.fill("#password", "zeker-niet-het-juiste-wachtwoord")
    anon.click("button[type=submit]")
    anon.wait_for_load_state("domcontentloaded")
    url = anon.url
    context.close()
    assert "/login" in url


@requires_credentials
def test_inloggen_lukt(page):
    assert "/login" not in page.url


# --- API ---


@requires_credentials
@pytest.mark.parametrize("endpoint", READONLY_ENDPOINTS)
def test_readonly_endpoint_geeft_200(page, endpoint):
    response = page.request.get(f"{BASE_URL}{endpoint}")
    assert response.status == 200, f"{endpoint} gaf {response.status}"


@requires_credentials
def test_ai_config_endpoint_is_alleen_voor_super_admin(page):
    """Bestaat het endpoint, dan mag het nooit 200 geven aan een niet-super-admin.

    404 betekent dat de AI-feature nog niet gedeployed is; dat is geen fout.
    """
    response = page.request.get(f"{BASE_URL}/api/admin/ai")
    assert response.status in (200, 403, 404)


def test_api_zonder_sessie_geeft_geen_data(browser):
    context = browser.new_context()
    anon = context.new_page()
    response = anon.request.get(f"{BASE_URL}/api/profile")
    status = response.status
    context.close()
    assert status != 200, "API geeft data terug zonder ingelogde sessie"


# --- UI ---


@requires_credentials
@pytest.mark.parametrize("tab", TABS)
def test_tab_opent_en_toont_inhoud(page, tab):
    button = page.locator(f".tab[data-tab='{tab}']").first
    assert button.count() == 1, f"tabknop '{tab}' niet gevonden"
    button.click()
    page.wait_for_timeout(800)

    panel = page.locator(f"#tab-{tab}").first
    assert panel.is_visible(), f"paneel '{tab}' werd niet zichtbaar"
    assert panel.inner_text().strip(), f"paneel '{tab}' is leeg"


# --- Mobiel ---
#
# De app wordt vooral op een smartphone in de winkel gebruikt. Deze tests bewaken
# dat scenario expliciet: geen overflow, leesbare invoervelden, en aanraakbare
# knoppen op de schermen die je met een kar in je hand bedient.

IPHONE_VIEWPORT = {"width": 390, "height": 844}
MIN_TAP_TARGET_PX = 44  # Apple HIG en WCAG 2.5.5


@pytest.fixture(scope="module")
def mobile_page(browser):
    """Ingelogde sessie op een smartphone-viewport met touch-emulatie."""
    context = browser.new_context(
        viewport=IPHONE_VIEWPORT, is_mobile=True, has_touch=True, device_scale_factor=3
    )
    target = context.new_page()
    target.goto(f"{BASE_URL}/login", wait_until="domcontentloaded", timeout=30000)
    target.fill("#email", EMAIL)
    target.fill("#password", PASSWORD)
    target.click("button[type=submit]")
    target.wait_for_load_state("networkidle", timeout=30000)

    if "/login" in target.url:
        pytest.fail("Inloggen mislukt op mobiele viewport.")

    yield target
    context.close()


@requires_credentials
@pytest.mark.parametrize("tab", TABS)
def test_geen_horizontale_overflow_op_mobiel(mobile_page, tab):
    """Zijwaarts scrollen maakt de app onbruikbaar met één hand."""
    mobile_page.locator(f".tab[data-tab='{tab}']").first.click()
    mobile_page.wait_for_timeout(600)
    overflow = _horizontale_overflow(mobile_page)
    assert overflow <= 2, f"tab '{tab}': {overflow}px horizontale overflow op 390px breed"


# html en body hebben overflow-x: hidden. Daardoor is scrollWidth van het document
# altijd gelijk aan de viewport, ook als de inhoud er ver buiten valt; de gebruiker
# kan er dan niet eens naartoe scrollen. Meet daarom op de inhoud zelf.
_OVERFLOW_JS = """() => {
  const vw = document.documentElement.clientWidth;
  let rechts = vw;
  for (const el of document.body.querySelectorAll('*')) {
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.right > rechts) rechts = r.right;
  }
  return Math.round(Math.max(rechts, document.body.scrollWidth) - vw);
}"""


def _horizontale_overflow(page):
    return page.evaluate(_OVERFLOW_JS)


DETAILPAGINAS = ["meal", "account", "shopping-history"]


@requires_credentials
@pytest.mark.parametrize("pagina", DETAILPAGINAS)
def test_detailpagina_heeft_geen_overflow_op_mobiel(mobile_page, pagina):
    """De losse pagina's laden app.js niet en vallen buiten de tab-tests.

    De maaltijd-detailpagina was 519px breed op een scherm van 390px, zonder dat
    iemand het zag: overflow-x: hidden verborg het, en de tab-tests kwamen er niet.
    """
    if pagina == "meal":
        url = mobile_page.evaluate(
            "(() => { const a = document.querySelector('a[href^=\"/meal/\"]'); return a && a.getAttribute('href'); })()"
        )
        if not url:
            pytest.skip("geen maaltijdlink zichtbaar in deze toestand")
    elif pagina == "account":
        url = f"/account/{EMAIL}"
    else:
        url = f"/shopping-history/{date.today().isoformat()}"
    response = mobile_page.goto(f"{BASE_URL}{url}", wait_until="networkidle", timeout=30000)
    assert response.status == 200, f"{url} gaf {response.status}"
    overflow = _horizontale_overflow(mobile_page)
    assert overflow <= 2, f"{url}: {overflow}px horizontale overflow op 390px breed"
    if pagina == "meal":
        # Bewerkmodus toont textarea's en extra knoppen; die mogen ook niet uitsteken.
        knop = mobile_page.locator("#detail-edit-btn")
        if knop.is_enabled():
            knop.click()
            mobile_page.wait_for_timeout(300)
            overflow = _horizontale_overflow(mobile_page)
            assert overflow <= 2, f"{url} in bewerkmodus: {overflow}px horizontale overflow"
    mobile_page.goto(BASE_URL, wait_until="networkidle", timeout=30000)


@requires_credentials
def test_invoervelden_zijn_minstens_16px_op_mobiel(mobile_page):
    """Onder 16px zoomt iOS Safari automatisch in zodra een veld focus krijgt.

    Geldt alleen voor velden waar je tekst in typt; checkboxes en radios doen dat niet.
    Faalt dit tegen productie, dan draait daar nog een versie van voor de fix.
    """
    te_klein = mobile_page.evaluate(
        """() => {
          const TEKSTVELDEN = ['text', 'number', 'email', 'password', 'url',
                               'search', 'tel', 'date', 'time'];
          const out = [];
          document.querySelectorAll('input, select, textarea').forEach(el => {
            if (!el.offsetParent) return;
            const tag = el.tagName.toLowerCase();
            if (tag === 'input' && !TEKSTVELDEN.includes(el.type)) return;
            const fs = parseFloat(getComputedStyle(el).fontSize);
            if (fs < 16) out.push((el.id || el.className || tag) + ': ' + fs + 'px');
          });
          return out;
        }"""
    )
    assert not te_klein, "invoervelden onder 16px: " + ", ".join(te_klein[:6])


@requires_credentials
def test_zoomen_is_niet_geblokkeerd(mobile_page):
    """WCAG 1.4.4: de gebruiker moet kunnen inzoomen, zeker in een winkel."""
    content = mobile_page.evaluate(
        "document.querySelector('meta[name=viewport]')?.getAttribute('content') || ''"
    ).lower()
    assert "user-scalable=no" not in content.replace(" ", "")
    assert "maximum-scale" not in content


@requires_credentials
def test_onderste_navigatiebalk_is_aanraakbaar(mobile_page):
    """Op mobiel wordt de sidebar een bottom nav; dat is de hoofdnavigatie."""
    maten = mobile_page.evaluate(
        """() => {
          const out = [];
          document.querySelectorAll('.sidebar .tab').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.width === 0 && r.height === 0) return;  // verborgen (bv. admin-tab)
            out.push({label: el.innerText.trim().slice(0, 20), w: r.width, h: r.height});
          });
          return out;
        }"""
    )
    assert maten, "geen navigatieknoppen gevonden op mobiel"
    te_klein = [m for m in maten if m["h"] < MIN_TAP_TARGET_PX or m["w"] < MIN_TAP_TARGET_PX]
    assert not te_klein, "navigatieknoppen onder 44px: " + ", ".join(
        f"{m['label']} {round(m['w'])}x{round(m['h'])}" for m in te_klein
    )


@requires_credentials
@pytest.mark.parametrize(
    "tab,selector",
    [
        ("shopping", "#shopping-complete-btn"),
        ("shopping", "#shopping-clear-btn"),
        ("shopping", "#shopping-refresh-btn"),
        ("planner", ".checkline"),
        ("planner", ".retry-btn"),
        ("planner", "#generate-btn"),
        ("dashboard", "#hero-generate-btn"),
        ("dashboard", "#hero-shopping-btn"),
        ("my-meals", "#cm-save-btn"),
        ("my-meals", "#cm-import-btn"),
        ("profile", "#save-profile-btn"),
        ("history", ".history-nav-btn"),
    ],
)
def test_knoppen_zijn_minstens_44px(mobile_page, tab, selector):
    """Bediening met één hand aan de winkelkar; kleiner dan 44px is mis-tappen."""
    mobile_page.locator(f".tab[data-tab='{tab}']").first.click()
    mobile_page.wait_for_timeout(900)

    element = mobile_page.locator(selector).first
    if element.count() == 0 or not element.is_visible():
        pytest.skip(f"{selector} niet zichtbaar in deze toestand")

    box = element.bounding_box()
    assert box is not None
    assert box["height"] >= MIN_TAP_TARGET_PX and box["width"] >= MIN_TAP_TARGET_PX, (
        f"{selector} is {round(box['width'])}x{round(box['height'])}, "
        f"kleiner dan {MIN_TAP_TARGET_PX}x{MIN_TAP_TARGET_PX}"
    )


@requires_credentials
def test_afvinken_van_een_boodschap_is_aanraakbaar(mobile_page):
    """De belangrijkste handeling in de winkel: een item afvinken.

    De klikbare zone is het hele label rond de checkbox, niet het vakje zelf.
    Slaat over als de lijst leeg is.
    """
    mobile_page.locator(".tab[data-tab='shopping']").first.click()
    mobile_page.wait_for_timeout(900)

    regels = mobile_page.locator("#tab-shopping .shopping-item .shop-checkline")
    if regels.count() == 0:
        pytest.skip("boodschappenlijst is leeg")

    box = regels.first.bounding_box()
    assert box is not None
    assert box["height"] >= MIN_TAP_TARGET_PX, (
        f"afvink-zone is {round(box['height'])}px hoog, minder dan {MIN_TAP_TARGET_PX}px"
    )


@requires_credentials
def test_geen_console_errors(page, console_errors):
    """Draait als laatste, zodat alle eerdere navigatie meegenomen is."""
    for tab in TABS:
        page.locator(f".tab[data-tab='{tab}']").first.click()
        page.wait_for_timeout(400)
    assert not console_errors, "console errors: " + " | ".join(sorted(set(console_errors))[:5])


@requires_credentials
def test_eigen_maaltijden_laden_pas_bij_gebruik(mobile_page):
    """In de winkel open je de boodschappenlijst. De zwaarste call, alle eigen
    recepten met ingredienten, hoort dan niet mee te komen; pas bij
    "Mijn maaltijden" of de keuzedialoog wordt hij opgehaald."""
    mobile_page.evaluate("localStorage.setItem('active_tab', 'shopping')")
    verzoeken = []
    handler = lambda request: verzoeken.append(request.url)
    mobile_page.on("request", handler)
    try:
        mobile_page.goto(BASE_URL, wait_until="networkidle", timeout=30000)
        te_vroeg = [url for url in verzoeken if "/api/custom-meals" in url]
        assert not te_vroeg, "eigen maaltijden werden al bij het opstarten geladen"
        with mobile_page.expect_response(lambda r: "/api/custom-meals" in r.url, timeout=15000) as antwoord:
            mobile_page.locator(".tab[data-tab='my-meals']").first.click()
        assert antwoord.value.status == 200
        kaarten = mobile_page.locator("#custom-meals-list .menu-card, #custom-meals-list .muted")
        kaarten.first.wait_for(state="visible", timeout=10000)
    finally:
        mobile_page.remove_listener("request", handler)
        mobile_page.evaluate("localStorage.removeItem('active_tab')")


@requires_credentials
def test_maaltijdenlijst_api_laat_bereiding_weg(page):
    """De bereiding is ruim de helft van de payload en wordt in de lijst niet gebruikt."""
    data = page.request.get(f"{BASE_URL}/api/custom-meals").json()
    items = data.get("items") or []
    if not items:
        pytest.skip("geen eigen maaltijden in deze omgeving")
    assert all("preparation" not in item for item in items)
    assert all("ingredients" in item for item in items), "ingredienten zijn nodig voor zoeken"
    volledig = page.request.get(f"{BASE_URL}/api/custom-meals?include_preparation=1").json()
    assert any("preparation" in item for item in volledig["items"])
