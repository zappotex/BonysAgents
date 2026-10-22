**Ablauf:** 2 Minuten erklären, 13 Minuten selbst arbeiten, 5 Minuten zusammentragen.

**Lösung / Erwartung:**

1. Beschlüsse: Mitgliedsbeitrag bleibt bei **36 EUR** im Jahr, Sommerfest am **4. Juli**, eine **Regentonne** für den
   Gemeinschaftsgarten. Alle einstimmig.
2. `protokoll-gerade.pdf`: Seite 2 um 90° (bzw. −90°) zurückgedreht. Manche Modelle drehen in die falsche Richtung –
   dann steht die Seite auf dem Kopf. Guter Anlass für „selbst prüfen“.
3. `rechnungen-gesamt.pdf` mit zwei Seiten: Rechnung 2026-031 (März), dann 2026-042 (April).
4. Für Schnelle: 48,50 + 41,90 = **90,40 EUR**.

**Stolperstellen:**

- Hermes nimmt statt PdfCraft das Terminal (`pdftotext`, Python): ausdrücklich „Benutze PdfCraft“ sagen; ist PdfCraft
  nicht sichtbar, wurde Hermes nach `hermes mcp add` nicht neu gestartet (`/reload-mcp`).
- „Zugriff verweigert“ oder Datei nicht gefunden: PdfCraft darf nur in `~/Agent-Dateien/pdf` arbeiten. Dateien
  außerhalb erst dorthin kopieren.
- Kostenloses Modell überlastet („Rate limit“): kurz warten oder mit `/model` wechseln.

Die Prüfung schaut mit `pdfinfo` und `pdftotext`, ob `rechnungen-gesamt.pdf` genau zwei Seiten hat und beide
Rechnungsnummern enthält.
