# Meal Planner systemd service (Debian)

Deze map bevat een `systemd` unit voor productie op Debian, met Docker Compose.

## Bestanden

- `meal-planner.service`: systemd service om de compose stack automatisch te starten bij boot.
- `menu.example.com.conf`: Nginx vhost (reverse proxy) voor `menu.example.com`.
- `meal-planner-backup.sh`: dagelijkse backup van database en config.

## Verwachte paden op server

- Project map: `/home/admin/meal-planner`
- Compose file: `/home/admin/meal-planner/docker-compose.yml`

Pas deze paden aan in `meal-planner.service` als jouw serverlayout anders is.

## Deploy stappen

1. Kopieer service file:

```bash
sudo cp /home/admin/meal-planner/server_config/meal-planner.service /etc/systemd/system/meal-planner.service
```

2. Herlaad systemd en activeer service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable meal-planner.service
sudo systemctl start meal-planner.service
```

3. Controleer status:

```bash
sudo systemctl status meal-planner.service
```

4. Volg logs:

```bash
journalctl -u meal-planner.service -f
```

## Handige commando's

- Herstarten:

```bash
sudo systemctl restart meal-planner.service
```

- Stoppen:

```bash
sudo systemctl stop meal-planner.service
```

## Vereisten

- Docker engine geïnstalleerd.
- Docker Compose plugin beschikbaar via `docker compose`.
- Gebruiker `admin` heeft toegang tot Docker (typisch via de `docker` group).

## Backups

De SQLite database bevat alles waar de app om draait: aankoopgeschiedenis, eigen
recepten en planningen. Eén bestand, dus zonder backup is één schijffout definitief
verlies.

1. Kopieer het script en maak het uitvoerbaar:

```bash
cp /home/admin/meal-planner/server_config/meal-planner-backup.sh /home/admin/meal-planner-backup.sh
chmod +x /home/admin/meal-planner-backup.sh
```

2. Draai het één keer met de hand om te controleren:

```bash
/home/admin/meal-planner-backup.sh
```

3. Zet het in cron (dagelijks om 03:15):

```bash
crontab -e
# 15 3 * * * /home/admin/meal-planner-backup.sh >> /home/admin/meal-planner-backups/backup.log 2>&1
```

Backups komen in `/home/admin/meal-planner-backups/` en worden 30 dagen bewaard.
Het script gebruikt de sqlite3 backup-API en niet `cp`, zodat de kopie consistent
is terwijl de app doorschrijft.

### Terugzetten

```bash
cd /home/admin/meal-planner
sudo systemctl stop meal-planner
gunzip -c /home/admin/meal-planner-backups/app.db.<stamp>.gz > data/app.db
sudo systemctl start meal-planner
```

Controleer een backup zonder hem terug te zetten:

```bash
gunzip -c /home/admin/meal-planner-backups/app.db.<stamp>.gz > /tmp/check.db
sqlite3 /tmp/check.db 'PRAGMA integrity_check;'
sqlite3 /tmp/check.db 'SELECT COUNT(*) FROM shopping_history;'
rm /tmp/check.db
```

## Nginx reverse proxy

1. Kopieer de vhost config:

```bash
sudo cp /home/admin/meal-planner/server_config/menu.example.com.conf /etc/nginx/sites-available/menu.example.com.conf
```

2. Activeer de site:

```bash
sudo ln -s /etc/nginx/sites-available/menu.example.com.conf /etc/nginx/sites-enabled/menu.example.com.conf
```

3. Test en herlaad Nginx:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## SSL via Let's Encrypt (Certbot)

1. Installeer Certbot + Nginx plugin:

```bash
sudo apt update
sudo apt install -y certbot python3-certbot-nginx
```

2. Vraag certificaat aan en laat Certbot Nginx aanpassen:

```bash
sudo certbot --nginx -d menu.example.com
```

3. Controleer auto-renew:

```bash
sudo systemctl status certbot.timer
sudo certbot renew --dry-run
```

Opmerking:
- Zorg dat DNS van `menu.example.com` naar je server-IP wijst.
- Poorten `80` en `443` moeten open staan in firewall/security group.
