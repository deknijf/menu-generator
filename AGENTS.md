# AGENTS.md

Werkinstructies en domeinkennis voor AI-agents die aan deze codebase werken.
Documentatie voor mensen staat in `README.md` en `server_config/README.md`.

---

## 1. Wat dit project is

Een webapp die het wekelijkse avondmaal-probleem van één gezin oplost, in drie stappen
die aan elkaar hangen:

1. **Plannen** — markeer per dag of er gekookt wordt, en laat de app een gevarieerd menu
   genereren dat rekening houdt met allergieën, voorkeuren en nutritionele doelen.
2. **Boodschappen** — leid uit de geplande maaltijden automatisch een geaggregeerde
   boodschappenlijst af, geschaald naar het aantal personen.
3. **Bijhouden** — vink af wat je gekocht hebt; dat verhuist met datum en tijdstip naar
   een doorzoekbare geschiedenis.

Die derde stap is geen bijzaak. "Wat heb ik wanneer gekocht" is een expliciet doel van
het project, niet enkel een logboek van de boodschappenlijst.

### Mobiel is de primaire omgeving

De app wordt **zeer vaak op een smartphone in de winkel gebruikt**. Dat is geen
randgeval maar het hoofdscenario voor de boodschappen- en geschiedenistabs: één hand
aan de kar, wisselend licht, haast.

Concreet betekent dat voor elke wijziging:

- **Mobiel eerst testen, niet als nacontrole.** Een feature die alleen op desktop
  bekeken is, is niet af.
- **Toegankelijkheid is een harde eis, geen nice-to-have.** Zoomen moet werken,
  tekst moet leesbaar zijn, en knoppen moeten met een duim raakbaar zijn.
- De relevante regels staan in §7 onder "Mobiele toegankelijkheid"; de tests die ze
  bewaken staan in §10.

### Richting

- **Nu:** één gezin (de groep "De Knijf"). In productie op https://menu.deknijf.eu.
- **Later:** meerdere huishoudens. De `groups`-structuur bestaat al en is het groeipad.
  **Elke nieuwe query en feature moet strikt op `group_id` scopen** — ook als er vandaag
  maar één groep is. Een ontbrekende `WHERE group_id = ?` is nu onzichtbaar en straks een
  datalek tussen gezinnen.
- Zelfregistratie, wachtwoord-hashing bij opslag en echte migraties zijn nog niet nodig,
  maar worden dat zodra er een tweede huishouden bijkomt.

### Taal en formaat

De hele UI is **Nederlands**. Foutmeldingen, labels, knoppen en API-error-strings ook.
Datums in Europees formaat (`dd/mm/jjjj`). Code, commentaar en variabelenamen zijn Engels;
alleen wat de gebruiker ziet is Nederlands. Ingrediëntnamen worden lowercase genormaliseerd.

---

## 2. Stack

Flask 3.1 + SQLite, vanilla JS frontend, Jinja2 templates, Docker.
Dependencies staan in `requirements.txt` en zijn bewust minimaal: Flask, python-dotenv,
gunicorn. `werkzeug` komt mee met Flask (gebruikt voor password hashing).
Er is geen frontend-buildstap, geen ORM en geen migratieframework.

Houd het zo. Voeg geen dependency toe zonder dat expliciet voor te leggen.

---

## 3. Structuur

```
run.py                      Entrypoint. `app = create_app()`; gunicorn draait `run:app`.
app/__init__.py             create_app(): load_dotenv → load_settings → init_db →
                            bootstrap_db_settings → register_routes.
app/config_loader.py        DEFAULT_SETTINGS + deep_merge met config/settings.json.
                            Schrijft settings.json weg als die ontbreekt.
app/db.py          (~54KB)  Álle SQLite-toegang. 68 functies, 15 tabellen.
app/routes.py      (~79KB)  Álle HTTP. Module-level `_helpers` + één register_routes(app).
app/meal_engine.py          Pure planningslogica: scoring, variatie, rotatie, allergieën.
app/admin_ai.py             OpenRouter-integratie, de enige AI-bron.
app/logging_setup.py        Eén stdout-handler; logs gaan naar journalctl.
app/recipes.json            10 vaste basisrecepten.
static/app.js      (~78KB)  Eén bestand, vanilla JS, globaal `state`-object bovenaan.
static/styles.css           Eén bestand.
static/sw.js                Service worker. Wordt via /sw.js geserveerd, niet
                            via /static/, want anders is de scope te smal.
static/manifest.webmanifest PWA-manifest, geserveerd via /manifest.webmanifest.
tests/                      pytest; zie §10.
templates/                  index.html (de hele app), login, meal_detail,
                            account_detail, shopping_history_detail.
config/settings.json        Lokale config. Gitignored. Voorbeeld: settings.json.example.
data/                       SQLite DB, caches, geüploade foto's. Volume in productie.
server_config/              systemd unit + nginx vhost voor de server.
```

