# Systemarchitektur: Halluzinationsfreies RAG über Forenwissen

Ziel: Aus unstrukturierten Foren-/Rückruf-/TÜV-Daten zuverlässige, belegbare
Aussagen wie *"Bei diesem Modell fällt Sensor X ab ~150.000 km häufig aus"*
erzeugen — ohne dass die KI plausibel klingende, aber falsche Fakten (Teilenummern,
Kilometerstände) erfindet.

```
 ┌──────────────┐   ┌───────────────┐   ┌───────────────────┐   ┌──────────────┐
 │ 1. Ingestion │ → │ 2. Extraction │ → │ 3. Embedding/Index │ → │ 4. Retrieval │ → 5. Grounded
 │  (Crawler)   │   │  (LLM-Batch)  │   │  (pgvector)        │   │  (Hybrid)    │    Generation
 └──────────────┘   └───────────────┘   └───────────────────┘   └──────────────┘   → 6. Guardrails
```

### 1. Ingestion (Datenerfassung)
Quellen: Motor-Talk-Threads, relevante Reddit-Subs, KBA-Rückrufdatenbank, TÜV-Report-PDFs,
Hersteller-TSBs (Technical Service Bulletins). Ausschließlich Quellen mit erlaubtem
Zugriff (robots.txt-konform bzw. offizielle APIs); `forum_scrape_sources.robots_txt_compliant`
wird pro Quelle geprüft und geloggt. Rate-Limiting pro Domain, inkrementelles Crawling
(nur neue/geänderte Threads seit `last_crawled_at`).

### 2. Extraction & Structuring (LLM-Batch-Pass)
Rohe Threads werden gechunkt (pro Post/Antwortabschnitt, 500–800 Tokens) und mit
Metadaten versehen (Marke, Modell, erwähnter Kilometerstand, Datum, Upvotes/Zustimmung
als Signal). Ein separater, güngstiger LLM-Batch-Call (niedrige Temperatur, striktes
JSON-Schema als Output) extrahiert **Issue-Kandidaten**:

```json
{
  "make": "Volkswagen", "model": "Polo IV", "engine_code": "AZQ",
  "issue_title": "Lenkschloss hakt / blockiert",
  "typical_mileage_from": 120000, "typical_mileage_to": 170000,
  "severity": "warning", "evidence_quote": "…", "source_url": "…"
}
```

**Deduplizierung:** Neue Kandidaten werden per Embedding-Ähnlichkeit (Cosine-Similarity
auf `issue_title` + Beschreibung) gegen bestehende `knowledge_base_issues`-Einträge
für dasselbe Modell abgeglichen. Bei Treffer (Similarity > 0.85) wird `mention_count`
inkrementiert und der Mittelwert der Kilometerstand-/Kostenangaben aktualisiert statt
eines Duplikats.

### 3. Embedding & Indexierung
Für jeden strukturierten Issue-Eintrag *und* für die zugrundeliegenden Rohtext-Chunks
werden Embeddings erzeugt und in `pgvector` gespeichert (Spalte `embedding` in
`knowledge_base_issues`, siehe `schema.sql`). Partitionierung/Filterung primär über
den `(make, model)`-Index, Vektor-Suche dient nur der Verfeinerung innerhalb dieser
Vorfilterung — kein Full-Table-Scan über alle Modelle.

### 4. Retrieval bei Nutzeranfrage (Hybrid)
Anfrage-Kontext = Fahrzeugdaten (Marke, Modell, Motorcode, aktueller Kilometerstand)
+ optionale Freitextfrage des Nutzers.

1. **Strukturierter Pre-Filter (SQL):** `WHERE make = ? AND model = ? AND
   typical_mileage_from <= current_mileage + 15000 AND typical_mileage_to >=
   current_mileage - 10000` — liefert die relevanten Issue-Kandidaten deterministisch.
2. **Vektor-Suche:** nur innerhalb der vorgefilterten Menge (bzw. bei Freitextfragen
   ohne exakten Mileage-Match) zur semantischen Ergänzung.
3. **Re-Ranking:** Cross-Encoder bewertet Top-K nach Relevanz zur konkreten Nutzerfrage;
   `confidence_score` und `mention_count` fließen als zusätzliche Gewichtung ein.

### 5. Grounded Generation
Das Antwort-LLM erhält **ausschließlich** die durch Retrieval gelieferten,
strukturierten Snippets als Kontext — nicht das offene Web. Der System-Prompt
erzwingt:
- Jede Tatsachenbehauptung muss einem übergebenen Snippet zuordenbar sein
  (Zitat-Referenz `[source_id]`).
- Bei fehlender Evidenz: explizite Formulierung *"Für dein Modell liegen dazu keine
  ausreichenden Daten vor"* statt Spekulation.
- Teilenummern/OEM-Angaben werden **nie frei generiert**, sondern ausschließlich aus
  der `parts`-Tabelle referenziert (Tool-Call statt Freitext).

### 6. Halluzinations-Guardrails (Post-Generation)
- **Faktencheck-Pass:** Ein zweiter, günstiger LLM-Call (oder Regel-basiert) prüft,
  ob jede genannte Teilenummer/Kilometerangabe in den übergebenen Snippets vorkommt.
  Bei Abweichung: Regeneration mit verschärftem Prompt oder Fallback auf
  Template-Antwort ("Kontaktiere eine Fachwerkstatt zur genauen Diagnose").
- **Nutzer-Feedback-Loop:** Daumen-hoch/-runter auf Anleitungen und Warnungen fließt
  zurück in `confidence_score` der zugrundeliegenden `knowledge_base_issues` — echtes
  Reinforcement über Nutzersignale statt nur Foren-Upvotes.
- **Caching:** Antworten werden pro `(make, model, engine_code, mileage_bucket)`
  gecacht (z. B. Redis, Bucket-Größe 10.000 km), da viele Nutzer mit demselben Modell
  ähnliche Anfragen stellen — reduziert LLM-Kosten erheblich und erhöht Konsistenz.
  Cache-Invalidierung bei neuen Scrape-Ergebnissen für das betroffene Modell.

### Kostenkontrolle
Die teuren Schritte (2: Extraction, 5: Generation) laufen batched/asynchron bzw.
gecacht — der Live-Pfad bei einer Nutzeranfrage ist im Idealfall nur Schritt 4
(SQL + Vektor-Suche, Millisekunden) plus ein gecachter oder sehr kurzer Generation-Call.
