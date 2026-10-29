# Vorschlag: Audio in Kurspaketen (gesprochene Lektionen) und später Musik/Radio

Stand: 2026-10-29 · **Nur Vorschlag** – nichts davon ist umgesetzt. Jede Umsetzung braucht Bonys Freigabe.
Anlass: Kurs „Stricken lernen“ (Phaseone0815) soll gesprochene Lektionen bekommen (ElevenLabs-Stimme, siehe
`docs/coordination/STATUS.md`).

## 1. Ist-Stand (geprüft am Code)

| Punkt | Befund | Fundstelle |
|---|---|---|
| Erlaubte Dateiarten | nur `.md .txt .json .sh .py .png .jpg .jpeg .gif .webp .minisig` | `kurspaket.py` `ENDUNGEN` |
| Audiodatei im Paket | wird beim Entpacken, Kopieren und Packen **abgewiesen** („Unerlaubte Dateiart“) | `_zip_eintraege`, `_ordner_kopieren`, `packen` |
| Unbekannte Felder in `paket.json` | werden beim Laden übergangen (kein Fehler) | `paket_pruefen` |
| Kurspaket-Editor | schreibt Lektionen aus festen Feldern neu – ein unbekanntes Feld `audio` ginge beim Speichern **verloren** | `paket_json` |
| Format-Kennung | `format_version` 1, `min_version` steuert, ab welcher App-Version ein Paket läuft | `FORMAT_VERSION`, `MIN_VERSION` |
| Portal-Prüfbericht | liest nur Text-Dateien, Skripte und Bilder; kennt kein Audio | `kurspaket_portal.py` |
| Anleitungsfenster | zeigt Markdown (`QTextBrowser`), lädt nur Dateien aus dem Paket; Agent-PC ist optional (Knopf aus, wenn keiner da) | `gui/kurspaket_anleitung.py` |
| Wiedergabe | `PySide6.QtMultimedia` ist in der Build-Umgebung vorhanden (6.12.0), wird bisher nirgends genutzt | – |
| Größen | je Datei 25 MB, entpackt 200 MB, 2000 Dateien – reicht für Sprache | `MAX_DATEI`, `MAX_GESAMT` |

Folge: Audio ohne Formaterweiterung geht heute nicht. Ein Paket mit Audiodateien würde von **allen** bisherigen
Versionen (0.23–0.28.x) mit „Unerlaubte Dateiart“ abgewiesen – sicher, aber nicht freundlich.

## 2. Vorschlag Teil A: gesprochene Lektionen im Kurspaket

### A1 Format (rückwärtsverträglich, `format_version` bleibt 1)

```
lektionen/01-material/
    anleitung.md
    audio/01-einstieg.ogg          neu, optional
    audio/01-einstieg.md           Pflicht zu jeder Audiodatei: wortgleiches Transkript
```

`paket.json`, je Lektion optional:

```json
"audio": [
  {"datei": "audio/01-einstieg.ogg", "titel": "Einstieg: Was brauche ich?",
   "transkript": "audio/01-einstieg.md", "dauer_sekunden": 185}
]
```

- Neues Feld nur zusätzlich; `min_version` des Pakets wird auf die erste App-Version mit Audio gesetzt. Ältere Apps
  melden dann „braucht Bony's Agents X oder neuer“ statt „Unerlaubte Dateiart“ – **sofern** die Versionsprüfung vor der
  Dateiart-Prüfung greift. Das ist heute nicht so (ZIP-Prüfung kommt zuerst); für künftige Erweiterungen sollte
  `paket.json` beim Entpacken zuerst gelesen werden.
- Höchstens 10 Audiodateien je Lektion, je Datei 10 MB, Audio gesamt 100 MB.
- Pfade wie bei Skripten über `_relpfad` (innerhalb der Lektion, keine Links, kein `..`).

### A2 Dateiart und Prüfung (fremde Daten!)

- **Nur Ogg/Opus** (`.ogg`): offen, klein (Sprache mono 32–48 kbit/s ≈ 0,3 MB/Minute), gut unterstützt. MP3 erst bei
  Bedarf.
- Prüfung ohne Decoder: Kopf `OggS`, erste Seite enthält `OpusHead`, Größe im Rahmen, angegebene Dauer plausibel.
  Kein Auswerten von Metadaten-Texten (Vorbis-Kommentare werden ignoriert, nie angezeigt).
- Grund für die Strenge: Die Wiedergabe läuft über die Medienbibliothek von Qt (FFmpeg) – ein Parser für fremde
  Binärdaten ist eine Angriffsfläche. Darum nur ein Format, feste Kopfprüfung, kein Abspielen aus dem Internet.
- Geheimnisprüfung gilt für das Transkript (Text); die Audiodatei selbst lässt sich nicht automatisch prüfen.

### A3 Portal und Moderation