`routes.py` en `db.py` zijn groot maar consistent georganiseerd: helpers eerst, dan de
routes gegroepeerd per domein. Splits ze niet op als bijzaak bij een feature — als het
nodig is, is dat een eigen taak met eigen review.

---

## 4. Datamodel

15 tabellen in SQLite, aangemaakt in `db.init_db()`. Die functie is idempotent en doet
ook de migraties inline: `CREATE TABLE IF NOT EXISTS`, gevolgd door
`PRAGMA table_info(...)` + `ALTER TABLE ... ADD COLUMN` voor nieuwe kolommen.
**Nieuwe kolommen horen in dat patroon** — er is geen Alembic.

| Tabel | Rol |
|---|---|
| `groups` | Huishoudens. Groep 1 is de default en fallback. |
| `auth_users`, `auth_user_groups` | Accounts, rollen, groepslidmaatschap (n-op-n). |
| `users` | Lichtgewicht profiel per e-mail. |
| `app_settings` | Runtime-instellingen die de settings.json-waarden overschrijven. |
| `group_day_plans` | Kern van de planner: per groep per datum `cook` + `meal_id`. |
| `user_preferences` | Allergieën per gebruiker. |
| `user_food_preferences`, `user_food_dislikes` | Likes/dislikes per gebruiker. |
| `user_menu_preferences`, `group_menu_preferences` | `menu_mode` per gebruiker/groep. |
| `custom_meals` | Eigen recepten van de groep. |
| `shopping_items` | Actieve boodschappenlijst (met `sort_order` en `checked`). |
| `shopping_history` | Afgevinkte aankopen: `purchased_on`, `purchased_time_hhmm`, `items_json`. |
| `generated_ai_meals` | Persistente AI-maaltijden per groep, als JSON-blob. |

Bijna alles hangt aan `group_id`. `delete_group()` ruimt alle gerelateerde tabellen op —
**voeg een nieuwe group-scoped tabel daar ook toe**, en aan de
`UPDATE ... SET group_id = 1 WHERE group_id IS NULL`-normalisatie in `init_db()`.

---

## 5. Domeinlogica

### Maaltijdbronnen

Drie bronnen, gecombineerd tot één pool waaruit de planner kiest:

1. **`app/recipes.json`** — 10 vaste basisrecepten.
2. **Eigen maaltijden** — `custom_meals`, door de groep zelf ingevoerd.
3. **AI** — OpenRouter via `admin_ai.py`, gecachet in `data/openrouter_menu_cache.json`
   (6u TTL) en persistent in `generated_ai_meals`.

TheMealDB was ooit een vierde bron en is verwijderd. OpenRouter is nu de enige
AI-bron: valt die weg, dan levert `_external_ai_recipes_for_mode()` een lege lijst
en meldt de route dat er geen AI-maaltijden beschikbaar zijn. Er is bewust geen
stille terugval meer op een externe receptendienst.

`_recipe_map_for_user()` is de uitzondering: dat is een opzoektabel voor bestaande
plannen en bevat daarom altijd álle bronnen, ongeacht de menu_mode.

### menu_mode

Per groep instelbaar: `ai_only` (default), `ai_and_custom`, `custom_only`.
`_effective_menu_mode()` in `routes.py` degradeert automatisch als er te weinig eigen
maaltijden zijn — `custom_only` heeft er ≥8 nodig, `ai_and_custom` ≥1. De gevraagde en
de effectieve modus verschillen dus regelmatig; log of toon altijd de effectieve.

