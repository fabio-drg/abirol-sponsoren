# User Journey: Registrierung bis zur ersten Reparaturanleitung

| # | Phase | Nutzeraktion | Systemreaktion | Bildschirm / Touchpoint | Datenpunkte |
|---|-------|--------------|-----------------|--------------------------|-------------|
| 1 | Onboarding | Öffnet App, wählt "Mit E-Mail" oder Apple/Google Sign-In | Legt `users`-Datensatz an, sendet Verifizierungs-Mail | Welcome-Screen | `email`, `auth_provider` |
| 2 | Fahrzeug erfassen | Gibt HSN/TSN ein (alternativ manuelle Auswahl Marke/Modell/Baujahr) oder scannt Fahrzeugschein per Kamera (OCR) | Löst Fahrzeug-Lookup gegen KBA-Referenzdaten aus, befüllt Marke/Modell/Motorisierung vor | "Fahrzeug hinzufügen"-Flow | `hsn`, `tsn`, `make`, `model`, `engine_code` |
| 3 | Kilometerstand & Baujahr | Bestätigt/korrigiert Kilometerstand, Erstzulassung | Legt `vehicles`-Datensatz + ersten `mileage_history`-Eintrag an | Formular | `current_mileage`, `first_registration_date` |
| 4 | Digital Twin erstellt | — | Erzeugt Dashboard-Kachel für das Fahrzeug, triggert asynchronen Erstabgleich gegen die Wissensdatenbank (RAG-Query nach Marke/Modell/Motorisierung/Kilometerstand) | Fahrzeug-Dashboard (leer, "Analyse läuft…") | — |
| 5 | Erste Warnungen | Erhält Push-Benachrichtigung "3 relevante Hinweise für dein Fahrzeug gefunden" | Schreibt Treffer als `vehicle_warnings` (Status `open`), sortiert nach Schweregrad × Kilometerstand-Nähe | Push + Dashboard-Badge | `issue_id`, `status=open` |
| 6 | Warnung öffnen | Tippt auf "Lenkung: erhöhter Verschleiß ab 150.000 km" | Zeigt Quellenbelege (Forenlinks, Anzahl Erwähnungen, Confidence-Score) und Handlungsoptionen (DIY-Anleitung anfordern / Werkstatt-Termin merken / Ignorieren) | Warnungs-Detailscreen | `vehicle_warnings.status → acknowledged` |
| 7 | DIY-Anleitung anfordern | Wählt Erfahrungslevel (Anfänger/Fortgeschritten), tippt "Anleitung erstellen" | Grounded-Generation-Call (RAG, siehe `03-architecture-rag.md`) erzeugt `repair_guides` + `guide_steps`; **1. kostenlose Anleitung im Freemium-Kontingent** | Ladeindikator → Anleitung-Screen | `skill_level`, `guide_id` |
| 8 | Anleitung erhalten | Liest Schritt-für-Schritt-Anleitung mit Zeitaufwand, Warnhinweisen | Zeigt zugehörige `guide_parts` (inkl. OEM-Nummer) und `guide_tools` an | Anleitung-Screen mit Tabs "Schritte / Teile / Werkzeug" | — |
| 9 | Smart Parts Matcher | Tippt auf benötigtes Teil | Live-Preisvergleich über Händler-APIs (AutoDoc, eBay, kfzteile24), gefiltert auf exakte OEM-Kompatibilität | Preisvergleichs-Modal | `part_offers` |
| 10 | Werkzeug-Check | Beantwortet "Hast du T20 Torx & 13er Nuss?" | Bei "Nein": schlägt Werkzeug-Bundle mit Affiliate-Link vor | Werkzeug-Finder-Modal | `user_tools` |
| 11 | Entscheidung | Wählt DIY (Teile bestellen) oder "In Werkstatt erledigen lassen" (Kostenschätzung übernehmen) | Legt bei Bestellung `expenses`-Eintrag (Kategorie `parts`) an; bei Werkstattwahl `budget_forecasts.status → fulfilled` | Checkout / Bestätigung | `expenses`, `budget_forecasts` |
| 12 | Zweite Anleitung (Paywall) | Fordert weitere KI-Anleitung an | Freemium-Limit erreicht → Upsell-Screen "Premium: 4,99 €/Monat oder 29,99 €/Jahr" mit Kosten-Nutzen-Rechner ("Diese Anleitung hätte in der Werkstatt X € gekostet") | Paywall-Screen | `subscription_tier` |
| 13 | Conversion | Schließt Abo ab | Setzt `subscription_tier=premium`, schaltet unlimitierte Anleitungen, proaktive Warnungen und Preisvergleich frei | In-App-Purchase / Store-Checkout | `subscription_expires_at` |

**Kernprinzip:** Der Zeitpunkt der Paywall liegt bewusst *nach* der ersten erlebten Werterfahrung (Schritt 7–11), nicht davor — der Nutzer sieht den Rechenwert (ersparte Werkstattkosten), bevor er zahlt.
