# Menu Planner Webapp

Webapp voor weekmenu-planning met focus op:
- koken/niet-koken dagen in een kalender
- maaltijden genereren met voorkeuren (meer proteine, minder koolhydraten, extra vis)
- menu en boodschappen schalen op aantal personen (1-4)
- rekening houden met allergieen en familievoorkeuren
- persoonlijke allergieen instellen via profielpagina
- boodschappenlijst op basis van geplande maaltijden
- login met e-mail en wachtwoord
- 1 admin account (`admin@example.com`) + extra accounts via config
- datumweergave in Europees formaat (`dd/mm/jjjj`)

## Stack
- Flask + SQLite
- Frontend: HTML/CSS/JS
- Docker + docker-compose

## Configuratie
Gebruik `config/settings.json.example` als startpunt en maak lokaal `config/settings.json` aan (staat in `.gitignore`).

Pas `config/settings.json` aan voor:
- `auth.admin_email`
- `auth.local_users` (accounts met e-mail/wachtwoord)
- `auth.allowed_emails` (voor optionele dev-login)
- familie-allergieen/voorkeuren
- nutritionele doelstellingen
- `app.base_servings` (basisporties voor ingrediëntschaling)

### Test-login standaard
In `config/settings.json` staat standaard:
- e-mail: `admin@example.com`
- wachtwoord: `choose-a-strong-password`

Wijzig dit meteen voor productie.

## Lokaal draaien (zonder Docker)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export FLASK_DEBUG=true
python run.py
```
Open: `http://localhost:8000`

## Docker draaien
```bash
docker compose up --build
```
Open: `http://localhost:8000`

## Git tag -> Docker Hub release
Bij elke push van een git tag start GitHub Actions automatisch een build en push naar:
- `deknijf/menu-generator:<git-tag>`

Voorbeeld:
```bash
git tag v1.2.3
git push origin v1.2.3
```
Resultaat:
- `deknijf/menu-generator:v1.2.3`

Vereiste GitHub repository secrets:
- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN` (Docker Hub access token)

## Dev login (optioneel)
Als `auth.allow_dev_login` op `true` staat, kan je ook testen via:
- `/auth/dev?email=admin@example.com`

Zet `auth.allow_dev_login` op `false` om dit uit te schakelen.