Let op: `_include_base_recipes_for_mode()` geeft alleen `True` bij `ai_and_custom`.
`recipes.json` doet dus **niet** mee in `ai_only`.

### Planner-opties en scoring

Opties: `high_protein`, `low_carb`, `prefer_fish`, `person_count` (1–8).
`meal_engine.generate_plan()` scoort per kookdag alle kandidaten en kiest de beste:

- `_recipe_score()` — basisscore op voorkeuren en nutritionele doelen.
- `_variety_penalty()` — straft herhaling van hetzelfde gerecht, dezelfde eiwitbron
  (`_primary_protein_key`) en hetzelfde zetmeel (`_starch_key`) binnen de laatste 6 dagen.
  Dit is wat "gevarieerd menu" concreet betekent; wijzig de gewichten niet zonder reden.
- `_max_occurrences()` — respecteert `rotation_limit` (`2_per_week` / `1_per_week` /
  `1_per_month`).
- `_is_allowed()` — harde filter op allergieën. Nooit omzeilen.
- Een random-component zorgt dat twee generaties niet identiek zijn. Tests moeten daar
  rekening mee houden (seed of assert op eigenschappen, niet op exacte output).

### Allergieën en voorkeuren

`_effective_allergies()` voegt de familie-allergieën uit `settings["family"]` samen met
de persoonlijke uit de DB. Allergieën zijn een **harde** uitsluiting; likes en dislikes
sturen enkel de score bij.

### Schaling

Recepten leggen hoeveelheden vast voor `app.base_servings` (default 2). De schaalfactor
is `person_count / base_servings`, toegepast in `_build_shopping_items()`. De AI-prompt
zegt expliciet dat hoeveelheden voor `base_servings` genoteerd moeten worden — als je
die prompt aanpast, hou die afspraak intact, anders klopt de boodschappenlijst niet meer.

### Boodschappen → geschiedenis

`_build_shopping_items()` loopt de geplande maaltijden af en aggregeert ingrediënten op
`(genormaliseerde naam, unit)`. Handmatige items kunnen erbij. De gebruiker vinkt af en
drukt "Gekocht": `complete_shopping_items()` verplaatst **alleen de afgevinkte** items
naar `shopping_history` met datum + tijdstip, en verwijdert ze uit de actieve lijst.
Niet-afgevinkte items blijven staan.

Het tijdstip gebruikt `app.time_zone` uit de settings (bv. `CEST`).

---

## 6. Permissies

Drie niveaus, en ze overlappen niet netjes — let op:

- **Super admin** — `_super_admin_email()`: het eerste account in `auth.local_users`, of
  anders `auth.admin_email`. Enige die de AI-configuratie mag lezen en schrijven.
- **`is_admin`** — globale admin. Enige die groepen mag verwijderen (`_can_delete_groups`).
- **`is_group_admin`** — admin binnen een groep. Mag gebruikers en menu_mode beheren.

Elke route begint met `_require_auth()`. Rechten checken doe je met de `_can_*`-helpers,
niet met een eigen ad-hoc conditie.

---

## 7. Conventies en valkuilen

**Cache-busting is handwerk.** Static assets worden geladen met een `?v=`-query:
`index.html` heeft `app.js?v=20260321v45` en `styles.css?v=20260210v17`. **Bump die
string bij elke wijziging aan `app.js` of `styles.css`**, anders zien gebruikers oude
code. De versies lopen momenteel uiteen tussen templates — bij een `styles.css`-wijziging
moeten ze in álle vijf templates mee.

**Frontend-state.** `static/app.js` heeft één globaal `state`-object bovenaan. Nieuwe
UI-state hoort daarin, niet in losse module-variabelen of in de DOM.

**Fail-closed defaults.** `DEFAULT_SETTINGS` in `config_loader.py` bevat bewust een leeg
wachtwoord en `allow_dev_login: False`. Er stond ooit een werkend account in met een
publiek bekend wachtwoord. Zet daar nooit een bruikbare credential terug.

