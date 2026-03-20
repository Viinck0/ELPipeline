# Rick & Morty EL Pipeline - Docker Image
# Minimalní image pro spuštění ETL pipeline

FROM python:3.12-slim

# Nastavení pracovního adresáře
WORKDIR /app

# Instalace závislostí
COPY requirements.txt .
RUN pip install --no-cache-dir --root-user-action=ignore -r requirements.txt

# Kopírování zdrojových souborů
COPY main.py .
COPY extractor.py .
COPY validator.py .
COPY loader.py .

# Vytvoření adresáře pro data (database, logy)
RUN mkdir -p /app/data

# Nastavení proměnných prostředí
ENV PYTHONUNBUFFERED=1
ENV DB_PATH=/app/data/rick_and_morty.db
ENV LOG_FILE=/app/data/el_pipeline.log

# Spuštění aplikace
CMD ["python", "main.py"]
