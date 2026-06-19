# 🌿 WasserWächter – Telegram Bot

Erinnert dich täglich daran, deine Pflanzen zu gießen.

## Deployment auf dem OrangePi

### Voraussetzungen
- Docker & Docker Compose installiert
- Telegram Bot Token (über @BotFather erstellen)

### Schritte

```bash
# 1. Repo/Dateien auf den OrangePi kopieren (z.B. via scp oder git)

# 2. .env anlegen
cp .env.example .env
nano .env          # BOT_TOKEN eintragen

# 3. Datenbank-Verzeichnis anlegen
mkdir -p data

# 4. Image bauen und starten
docker compose up -d --build

# 5. Logs verfolgen
docker compose logs -f
```

### Datenbank sichern
Die SQLite-Datenbank liegt in `./data/Pflanzendaten.db` auf dem Host.
Einfach diese Datei sichern.

### Bot neu starten
```bash
docker compose restart
```

### Bot stoppen
```bash
docker compose down
```

## Funktionen

| Funktion | Beschreibung |
|---|---|
| 💧 Pflanze gegossen | Markiert eine Pflanze als heute gegossen |
| 📋 Übersicht | Zeigt alle Pflanzen mit Intervall und Tagen bis zum nächsten Gießen |
| 🌱 Neue Pflanze | Fügt eine neue Pflanze hinzu |
| ✏️ Bearbeiten | Intervall ändern, letztes Gießen setzen, oder Pflanze löschen |
| 📅 Kalender teilen | Kalender einer anderen Person verknüpfen (Telegram-ID eingeben) |

Täglich um **10:00 Uhr** schickt der Bot eine Erinnerung für alle fälligen Pflanzen.