**`allow_dev_login` is niet overschrijfbaar vanuit de DB.** `get_runtime_settings()`
legt `app_settings` over `settings.json` heen, maar leest `allow_dev_login` bewust alleen
uit de basisconfig. De dev-login-bypass kan dus niet via de UI of de database aangezet
worden. Hou dat zo.

**Foutmeldingen zijn Nederlands** en komen als `{"error": "..."}` met een passende
statuscode terug.

### Mobiele toegankelijkheid

De mobiele breakpoint is `max-width: 760px`. Daar wordt de sidebar een bottom nav met
`env(safe-area-inset-bottom)` voor toestellen met een home indicator.

Drie regels die makkelijk stuk gaan en daarom door tests bewaakt worden:

1. **Zoom nooit blokkeren.** De viewport-meta mag geen `user-scalable=no` of
   `maximum-scale` bevatten. Dat breekt WCAG 1.4.4, en in een winkel is inzoomen op je
   lijst precies wat je nodig hebt.
2. **Invoervelden minstens 16px op mobiel.** iOS Safari zoomt automatisch in zodra een
   tekstveld onder 16px focus krijgt. Dát was ooit de reden om zoom uit te zetten; de
   juiste oplossing is de velden vergroten, niet de zoom uitschakelen. Zie het
   mobiele blok onderaan `static/styles.css`. Let op de specificiteit: verspreid over
   het bestand staan class-selectoren zoals `.shopping-tools input[type="text"]` die
   een kleinere `font-size` zetten en een generieke `input`-regel overrulen.
3. **Aanraakvlakken minstens 44×44 px** (Apple HIG, WCAG 2.5.5). De klikbare zone telt,
   niet het zichtbare vakje: de checkbox in de boodschappenlijst is zelf 20×20, maar het
   `.shop-checkline`-label eromheen is 44 hoog en dát is wat je raakt.

---

## 8. Deployment

De repo `deknijf/menu-generator` op GitHub is **publiek**, en de app draait op het open
internet. Beide feiten zijn relevant bij elke wijziging.

**Release-flow:**
1. Git tag pushen → GitHub Actions (`.github/workflows/`) bouwt en pusht
   `deknijf/menu-generator:<tag>` naar Docker Hub.
2. Op de server (`admin@menu.deknijf.eu`, map `~/meal-planner`) staat in
   `docker-compose.yml` een **expliciet gepinde tag**. Die moet handmatig mee omhoog.
3. `systemctl restart meal-planner` doet `docker compose pull && up -d`.

Nginx doet reverse proxy naar **`127.0.0.1:8001`**, met Let's Encrypt. Op dezelfde
server draaien ook Immich en een docstore — niet aankomen. Die docstore heeft poort
8000 al, vandaar dat de container op hostpoort 8001 zit. Overschrijf de compose op de
server dus nooit klakkeloos met een variant die 8000 gebruikt: dan faalt de start met
"port is already allocated" en ligt de site eruit.

`~/meal-planner` op de server is **geen git clone** maar een losse map. Wijzigingen aan
`docker-compose.yml` moeten daar met de hand gebeuren; maak eerst een kopie in
`~/meal-planner-backups/`.

Alleen `./data` en `./config` zijn gemount. **Alles buiten die twee mappen is weg na een
redeploy.** Schrijf runtime-state dus nooit ergens anders naartoe.

---

## 9. Openstaande punten

1. **Vier meal-foto's zijn getrackt in `data/pictures/`** terwijl dat runtime-data is.
   `.gitignore` stopt nieuwe uploads; de bestaande vier zijn nog niet untrackt.
2. **`data/menu.db` is een leeg restant** van een oude opzet en mag weg.
3. **Er is geen migratieframework.** `init_db()` doet het inline met
   `CREATE TABLE IF NOT EXISTS` en `PRAGMA table_info` + `ALTER TABLE`. Werkbaar voor
   één huishouden; zodra er een tweede bijkomt is dit het eerste dat gaat wringen.
4. **`routes.py` (~80KB) en `db.py` (~57KB) mogen ooit gesplitst.** Niet als bijzaak
   bij een feature — dat is een eigen taak met eigen review.

