# GearTwin AI — Konzept & Prototyp

Prädiktiver digitaler Zwilling für Gebrauchtwagen. Dieses Verzeichnis enthält das
Produkt- und Systemkonzept sowie einen lauffähigen Backend-Prototyp.

## Inhalt

- [`concept/01-user-journey.md`](concept/01-user-journey.md) — User Journey von der Registrierung bis zur ersten Reparaturanleitung
- [`concept/02-data-model.md`](concept/02-data-model.md) — Datenmodell (ER-Übersicht, siehe `backend/schema.sql` für die DDL)
- [`concept/03-architecture-rag.md`](concept/03-architecture-rag.md) — Systemarchitektur der RAG-Pipeline (Forendaten → halluzinationsfreie Antworten)
- [`concept/04-budget-and-parts-modules.md`](concept/04-budget-and-parts-modules.md) — Vertiefung: Prädiktiver Budget-Tracker & Smart Parts Matcher

## Code-Prototyp (`backend/`)

- `schema.sql` — vollständiges PostgreSQL-Schema
- `vehicle_api.py` — FastAPI-Endpunkte für den Fahrzeug-Digital-Twin und das prädiktive Warnsystem (RAG-Retrieval als austauschbarer Stub)
- `budget_tracker.py` — FastAPI-Endpunkt, der einen CSV-Kontoauszug einliest, Auto-Ausgaben per Regex kategorisiert und ein prädiktives Wartungsbudget je nach Fahrzeugmodell berechnet
- `sample_transactions.csv` — Beispiel-Kontoauszug zum Testen

### Lokal starten

```bash
cd geartwin-ai/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn vehicle_api:app --reload --port 8000
# in einem zweiten Terminal:
uvicorn budget_tracker:app --reload --port 8001
```

Beispiel-Request für den Budget-Tracker:

```bash
curl -X POST "http://localhost:8001/budget/analyze?make=VW&model=Polo%20IV&mileage=148000&monthly_mileage=900" \
  -F "file=@sample_transactions.csv"
```
