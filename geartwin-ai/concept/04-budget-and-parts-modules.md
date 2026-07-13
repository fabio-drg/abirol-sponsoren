# Vertiefung: Prädiktiver Budget-Tracker & Smart Parts Matcher

## Modul 1: Prädiktiver Budget-Tracker

### Automatisierte Kategorisierung
Zwei Eingangskanäle, ein gemeinsames Zielschema (`expenses`, siehe Datenmodell):

1. **OCR-Import (Tankbeleg-Foto):** Beleg wird per OCR erfasst, Betrag + Händlername
   extrahiert. Händlername gegen eine Tankstellen-Whitelist gematcht → `category=fuel`.
2. **CSV-Import (Kontoauszug):** Verwendungszweck-Feld wird gegen ein Regex-Set
   pro Kategorie geprüft (siehe `backend/budget_tracker.py`, Funktion
   `categorize_transaction`). Reicht die Regex-Erkennung nicht (uneindeutiger
   Verwendungszweck), wird optional ein LLM-Klassifikations-Call mit den fünf
   Zielkategorien als geschlossenem Label-Set nachgeschaltet (kein Freitext,
   damit die Kategorie immer valide bleibt).

Ergebnis: monatliche Ist-Ausgaben je Kategorie (`fuel`, `maintenance`, `insurance`,
`tax`, `parts`, `other`) als Baseline für die Prognose.

### Algorithmus "Rücklagen-Vorschau"
Eingaben: `vehicle` (make, model, engine_code, current_mileage), historische
`mileage_history`-Einträge (→ durchschnittliche monatliche Fahrleistung), gefilterte
`knowledge_base_issues` für dieses Modell.

```
1. monthly_mileage = (letzter Kilometerstand − vorletzter Kilometerstand)
                      / Monate dazwischen
                      (Fallback: Nutzer-Schätzung, falls < 2 Messpunkte vorhanden)

2. FOR jedes issue IN knowledge_base_issues WHERE make/model matcht:
       km_bis_issue = issue.typical_mileage_from − vehicle.current_mileage
       IF km_bis_issue <= 0:
           # Fenster hat bereits begonnen → sofort relevant, hohe Prioritaet
           monate_bis_faellig = 0
       ELSE:
           monate_bis_faellig = km_bis_issue / monthly_mileage

       IF monate_bis_faellig <= HORIZON_MONATE (default 6):
           reserve_monatlich = issue.avg_cost_workshop_eur
                                / max(monate_bis_faellig, 1)
           EMIT budget_forecast(issue, monate_bis_faellig, reserve_monatlich)

3. Sortiere Ergebnisse nach monate_bis_faellig (dringendste zuerst)
```

Die Kernidee: **Kilometerstand-Fenster aus der Wissensdatenbank werden über die
individuelle Fahrleistung des Nutzers in eine Zeitachse übersetzt.** Das macht aus
einer abstrakten Aussage ("ab 150.000 km") eine konkrete, handlungsleitende Aussage
("in 6 Monaten, lege jetzt 15 €/Monat zurück").

Reifen sind ein Sonderfall desselben Prinzips: statt eines Kilometerstand-Fensters
aus der Wissensdatenbank wird die verbleibende Profiltiefe (Nutzereingabe oder
Werkstatt-Messung) durch den durchschnittlichen Abrieb pro 1.000 km geteilt, um den
Fälligkeitsmonat zu bestimmen; die Reifendimension (`vehicles`-Metadaten) bestimmt
den Preis-Lookup beim Parts Matcher.

### Referenz-Implementierung
Siehe [`backend/budget_tracker.py`](../backend/budget_tracker.py) — FastAPI-Endpoint
`POST /budget/analyze`, der einen CSV-Kontoauszug einliest, Ausgaben kategorisiert
und daraus + einer kleinen Modell-Wissensbasis eine Rücklagen-Vorschau berechnet.

---

## Modul 2: Smart Parts Matcher

### OEM-Kompatibilitäts-Check
Jedes verbaute Referenzteil des digitalen Zwillings ist über `guide_parts` bzw.
direkt über die Fahrzeugkonfiguration mit einer `parts.oem_number` verknüpft.
Beim Preisvergleich läuft der Abgleich in zwei Stufen:

1. **Exakter OEM-Match:** Händler-APIs (AutoDoc, eBay Motors, kfzteile24) werden
   primär über die OEM-Nummer abgefragt, nicht über Freitextsuche — eliminiert
   Fehlkäufe durch generische Produktbezeichnungen.
2. **Fallback Fahrzeug-Kompatibilitätsfilter:** Liefert ein Händler keine
   OEM-Suche, wird stattdessen über `compatible_makes`/`compatible_models` +
   HSN/TSN gefiltert, und Treffer werden mit einem sichtbaren
   Kompatibilitäts-Badge ("passt zu deinem Fahrzeug lt. HSN/TSN-Abgleich")
   versehen statt stillschweigend als sicher angezeigt.

Ergebnisse aller Händler werden in `part_offers` normalisiert (Preis, Vendor, URL,
`fetched_at`) und nach Preis aufsteigend sortiert; `fetched_at` steuert einen
Cache-Refresh (Preise sind kein Echtzeit-Stream, sondern periodisch aktualisiert,
z. B. alle 6–12 Stunden für aktive Guides).

### Werkzeug-Finder-Logik
Jede `repair_guides`-Instanz referenziert über `guide_tools` die benötigten
Werkzeuge mit einem `required`-Flag (Pflicht vs. "nice to have"). Beim Aufruf der
Anleitung:

```
benoetigt = guide_tools WHERE guide_id = X AND required = true
vorhanden = user_tools WHERE user_id = Y
fehlend   = benoetigt − vorhanden

IF fehlend ist nicht leer:
    zeige Werkzeug-Checkliste mit fehlenden Items
    schlage Bundle-Angebot vor (Ersatzteil + fehlendes Werkzeug im selben
    Warenkorb, ein Affiliate-Link → höhere Provision durch höheren Warenkorbwert)
ELSE:
    zeige nur "Alles vorhanden ✓", kein Werkzeug-Upsell
```

Der Schwierigkeitsgrad der Anleitung (`repair_guides.skill_level`, vom LLM anhand
Schrittanzahl/Fachbegriffen geschätzt) wird zusätzlich gegen `users.diy_skill_level`
gespiegelt: bei Mismatch (Anfänger + Anleitung mit Schwierigkeit "advanced") erhält
der Nutzer einen Warnhinweis mit Empfehlung "Werkstatt statt DIY" statt nur die
Anleitung stumm anzuzeigen.