- Prüfbericht listet je Audiodatei: Pfad, Größe, Dauer, Transkript vorhanden ja/nein.
- Paket mit Audio ist mindestens **`needs_review`**: ein Mensch muss hören, ob Ton und Transkript übereinstimmen.
- Audio ohne Transkript → `rejected`.

### A4 Wiedergabe in der App

- Im Anleitungsfenster je Lektion eine schmale Leiste: ▶/⏸, Fortschritt, Lautstärke, Liste der Audiodateien,
  Knopf „Transkript zeigen“.
- **Nie automatisch abspielen.** Beim Wechsel der Lektion stoppt die Sprachausgabe (Sprache gehört zur Lektion).
- Datei nur per `QUrl.fromLocalFile` aus dem geprüften Paketordner; Pfad vorher wie bei Bildern auf „innerhalb des
  Pakets“ prüfen.
- Barrierefreiheit: Transkript ist immer sichtbar erreichbar; Audio ergänzt den Text, ersetzt ihn nicht.
- Kurs mit Gruppe: Audio läuft auf dem Rechner der Teilnehmenden (Kopfhörer im Ablaufplan erwähnen).

### A5 Editor und Werkzeuge

- Kurspaket-Editor muss `audio` lesen und wieder schreiben (sonst Datenverlust, siehe Ist-Stand).
- Erzeugen der Audiodateien bleibt **außerhalb** der App und des Pakets: lokales Werkzeug wie bei den Videos
  (Transkript → ElevenLabs → Lautheit angleichen, z. B. −16 LUFS → Opus mono). API-Schlüssel nie im Repository, im
  Paket oder im Bericht.

### A6 Rechte

- ElevenLabs: vor Veröffentlichung prüfen, ob der genutzte Tarif die kommerzielle Nutzung und Weitergabe der
  erzeugten Sprache erlaubt und ob eine Nennung nötig ist. In `paket.json` → `quellen` bzw. Handout vermerken.
- Lizenz des Pakets (`lizenz`) gilt auch für die Audiodateien – Einreichungsbedingungen entsprechend ergänzen.

### A7 Tests (bei Umsetzung)

- Laden: gültige `audio`-Einträge, fehlende Datei, fehlendes Transkript, falsche Endung, Pfad mit `..`, Link,
  zu groß, zu viele.
- Kopfprüfung: echtes Opus ok; umbenannte PNG/MP3/Zufallsdaten als `.ogg` abgewiesen.
- Entpacken/Packen/Kopieren mit `.ogg`; Editor-Rundweg erhält `audio`.
- Portal: Paket mit Audio → `needs_review`, ohne Transkript → `rejected`, Bericht ohne Metadaten-Texte.
- GUI (offscreen): kein Autoplay, Stopp beim Lektionswechsel, Transkript-Knopf.

## 3. Vorschlag Teil B (später): Musik oder Radio beim privaten Lernen

Gehört **nicht** ins Kurspaket-Format, sondern in die App – Pakete bringen keine Musik mit.

- Eigene, bewusst eingeschaltete Quelle im Anleitungsfenster bzw. Hauptfenster: lokale Dateien aus einem vom
  Nutzer gewählten Ordner oder eine vom Nutzer eingetragene `https://`-Stream-Adresse.
- Zunächst **keine** mitgelieferte Senderliste (Rechte, Verfügbarkeit, Datenschutz: der Sender sieht die IP-Adresse
  – Hinweis wie beim Community-Katalog).
- Keine automatische Wiedergabe; Lautstärke, Pause, Quellenwechsel; läuft über Lektionswechsel weiter.
- **Vorrang für den Kurs:** Spricht eine Lektion (Teil A), eine Prüfung oder ein Hilfe-Hinweis, wird die Musik
  leiser (Ducking) oder pausiert; danach geht sie weiter.
- Im Kursraum (Kursleitung, Gruppe) standardmäßig aus.
- Nutzt dieselbe Abspielkomponente wie Teil A – darum Teil A zuerst bauen.

## 4. Empfohlene Reihenfolge

1. Strickkurs-Entwurf ins Repository legen und mit dem bestehenden Validator prüfen (ohne Audio).
2. Bony entscheidet die offenen Punkte unten.
3. Teil A als eigener Block: Format + Prüfung + Tests → Portal/Bericht → Wiedergabe → Editor.
4. Audiodateien für den Strickkurs erzeugen und Probe hören (Bony).
5. Release mit neuer `min_version`; Strickkurs bekommt diese `min_version`.
6. Teil B frühestens danach.

## 5. Entscheidung erforderlich (Bony)

1. Nur Ogg/Opus – oder zusätzlich MP3?
2. Transkript als Pflicht zu jeder Audiodatei?
3. Pakete mit Audio im Portal immer `needs_review`?
4. Strickkurs mitgeliefert (macht `.deb`/Setup größer) oder nur über den Katalog?
5. ElevenLabs-Nutzungsrechte: wer klärt den Tarif?
6. Teil B (Musik/Radio) vorerst nur als Idee lassen?
