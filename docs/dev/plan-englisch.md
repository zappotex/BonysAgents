# Plan: Bony's Agents auf Englisch (englische Oberfläche und Inhalte)

Stand: 2026-10-29 · **Plan mit Bonys Entscheidungen (Abschnitt 5)**. Umgesetzt: Phasen 0–4 und der Teil von Phase 5 in diesem Repository (nicht committet). Jede Phase braucht Bonys Freigabe.
Anlass: In `CLAUDE.md` steht unter „Geplante nächste Themen“ die „spätere englische Erweiterung“. Bisher gab es
dazu keinen Plan (Bony, 29.10.2026: „ja schreib den plan und trag es in den fahrplan“).

## 1. Ist-Stand (geprüft am Code)

| Punkt | Befund | Fundstelle |
|---|---|---|
| Texte der App | fest auf Deutsch im Quelltext, kein Übersetzungsmechanismus | `src/bonys_agents/**` |
| Umfang (grob gezählt) | ca. 1.000 Textstellen in der Oberfläche (30 Dateien), ca. 2.200 Zeichenketten mit Wörtern im Kern (49 Dateien, davon ein Teil Skripte für den Agent-PC und Protokolltexte, die nicht übersetzt werden) | `gui/*.py`, `*.py` |
| Größte Dateien | `main_window.py` 1.854 Zeilen, `template_dialogs.py` 937, `kurspaket_anleitung.py` 772, `create_dialog.py` 751 | `gui/` |
| Qt-eigene Texte | deutsche Qt-Übersetzung wird geladen (`QTranslator`, aus der Durchsicht U-03) | `gui/app.py` |
| Fehlermeldungen | Ausnahmen im Kern tragen deutsche Sätze, die die Oberfläche direkt anzeigt | z. B. `kurspaket.py`, `vm.py` |
| Agent-PC | Locale ist schon wählbar (`locale`, Standard `de_DE.UTF-8`), Schreibtischordner „Schreibtisch“/„Desktop“ richtet sich danach | `cloudinit.py` |
| Kurspakete | Feld `sprache` gibt es schon (Standard `de`, wird geprüft) | `kurspaket.py` |
| Handbücher | Deutsch, ca. 13.000 Wörter (Benutzer 7.900, Kursleiter 4.200), daraus PDFs | `docs/handbuch/` |
| Tests | viele Tests prüfen deutsche Meldungstexte | `tests/` |
| **Vorbild Bony's VPN** | `tr("deutscher Text")` mit Wörterbuch `EN = {…}` (ca. 210 Einträge), Sprache aus `LANGUAGE`/`LC_ALL`/`LANG`, Deutsch bei `de*`, sonst Englisch | `bonys-vpn/src/bonys_vpn/model.py` |

Fazit: Das VPN-Verfahren hat sich bewährt und passt zur Art, wie hier Code geschrieben wird. Für etwa
15-mal so viele Texte braucht es aber eine eigene Katalogdatei, ein Werkzeug zum Einsammeln der Texte und eine
Prüfung, die fehlende Übersetzungen findet.

## 2. Vorschlag: Aufbau

### 2.1 Grundgerüst (wie Bony's VPN, nur größer)

- Neues Modul `src/bonys_agents/i18n.py` mit `tr(text, **kw)`. Schlüssel ist der deutsche Text, die deutsche
  Fassung bleibt also unverändert im Code und gut lesbar.
- Englischer Katalog als Datei `src/bonys_agents/resources/i18n/en.json`, nicht als Wörterbuch im Code.
- Sprache:
  1. Einstellung in der App („Sprache: Automatisch / Deutsch / English“), wirkt nach einem Neustart.
  2. Bei „Automatisch“: Systemsprache (`QLocale` bzw. Umgebungsvariablen wie im VPN). Deutsch bei `de*`, sonst
     Englisch.
- Qt-eigene Texte: `qtbase_de` bzw. die englischen Standardtexte passend zur gewählten Sprache.
- Fehlende Übersetzung: Der deutsche Text erscheint, die App stürzt nicht ab.
- Texte, die im Code deutsch bleiben müssen (Zustände wie „läuft“, die auch als Schlüssel dienen, Konstanten,
  Beschreibungen in Datenklassen), markiert `n_("…")`; übersetzt wird beim Anzeigen mit `tr(variable)`
  (seit Phase 1).

### 2.2 Werkzeuge und Prüfung

- `tools/i18n_sammeln.py` sucht alle `tr("…")`-Aufrufe (per `ast`) und ergänzt neue Schlüssel in `en.json`
  (leer = noch offen).
- Test `tests/test_i18n.py`:
  - Jeder `tr()`-Text hat einen englischen Eintrag.
  - Die Platzhalter `{name}` stimmen in beiden Sprachen überein.
  - Es gibt keine verwaisten Einträge.
