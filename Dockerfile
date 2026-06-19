# Basis-Image: offizielles Python-Slim, kompatibel mit ARM64/ARMv7 (OrangePi)
FROM python:3.12-slim

# Arbeitsverzeichnis im Container
WORKDIR /app

# Abhängigkeiten zuerst kopieren (Layer-Caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Quellcode kopieren
COPY main.py db.py translations.py ./

# Persistenz-Verzeichnis anlegen (wird als Volume gemountet)
RUN mkdir -p /data

# Datenbankpfad als Umgebungsvariable (überschreibbar)
ENV DB_PATH=/data/Pflanzendaten.db

# BOT_TOKEN muss beim Starten übergeben werden (nicht im Image gespeichert!)
# Beispiel: docker run -e BOT_TOKEN=xxx ...

CMD ["python", "main.py"]
