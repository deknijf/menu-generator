"""Statische checks op de Jinja-templates.

Deze draaien zonder server en zonder database, en bewaken afspraken die anders pas
in productie opvallen: zoom-toegankelijkheid, cache-busting en het niet lekken van
persoonsgegevens in publieke HTML.
"""

import re
from pathlib import Path

import pytest

TEMPLATE_DIR = Path("templates")
TEMPLATES = sorted(TEMPLATE_DIR.glob("*.html"))


def _read(path):
    return path.read_text(encoding="utf-8")


def test_er_zijn_templates_gevonden():
    assert TEMPLATES, "geen templates gevonden; draait pytest vanuit de repo-root?"


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_template_heeft_viewport_meta(template):
    assert 'name="viewport"' in _read(template)


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_template_blokkeert_zoomen_niet(template):
    """De app wordt in de winkel gebruikt; pinch-zoom moet blijven werken.

    user-scalable=no en maximum-scale breken WCAG 1.4.4 (Resize Text). Wie de
    auto-zoom van iOS op invoervelden wil vermijden, zet die velden op 16px
    (zie de mobiele blok onderaan static/styles.css) in plaats van zoom uit te zetten.
    """
    html = _read(template)
    viewport = re.search(r'<meta\s+name="viewport"[^>]*content="([^"]*)"', html)
    assert viewport, f"{template.name} heeft geen leesbare viewport meta"
    content = viewport.group(1).lower()

    assert "user-scalable=no" not in content.replace(" ", "")
    assert "maximum-scale" not in content


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_static_assets_hebben_cache_busting(template):
    """Zonder ?v= blijven gebruikers oude CSS/JS zien na een release."""
    html = _read(template)
    for asset in re.findall(r'(?:href|src)="(/static/[^"]+\.(?:css|js))(\?[^"]*)?"', html):
        pad, query = asset
        assert query and "v=" in query, f"{template.name}: {pad} mist een ?v= cache-bust"


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_template_bevat_geen_hardcoded_emailadres(template):
    """Er stond ooit een persoonlijk adres in de dev-login link van login.html."""
    html = _read(template)
    # Jinja-expressies mogen wel over e-mail gaan; het gaat om letterlijke adressen.
    zonder_jinja = re.sub(r"\{\{.*?\}\}|\{%.*?%\}", "", html, flags=re.DOTALL)
    adressen = re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", zonder_jinja)
    # example.com/.org/.net zijn gereserveerd voor documentatie (RFC 2606),
    # en naam@domein.be is de placeholder in het loginformulier.
    placeholder = re.compile(r"@(example\.(com|org|net)|domein\.be)$")
    echte = [a for a in adressen if not placeholder.search(a)]
    assert not echte, f"{template.name} bevat een hardcoded e-mailadres: {echte}"


def test_styles_versie_is_gelijk_in_alle_templates():
    """Eén stylesheet, dus één versiestring. Anders cachet een deel van de app oud."""
    versies = {}
    for template in TEMPLATES:
        match = re.search(r'/static/styles\.css\?v=([^"]+)', _read(template))
        if match:
            versies.setdefault(match.group(1), []).append(template.name)
    assert len(versies) <= 1, f"styles.css heeft meerdere versiestrings: {versies}"


def test_mobiele_invoervelden_zijn_minstens_16px():
    """Onder 16px zoomt iOS Safari automatisch in bij focus op een invoerveld.

    Dat was de reden dat de viewport ooit op user-scalable=no stond.
    """
    css = Path("static/styles.css").read_text(encoding="utf-8")
    mobiel = re.search(
        r"@media\s*\(max-width:\s*760px\)\s*\{(.*)$", css, re.DOTALL
    )
    assert mobiel, "geen mobiel media-blok gevonden in static/styles.css"
    assert "font-size: 16px" in mobiel.group(1)