- Ein Test öffnet die Hauptfenster einmal auf Englisch (offscreen). So fallen Texte auf, die nicht in `tr()`
  stehen oder zu lang sind.
- Die bestehenden Tests laufen weiter auf Deutsch (Sprache in den Tests fest auf `de`), damit sich die deutschen
  Meldungstexte nicht ändern.

### 2.3 Regeln für Texte

- Keine Sätze aus Bruchstücken zusammensetzen („Agent-PC “ + name + „ gestartet“), sondern ganze Sätze mit
  Platzhaltern: `tr("Agent-PC „{name}“ gestartet", name=…)`.
- Mehrzahl über zwei Schlüssel („1 Datei“ / „{n} Dateien“), kein eigenes Pluralsystem.
- Zahlen, Datum und Größen über eine Formatierfunktion wie `fmt_bytes` im VPN.
- Fehler im Kern: Ausnahmen bekommen den deutschen Text als Schlüssel. Übersetzt wird beim Anzeigen, die
  Protokolldateien bleiben deutsch.
- Server (Bony-Netz, Kursportal): Antworten mit festen Codes, die App übersetzt sie. Am Serverprotokoll ändert
  sich dadurch nichts.

### 2.4 Agent-PC auf Englisch

- Beim Anlegen „Sprache des Agent-PCs“ anbieten. Standard ist die Sprache der App, gesetzt wird `en_US.UTF-8`
  und eine passende Tastatur.
- Starter auf dem Schreibtisch, Hermes-Begrüßung und Systemtext, Hilfe-Texte im Agent-PC: je Sprache.
- Bestehende Agent-PCs bleiben, wie sie sind.
- **Umgesetzt (Phase 3):** „Sprache des Agent-PCs“ im Anlegen-Dialog, `create --sprache`, `vm.create(sprache=)`,
  Kurspakete über ihr Feld `sprache`. Beim Anlegen steht die Sprache fest (`AGENT_LANG` im Einrichtungsskript);
  Nachinstallieren liest sie aus `/etc/default/locale` im Agent-PC (`cloudinit.GUEST_LANG`), so passen auch Klone
  und alte Agent-PCs. Starter mit `Name`/`Comment` englisch und `[de]` deutsch. Eine eigene Hermes-Begrüßung oder
  einen eigenen Systemtext gibt es nicht – Hermes ist ab Werk englisch; eingestellt werden Spracheingabe und Stimme.
- **Noch deutsch im Agent-PC:** die Seite „Agenten-Apps“ (Inhalt aus `agent-apps/agent-apps.yaml`, mit der
  Online-Fassung zusammen in Phase 5) samt Ordner `~/Agent-Dateien`, Meldungen im Einrichtungsprotokoll.

### 2.5 Inhalte

- Handbücher Benutzer und Kursleiter auf Englisch (eigene Dateien `docs/handbuch/en/`, eigene PDFs).
- README auf Englisch (für GitHub wichtig).
- **Umgesetzt (Phase 4):** `docs/handbuch/en/user-guide.md` und `trainer-guide.md` (vollständige Übersetzungen),
  PDFs `BonysAgents-User-Guide-…`/`-Trainer-Guide-…`, Bilder `bilder/en/` (Oberfläche englisch) und
  die von Hand gemachten Bilder aus `bilder/eigene/` für beide Sprachen (Bony), Vorlage nach `-M sprache=en`, App-Link nach Sprache.
  `README.en.md` ist eine **kompakte** englische README (Überblick, Installation, Benutzung, CLI, Datenschutz,
  Lizenz) mit Verweis auf die ausführliche deutsche – eine vollständige Übersetzung nur auf Wunsch.
  Nachgezogen aus Phase 2: Kursraum-Seite (`tr()` in `kursraum.js`, `data-tr` in `index.html`, Texte über
  `texte.js` aus dem Katalog), Schritt-Titel der Einrichtung (`cloudinit.schritt_titel`), „Persönliche Daten“,
  Editor-Gliederung, Prüfspalte.
- **Noch deutsch:** die Browser-Seiten der Kursleiter-Version (Vorführung `trainer/resources/present/`, Hilfe-Ansicht
  `trainer/resources/hilfe/`, Seiten des Freigabe-Servers), Meldungen der Server (Zentrale, z. B. „Der Kurs ist
  voll“ – Plan: feste Codes), Schriftzug im Hintergrundbild, Seite „Agenten-Apps“, mitgelieferte Kurspakete.
- Kurspakete: alle mitgelieferten Pakete auf Deutsch **und** Englisch (Bony, 29.10.2026). Je Sprache ein
  eigenes Paket (`sprache` `de`/`en`). Bibliothek und Katalog zeigen zuerst die Pakete in der Sprache der App.
  **Entschieden (Bony, 29.10.2026, Phase 5):** englische Fassung = deutsche ID + „-en“ (z. B.
  `einfuehrung-hermes-agent-en`, kein Zusatzfeld); die Bibliothek zeigt nur die Fassung in der Sprache der App, die
  andere über „Alle Sprachen“ – Pakete, die es nur in einer Sprache gibt, immer. Reihenfolge: erst Code (Browser-Seiten
  der Kursleiter-Version, Bibliothek), dann Inhalte (4 fertige Pakete, Entwürfe, Agenten-Apps), danach Mission
  Control, Zentrale und Webseiten als eigene Blöcke.
