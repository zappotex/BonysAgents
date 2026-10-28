# Entwurf: Öffentlicher Katalog und Download (Schritt 5)

Stand: 28.10.2026
Status: **Entschieden 28.10.2026 und lokal umgesetzt (Bundle v3), noch nicht deployt.** Setzt Schritt 1–4 aus `plan-kursportal.md` voraus (Annahme läuft auf `kurse.bony23.de`).

## Ausgangslage im Code

Bony's Agents lädt Kurspakete schon aus einem Katalog: `kurspaket.katalog_laden()` liest eine `index.json`
(Format `bonys-agents-kurspaket-katalog`, nur HTTPS, höchstens 500 Einträge), `herunterladen()` prüft Größe und SHA-256,
entpackt in ein Prüfverzeichnis und vergleicht die Paket-ID. Der Katalog liegt heute im Repo
`zappotex/bonys-agents-kurspakete`. Ein Portal-Katalog muss **dasselbe Format** liefern, damit die App nichts Neues
lernen muss. Einträge brauchen: `id`, `name`, `version`, `stufe`, `beschreibung`, `dauer_minuten`, `datei`, `sha256`,
`groesse`.

## Vorschlag

1. **Veröffentlichen** (`approved → published`, weiterhin nur per menschlicher Entscheidung) schreibt zwei Dinge in ein
   getrenntes Volume `katalog_public`:
   - die Originaldatei als `pakete/<id>-<version>.bonyspaket` (unveränderlich, Dateiname aus geprüften Feldern)
   - eine neu erzeugte `index.json` nur aus **freigegebenen** Einreichungen, mit bereinigten Metadaten
2. **Rücknahme** (`published → withdrawn`) entfernt Datei und Eintrag; der Verlauf bleibt erhalten.
3. **Auslieferung:** Caddy liefert `/katalog/` schreibgeschützt aus `katalog_public` (nur GET, `nosniff`,
   `Content-Disposition: attachment`, kein Verzeichnislisting). Das `portal` schreibt dorthin, Caddy liest nur.
   Originale und Prüfberichte bleiben im nicht öffentlichen Volume `portal_data`.
4. **App:** `katalog_url()` bekommt eine zweite, **optionale** Quelle „Community-Kurspakete“. Einträge daraus sind
   deutlich als „Community, von der Moderation geprüft“ gekennzeichnet – nie als „Geprüftes Kurspaket von Bony's Agents“
   (`kurslauf.geprueft` bleibt den mitgelieferten Paketen vorbehalten). Skripte in Community-Paketen verlangen weiter die
   bestehende Rückfrage vor der Ausführung im Agent-PC.

## Sicherheitsregeln

- In den öffentlichen Katalog kommen nur Felder aus `paket.json` nach `_bereinigen`, kein Autor, keine Prüfberichte,
  keine Fundstellen.
- Der Download-Fingerabdruck (SHA-256) stammt aus der geprüften Einreichung; die Datei im Katalog wird beim
  Veröffentlichen nochmals gegen diese Summe geprüft.
- `index.json` wird atomar ersetzt (Temp-Datei, dann `replace`); fehlende oder kaputte Datei = leerer Katalog.
- Keine automatische Veröffentlichung, auch nicht bei `approved`.
- Kein Upload-Pfad und kein Schreibzugriff von außen auf `/katalog/`.

## Entscheidungen (Bony, 28.10.2026)

1. Ort: `kurse.bony23.de/katalog/`. 2. Community-Quelle in der App standardmäßig an. 3. Mitgelieferte Paket-IDs werden abgelehnt.
4. Neue Version ersetzt die alte im Katalog (ältere bleibt privat archiviert).

Ursprüngliche Fragen:

1. **Wo liegt der öffentliche Katalog?** (a) auf `kurse.bony23.de/katalog/` (einfach, eigene Domain wie bisher) oder
   (b) als Eintrag im bestehenden GitHub-Repo `bonys-agents-kurspakete` (ein Katalog, aber Moderation müsste dort
   committen).
2. **Sichtbarkeit in der App:** Community-Quelle standardmäßig an, aus (per Schalter) oder nur in der Kursleiter-Edition?
3. **Gleiche Paket-ID wie ein mitgeliefertes Paket:** immer ablehnen (Vorschlag) oder neue Fassung erlauben?
4. **Update-Regel:** Darf eine neue Version derselben Paket-ID die alte ersetzen, oder bleiben Versionen nebeneinander?

## Umsetzung (nach Freigabe)

1. `kurspaket_katalog.py`: Katalog aus freigegebenen Einreichungen erzeugen und schreiben (rein lokal, mit Tests).
2. `portal_server.py`: Befehle `veroeffentlichen` / `zurueckziehen` über die Moderation, schreiben ins Katalog-Volume.
3. Caddyfile/Compose: Volume `katalog_public`, Route `/katalog/`.
4. App: zweite Katalogquelle mit Kennzeichnung.
5. Bundle v3, Deploy durch Bony, echter Test (Veröffentlichen, Laden in der App, Rücknahme).

## Veröffentlichungsschranke

Gilt unverändert: Erst nach ausdrücklicher Freigabe durch Bony (realer Test, Sicherheitsprüfung) wird etwas
öffentlich geschaltet. Dieser Entwurf aktiviert nichts.

## Stand der Umsetzung

- Erledigt: `kurspaket_katalog.py` (Index + Dateien, nur `published`, neueste Version, Prüfsumme gegen Original), reservierte IDs
  (`reservierte_ids.json` beim Bundle-Bau), Server-Befehl `katalog`, `entscheiden` gleicht den Katalog ab, Compose-Volume
  `katalog_public`, Caddy-Route `/katalog/`.
- Offen: App-Seite (zweite Katalogquelle mit Kennzeichnung „Community“), Deploy und echter Test durch Bony.