### Recent afgehandeld

Zodat je niet opnieuw voorstelt wat er al staat:

- TheMealDB verwijderd; OpenRouter is de enige AI-bron.
- `.env` wordt gemount in `docker-compose.yml`, dus de OpenRouter-key overleeft een
  redeploy. Het bestand moet wel op de host bestaan vóór de stack start, anders maakt
  Docker er een directory van.
- Login gehard: throttle op mislukte pogingen (`login_attempts`-tabel, 8 pogingen per
  15 minuten per IP én per e-mail), `SESSION_COOKIE_SECURE`/`HTTPONLY`/`SAMESITE`, en
  ProxyFix zodat `remote_addr` achter nginx klopt.
- Logging naar stdout; `admin_ai.py` slikt geen fouten meer stil.
- Aanraakvlakken op mobiel naar minstens 44×44.
- PWA: manifest + service worker. De boodschappenlijst blijft leesbaar zonder bereik,
  en afvinken/verwijderen gaat naar een wachtrij in localStorage die bij herstel
  automatisch wordt afgespeeld. `boot()` schermt elke opstartstap apart af — zonder dat
  brak de eerste mislukte call het hele opstarten en bleef juist de lijst leeg.

---

## 10. Werkafspraken

### Verifiëren

Testdependencies staan in `requirements-dev.txt` en zitten bewust niet in de image:

```bash
pip install -r requirements-dev.txt
playwright install chromium --only-shell   # eenmalig, voor de smoke test
```

De suite valt uiteen in twee delen.

**Unit tests** — snel, geen server, geen database. Draai deze voor elke commit:

```bash
pytest -m "not live"
```

- `tests/test_meal_engine.py` — allergiefilter, rotatielimieten, variatie, buren.
  `generate_plan()` heeft een random-component, dus deze tests asserteren op
  eigenschappen ("komt nooit voor", "hoogstens N keer") en draaien waar nodig meerdere
  rondes. Assert nooit op exacte output.
- `tests/test_shopping.py` — unit- en naamnormalisatie plus de aggregatie in
  `_build_shopping_items()`. De twee DB-afhankelijkheden worden gemonkeypatcht, zodat
  `data/app.db` niet aangeraakt wordt.
- `tests/test_templates.py` — statische checks op de templates: zoom niet geblokkeerd,
  cache-busting aanwezig en gelijk, geen hardcoded e-mailadressen.

**Smoke test** — Playwright tegen een draaiende app, read-only:

```bash
MP_URL=http://localhost:8000 MP_EMAIL=... MP_PASS=... pytest -m live
```

Zonder `MP_EMAIL`/`MP_PASS` worden deze overgeslagen. `tests/test_smoke_live.py` dekt
auth, de read-only endpoints, alle tabs, en een apart mobiel blok op een 390×844
viewport met touch-emulatie: overflow per tab, 16px invoervelden, zoom niet geblokkeerd,
bottom nav ≥44px en de afvink-zone van de boodschappenlijst.

Draait de smoke test tegen productie, dan test je de gedeployede versie — niet je
werkkopie. Falen de mobiele a11y-tests daar terwijl ze lokaal slagen, dan is de fix
gewoon nog niet gedeployed.

Playwright is ook beschikbaar als MCP-server in deze omgeving.

Bij UI-werk: controleer het resultaat in de echte app op een mobiele viewport, niet
alleen in de code.

### Wat een agent niet zelfstandig doet

- **Niet committen of taggen** zonder te vragen. Een tag start automatisch een
  Docker Hub-build.
- **Niet deployen.** De compose-pin bijwerken en de service herstarten op de server blijft
  handwerk van Bert.
- **Niet schrijven naar productiedata.** `POST /api/generate` en de shopping-mutaties
  overschrijven de echte weekplanning. Read-only testen tegen productie mag; muteren
  vraag je eerst.

### Credentials

Nooit inloggegevens in de repo, in een testbestand, of in een commit. Ze gaan via
environment variables of via `config/settings.json` en `.env` — beide gitignored, en
beide ook afgedekt in `.dockerignore` zodat ze niet in een image-layer belanden.