- **Umgesetzt (Phase 5, dieses Repository):** englische Fassungen aller 9 mitgelieferten Kurspakete
  (`kurspakete/*-en`, Test `test_englische_fassungen_passen_zur_deutschen` verlangt gleichen Aufbau), Bibliothek und
  Katalog nach Sprache (`kurspaket.nach_sprache`, Schalter „Alle Sprachen“), `sprache` im Katalog und Prüfbericht,
  Editor-PDFs nach Paketsprache, Agenten-Apps englisch (`agent-apps/agent-apps.en.yaml` nur Texte, Befehle aus der
  Liste, `~/Agent-Files`; online `/agenten-apps/en/`), Browser-Seiten der Kursleiter-Version (Sprache des Browsers),
  Server-Fehler nach `Accept-Language`. Englische Übungsordner: `~/Course`, `~/Agent-Files`; englische Feeds im
  n8n-Kurs (BBC, Ars Technica, Guardian, NPR).
- Getrennte Projekte, jeweils eigener Block: Mission Control (`lang="de"` im `index.html`), Bony's VPN (ist schon
  zweisprachig), Schulungsseite und Kursportal-Seiten (deployt Bony).

## 3. Phasen und grober Aufwand

| Phase | Inhalt | Aufwand |
|---|---|---|
| 0 | Grundgerüst: `i18n.py`, Katalog, Sprachwahl, Sammelwerkzeug, Tests | klein (1 Sitzung) |
| 1 | Hauptfenster, Anlegen-Dialog, Statusleiste, häufige Meldungen | mittel (1–2 Sitzungen) |
| 2 | Restliche Dialoge (Kurse, Kurspakete, Editor, Bony-Netz, Kursraum, Musik), Fehlermeldungen aus dem Kern, CLI | groß (3–5 Sitzungen) |
| 3 | Agent-PC auf Englisch (Locale, Starter, Hermes-Texte), echter Test mit neuem Agent-PC | mittel (1–2 Sitzungen) |
| 4 | Handbücher und README auf Englisch, PDFs | mittel (1–2 Sitzungen) |
| 5 | Kurspakete nach Sprache, alle mitgelieferten Pakete auch auf Englisch; Mission Control und Webseiten | mittel bis groß |

Nach Phase 2 ist die App vollständig englisch bedienbar. Das erste englische Release kommt nach Phase 3 (Bony: App
und Agent-PC zusammen), Phasen 4–5 folgen bis Version 1.0.

Die Übersetzung schreibt Claude. Gegengelesen wird von Claude in einem eigenen Durchgang oder von einer anderen KI
(Bony, 29.10.2026).

## 4. Risiken

- **Viele kleine Änderungen in vielen Dateien:** Jede Textstelle bekommt `tr()`. Das Risiko liegt weniger in der
  Logik als darin, Stellen zu übersehen. Dagegen helfen das Sammelwerkzeug und der Englisch-Test der Fenster.
- **Längere Texte:** Englische Texte sind meist kürzer, einzelne Knöpfe können sich trotzdem verschieben. Das zeigt
  der Layout-Test (`tests/test_gui_layout.py`) auf Englisch.
- **Zusammengesetzte Sätze** im Bestand müssen umgebaut werden, das ist der größte Handaufwand in Phase 2.
- **Gemischte Sprache** während der Umstellung: Bis Phase 2 fertig ist, sollte es kein Release mit englischer
  Auswahl geben (die Einstellung bleibt bis dahin verborgen).
- **Pflege:** Jeder neue Text braucht künftig eine englische Fassung, der Test erzwingt das. Das macht jede künftige
  Änderung ein wenig aufwendiger.
- **Baustein `bony_netz`** ist in Agents und VPN dateigleich. Seine Texte müssen in beiden Projekten auf dieselbe
  Weise übersetzt werden.

## 5. Entscheidungen (Bony, 29.10.2026)

Wortlaut: „vor 1.0 2 zum umstellen 3 beides 4 du oder andere ki die kuspakete englisch und deutsch 6 evtl“

1. **Zeitpunkt:** vor Version 1.0.
2. **Sprachwahl:** automatisch nach System, in der App umstellbar.
3. **Erstes englisches Release:** App und Agent-PC auf Englisch (Phasen 0–3).
4. **Gegenlesen:** Claude oder eine andere KI.
5. **Kurspakete:** auf Deutsch und Englisch.
6. **Weitere Sprachen:** eventuell später. Das Grundgerüst lässt das ohne Umbau zu.
