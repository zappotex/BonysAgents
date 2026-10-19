# Handbücher

Quelltext der Handbücher von Bony's Agents. Die PDFs entstehen daraus mit `erstellen.sh` und hängen an jedem
Release (`.github/workflows/release.yml`, Job `handbuch`) – im Repository liegen sie nicht.

| Datei | PDF |
|---|---|
| [benutzer.md](benutzer.md) | `BonysAgents-Benutzerhandbuch-<Version>.pdf` |
| [kursleiter.md](kursleiter.md) | `BonysAgents-Kursleiter-Handbuch-<Version>.pdf` |
| [ablaufplan.md](../../kurspakete/einfuehrung-hermes-agent/ablaufplan.md) (Kurspaket) | `BonysAgents-Beispielkurs-Hermes-Kursleitung-<Version>.pdf` |
| [handout.md](../../kurspakete/einfuehrung-hermes-agent/handout.md) (Kurspaket) | `BonysAgents-Beispielkurs-Hermes-Handout-<Version>.pdf` |

Der Beispielkurs hat **eine** Quelle: das mitgelieferte Kurspaket `kurspakete/einfuehrung-hermes-agent/`. Ablaufplan
und Handout dort ändern – `erstellen.sh` baut die PDFs von dort.

Lizenz der Handbücher: **CC BY-SA 4.0** (Name und Logo ausgenommen, siehe letzte Seite der PDFs).

## Erstellen

```bash
docs/handbuch/erstellen.sh               # Bildschirmfotos neu aufnehmen, prüfen, alle vier PDFs
docs/handbuch/erstellen.sh --ohne-bilder # nur PDFs (mit den Bildern aus bilder/)
docs/handbuch/erstellen.sh --nur-bilder  # nur Bildschirmfotos
```

Die PDFs landen in `docs/handbuch/pdf/`. Version und Datum kommen automatisch aus
`src/bonys_agents/__init__.py` bzw. dem letzten Commit.

**Werkzeuge** (frei, Linux):

- [Pandoc](https://github.com/jgm/pandoc/releases) und [Typst](https://github.com/typst/typst/releases)
  – je eine Datei, z. B. nach `~/.local/bin`. Getestet mit Pandoc 3.12.1 und Typst 0.15.1 (wie in der
  Release-Aktion); das Pandoc aus Mint 22/Ubuntu 24.04 (3.1) ist zu alt.
- Für die Bildschirmfotos: Python mit den Abhängigkeiten von Bony's Agents (z. B. `build/venv`, `pip install -e .`),
  die Seite des Kursraums (`python packaging/fetch-livekit.py`) und `tesseract-ocr tesseract-ocr-deu` für die
  Prüfung.
- Für Emoji in den PDFs (✋ 🆘 🎤): `fonts-noto-color-emoji`. Die Textschriften (Source Sans 3, Source Code Pro,
  SIL OFL) liegen in `vorlage/schriften/`.

## Aufbau

```
docs/handbuch/
├── benutzer.md, kursleiter.md        (Beispielkurs: kurspakete/einfuehrung-hermes-agent/)
├── bilder/              automatisch erzeugte Bildschirmfotos (erstellen.sh ersetzt sie)
│   └── eigene/          von Hand gemachte Bilder (bleiben)
├── vorlage/             Gestaltung: stil.typ (Typst), pandoc.typ (Pandoc-Vorlage), filter.lua, schriften/
├── vorfuehrung/         Vorführmodus für die Bildschirmfotos und deren Prüfung
└── erstellen.sh
```

**Schreiben:** Markdown wie gewohnt, dazu

- Kästen: `::: hinweis`, `::: tipp`, `::: warnung`, `::: datenschutz` … `:::`
- Nummern wie in den Bildern: ①②③ im Text (werden zu orangen Kreisen)
- Bilder mit Unterschrift: `![Unterschrift](bilder/hauptfenster.png){width=70%}`
- Felder zum Ausfüllen (Handout): `::: {.feld hoehe="2cm" text="Beschriftung"}` … `:::`

Fehlt ein Bild aus `bilder/eigene/`, steht im PDF ein grauer Platzhalter „Bild folgt“, und `erstellen.sh` meldet es.

## Bildschirmfotos

`vorfuehrung/bildschirmfotos.py` startet die App im **Vorführmodus** und nimmt jedes Fenster mit Qt auf
(`QWidget.grab()`, `QT_QPA_PLATFORM=offscreen` – geht ohne Bildschirm und unter Wayland). Hauptfenster und
Kursraum in 1280 × 800, Dialoge in ihrer natürlichen Größe, Schrift Source Sans 3, Farbschema der App.

Der Vorführmodus benutzt nur erfundene Daten und fasst den Rechner nicht an:

- eigener, leerer Datenordner unter `/tmp` (wird danach gelöscht), eigene Bony-Netz-Anmeldung, Login-Name „anna“
  bzw. „eva“, Rechnername `annas-laptop` bzw. `kursleitung-pc`;
- Agent-PCs `agent-buero`, `agent-kurs`, `agent-test` (Kursleiterin: `agent-kursleitung`), Vorlagen `kurs-basis`,
  `buero-basis` – ohne QEMU, „läuft“ ist nur vorgespielt;
- eine Zentrale im Speicher (`vorfuehrung/zentrale.py`) mit dem Kurs „Einführung in Hermes Agent“, Kurscode
  `K7QX-M3PA`, Kursleiterin Eva, Teilnehmer Anna, Ben, Clara;
- der Kursraum mit einer Attrappe von LiveKit (`vorfuehrung/livekit-attrappe.js`): Platzhalter statt Kameras, ein
  Beispielbild statt geteiltem Bildschirm;
- Freigabe, Vorführung und Hilfe-Schalter mit erfundenen Teilnehmern – kein Port wird geöffnet, nichts im Netz
  angekündigt;
- Adressen nur aus 192.168.178.0/24 (Beispiel-Heimnetz), 100.64.0.0/24 (Bony-Netz) und 10.8.0.0/24 (VPN).

Danach prüft `vorfuehrung/pruefen.py` jedes Bild per Texterkennung auf Daten dieses Rechners (Rechnername,
Benutzername, Home-Ordner, eigene IP-Adressen, E-Mail aus Git, echte Bony-Netz-Anmeldung) sowie auf fremde
IP-Adressen und Zeichenketten, die wie Tokens aussehen. Findet es etwas, bricht `erstellen.sh` ab.

Ändert sich die Oberfläche, reicht meist `erstellen.sh`. Neue Fenster: eine Zeile in `bilder_anwender` bzw.
`bilder_kursleiter` in `bildschirmfotos.py`. Die Nummern in den Bildern (`marken=[…]`) zeigen auf Widgets, wandern
also mit, wenn sich das Layout ändert – den Text dazu (①②③) bitte mitprüfen.

## Bilder, die von Hand gemacht werden

Diese Bilder lassen sich nicht automatisch erzeugen (fremde Programme, echtes Video). Sie gehören nach
`bilder/eigene/` unter genau diesem Namen. Bitte keine echten Namen, Codes, IP-Adressen oder Tokens zeigen.

| Datei                         | Was zu sehen sein soll                                                                                                                                                                                                                                    |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `windows-smartscreen.png`     | Windows 11: die blaue Warnung „Der Computer wurde durch Windows geschützt“ **nach** dem Klick auf „Weitere Informationen“, also mit App-Name `BonysAgents-Setup-….exe` und dem Knopf „Trotzdem ausführen“                                                 |
| `linux-paketinstallation.png` | Linux Mint: Doppelklick auf `bonys-agents_…_amd64.deb` – das Fenster der Paketinstallation mit Paketname, Beschreibung und Knopf „Paket installieren“ bzw. „Installieren“                                                                                 |
| `macos-nicht-geoeffnet.png`   | (aus `docs/images/macos/` übernommen) Meldung „„Bony's Agents“ nicht geöffnet“ mit „Fertig“                                                                                                                                                               |
| `macos-dennoch-oeffnen.png`   | (aus `docs/images/macos/` übernommen) Systemeinstellungen → Datenschutz & Sicherheit → „Dennoch öffnen“                                                                                                                                                   |
| `agent-pc-desktop.png`        | Das QEMU-Fenster eines frisch eingerichteten Agent-PCs (Cinnamon) mit Hintergrundbild und den Schreibtisch-Symbolen Brave, Telegram und Hermes Agent, kein Programm offen, etwa 1280 × 800                                                                |
| `hermes-setup.png`            | Terminal im Agent-PC nach Doppelklick auf „Hermes Agent“: `hermes setup` läuft, die Auswahl des Anbieters ist zu sehen (z. B. OpenRouter markiert), **noch ohne** eingefügten API-Schlüssel                                                               |
| `browser-zertifikat.png`      | Brave oder Firefox beim Öffnen einer Vorführung (`https://192.168.178.30:47120`): die Warnung „Verbindung nicht privat“ bzw. „Warnung: Mögliches Sicherheitsrisiko“ mit aufgeklapptem „Erweitert“                                                         |
| `kl-hilfe-fenster.png`        | Kursleiter-Version: das Fenster „Hilfe – Ben (Ansehen und bedienen)“ während „Helfen“, oben die Knöpfe „An Fenster anpassen“, „Strg+Alt+Entf“, „Beenden“, darunter der Desktop des Teilnehmer-Agent-PCs (Testkurs mit zweitem Rechner; Anzeigename „Ben“) |

Optional, falls du statt der Platzhalter echte Kameras zeigen möchtest: ein echter Kursraum mit Video – nur mit
Einverständnis aller Abgebildeten.
