# Kurspaket-Format (`.bonyspaket`) – für Autorinnen und Autoren

Ein **Kurspaket** ist der *Inhalt* einer Schulung: Lektionen mit Anleitungen, Ablaufplan für die Kursleitung,
Handout, Prüfaufgaben und Quiz. Ein **Kurs** ist die *Durchführung* (über das Bony-Netz mit Kurscode oder als
Schulung im eigenen Netz). Ein Kurspaket lässt sich auch ohne Kurs allein durcharbeiten (Selbstlern-Modus).

Ab Bony's Agents **0.23.0**. Lizenz der Beispielpakete: CC BY-SA 4.0.

## Aufbau

Ein Kurspaket ist ein **Ordner** – gut mit Git zu verwalten und mit jedem Texteditor zu bearbeiten – oder derselbe
Inhalt als **ZIP-Datei mit der Endung `.bonyspaket`** zum Weitergeben. In der ZIP-Datei darf `paket.json` ganz oben
liegen oder in genau einem Ordner ganz oben (so entsteht sie, wenn man den Ordner packt).

```
einfuehrung-hermes-agent/
├── paket.json                   Steuerdatei (Pflicht)
├── ablaufplan.md                Für die Kursleitung: Blöcke mit Zeiten, Notizen, Lösungen (Pflicht)
├── handout.md                   Für Teilnehmer, zum Ausdrucken (optional)
├── bilder/                      Bilder für Ablaufplan und Handout (optional)
└── lektionen/                   Lektionen zum Durcharbeiten neben dem Agent-PC (optional)
    └── 03-hermes-startklar/     Ordnername „NN-name“ (zwei Ziffern, Bindestrich, Kleinbuchstaben)
        ├── anleitung.md         Schritte für Teilnehmer (Pflicht je Lektion)
        ├── kursleitung.md       Notizen zur Lektion – nur in der Kursleiter-Version sichtbar (optional)
        ├── quiz.json            Quiz am Ende der Lektion (optional)
        ├── pruefung/            Prüfskripte (optional) – laufen nur im Agent-PC
        ├── start/               Startskript für den Startzustand (optional) – läuft nur im Agent-PC
        └── bilder/              Bilder der Anleitung (optional), im Text z. B. ![Terminal](bilder/terminal.png)
```

**Erlaubte Dateien:** `.md`, `.txt`, `.json`, `.sh`, `.py`, `.png`, `.jpg`/`.jpeg`, `.gif`, `.webp`, `.minisig` und Dateien
ohne Endung (z. B. `LICENSE`). Versteckte Dateien (`.git`, `.DS_Store` …) und `__MACOSX` werden beim Packen und
Importieren weggelassen. Alle Texte in UTF-8.

**Grenzen:** entpackt höchstens 200 MB, je Datei 25 MB, 2000 Dateien, 8 Ordnerebenen, 100 Lektionen; Markdown und
Skripte je 2 MB, JSON-Dateien je 1 MB.

## Was niemals in ein Kurspaket gehört

- **Keine API-Schlüssel, Tokens, Passwörter oder sonstige Zugangsdaten** – auch nicht „nur für den Kurs“.
  Teilnehmer nutzen ein kostenloses Modell mit eigenem Konto oder ihren eigenen Schlüssel.
- Keine persönlichen Daten (Namen, E-Mail-Adressen, Telefonnummern von Teilnehmern).
- Kein Festplatten-Abbild – stattdessen das **Rezept** (siehe unten) bzw. ein Verweis auf eine Vorlage.

Bony's Agents sucht beim Speichern im Editor und beim Exportieren in allen Textdateien nach Schlüsseln, Tokens,
Passwörtern, E-Mail-Adressen, Telefonnummern und IBANs und **blockiert**, bis sie entfernt sind (angezeigt wird nur
Datei, Zeile und Art – nie der Wert). Platzhalter wie `<dein-schlüssel>` oder `$OPENROUTER_API_KEY` sind in Ordnung,
ebenso Beispieladressen wie `kurs@example.com`.

## Markdown

`anleitung.md`, `kursleitung.md`, `ablaufplan.md` und `handout.md` sind Markdown wie in den Handbüchern von
Bony's Agents. Zusätzlich verstanden werden:

- Titelblock am Anfang: `---` / `title: …` / `subtitle: …` / `---`
- Kästen: `::: hinweis`, `::: tipp`, `::: warnung`, `::: datenschutz` … `:::`
- Felder zum Ausfüllen (Handout): `::: {.feld hoehe="2cm" text="Beschriftung"}` … `:::`

Bony's Agents zeigt **kein HTML** an, lädt **Bilder nur aus dem Kurspaket** (nichts aus dem Internet) und öffnet
Links nur nach einem Klick und nur mit `https://` im Browser.

## `paket.json`

Beispiel (gekürzt):

```json
{
  "format": "bonys-agents-kurspaket",
  "format_version": 1,
  "min_version": "0.23.0",
  "id": "einfuehrung-hermes-agent",
  "name": "Einführung in Hermes Agent",
  "beschreibung": "Was ein KI-Agent ist, wie man ihm Aufgaben gibt und wo seine Grenzen sind.",
  "stufe": "anfaenger",
  "sprache": "de",
  "autor": "Bony",
  "lizenz": "CC-BY-SA-4.0",
  "version": "1.0.0",
  "dauer_minuten": 120,
  "pause_minuten": 10,
  "teilnehmer": {"min": 5, "max": 10},
  "zielgruppe": "Menschen ohne Vorkenntnisse",
  "voraussetzungen": ["Rechner mit mind. 8 GB RAM und 40 GB frei", "Internet"],
  "kosten": "keine – kostenloses Modell",
  "lernziele": ["erklären, was ein KI-Agent ist", "Hermes starten und ihm eine Aufgabe geben"],
  "quellen": [{"titel": "Hermes Agent Docs", "url": "https://hermes-agent.nousresearch.com/docs"}],
  "rezept": {
    "name": "agent-kurs",
    "desktop": "cinnamon",
    "apps": ["brave", "telegram", "hermes"],
    "disk_gb": 64,
    "username": "agent",
    "keyboard": "de",
    "timezone": "Europe/Berlin"
  },
  "lektionen": [
    {"ordner": "01-was-ist-ein-agent", "titel": "Was ist ein Agent?", "dauer_minuten": 15,
     "art": "Erklärung + Quiz", "ziel": "Den Unterschied zwischen Chatbot und Agent verstehen."},
    {"ordner": "02-hermes-startklar", "titel": "Hermes startklar", "dauer_minuten": 15, "art": "Mitmachen",
     "pruefung": {"typ": "agent-pc-laeuft", "aufgabe": "Der Agent-PC läuft.",
                  "noch_nicht": "Starte deinen Agent-PC im Hauptfenster."}},
    {"ordner": "03-uebung-dateien", "titel": "Übung 1: Dateien", "dauer_minuten": 20, "art": "Übung",
     "pruefung": {"skript": "pruefung/einkaufsliste.sh", "aufgabe": "~/Kurs/einkaufsliste.txt mit Käse",
                  "geschafft": "Die Einkaufsliste ist da!", "noch_nicht": "Die Datei fehlt noch.",
                  "zeitlimit": 20}}
  ]
}
```

### Felder

| Feld | Pflicht | Bedeutung |
|---|:---:|---|
| `format` | ✓ | immer `"bonys-agents-kurspaket"` |
| `format_version` | ✓ | `1` |
| `min_version` | | älteste Version von Bony's Agents, die das Paket öffnen kann (Standard `0.23.0`) |
| `id` | ✓ | eindeutige Kennung, 3–60 Zeichen `a-z 0-9 -`. Gleiche ID = dasselbe Paket (Aktualisieren) |
| `name` | ✓ | Titel (bis 120 Zeichen, einzeilig) |
| `beschreibung` | ✓ | kurze Beschreibung (bis 2000 Zeichen) |
| `stufe` | ✓ | `anfaenger`, `fortgeschritten` oder `experte` |
| `version` | ✓ | z. B. `1.0.0` – beim Ändern erhöhen |
| `sprache` | | z. B. `de` (Standard) |
| `autor`, `lizenz` | | Lizenz Standard `CC-BY-SA-4.0` |
| `dauer_minuten`, `pause_minuten` | | Gesamtdauer; fehlt sie, wird die Summe der Lektionen genommen |
| `teilnehmer` | | `{"min": 5, "max": 10}` |
| `zielgruppe`, `kosten` | | Text |
| `voraussetzungen`, `lernziele` | | Listen von Texten |
| `quellen` | | Liste `{"titel", "url"}`, nur `https://` |
| `entwurf` | | `true` = Gliederung, noch nicht ausgearbeitet |
| `rezept` | | wie der Agent-PC aussehen soll (siehe unten) |
| `lektionen` | | Liste der Lektionen in der Reihenfolge des Durcharbeitens |

### Rezept

| Feld | Bedeutung |
|---|---|
| `name` | Vorschlag für den Namen des Agent-PCs (Buchstaben, Ziffern, `-`, `_`; bis 40) |
| `desktop` | `cinnamon`, `xfce`, `kde`, `gnome`, `mate` oder `lxqt` |
| `apps` | Programme, z. B. `brave`, `telegram`, `hermes`, `obsidian`, `docker`, `mission-control`, `vpn` |
| `ram_mb`, `cpus`, `disk_gb` | Empfehlung (Festplatte 32–1024 GB) |
| `username`, `keyboard`, `timezone` | Standard `agent`, `de`, `Europe/Berlin` |
| `vorlage` | Name einer Vorlage, die genutzt wird, wenn sie auf dem Rechner vorhanden ist |
| `vorlage_sha256` | SHA-256 der passenden `.bonys`-Datei (zum Weitergeben der Vorlage) |

### Lektion

| Feld | Pflicht | Bedeutung |
|---|:---:|---|
| `ordner` | ✓ | Ordner unter `lektionen/`, Form `NN-name` |
| `titel` | ✓ | Titel der Lektion |
| `dauer_minuten`, `art`, `ziel` | | z. B. `20`, `"Übung"`, `"Hermes löst eine kleine Aufgabe."` |
| `pruefung` | | Prüfaufgabe (siehe unten) |
| `start` | | `{"skript": "start/einrichten.sh", "zeitlimit": 120, "als": "root"}` – Startskript (siehe unten) |

### Prüfaufgabe

Ergebnis ist immer nur **„geschafft“ oder „noch nicht“** mit dem Hinweistext aus dem Paket – die Ausgabe eines
Skripts sieht niemand.

| Feld | Bedeutung |
|---|---|
| `typ` | `skript` (Standard), `agent-pc-laeuft` oder `vorlage-vorhanden` |
| `skript` | bei `typ: skript`: Pfad in der Lektion, z. B. `pruefung/einkaufsliste.sh` (`.sh` oder `.py`) |
| `aufgabe` | was die Teilnehmer tun sollen |
| `geschafft`, `noch_nicht` | Hinweistexte |
| `zeitlimit` | Sekunden, 1–300 (Standard 30) |
| `als` | `benutzer` (Standard, Benutzer des Agent-PCs) oder `root` |
| `loesung` | optional, bei `typ: skript`: Skript, das die Aufgabe löst, z. B. `pruefung/loesung.sh` – läuft nur bei **„Kurspaket prüfen“** im Editor (Test-Agent-PC), nie bei Teilnehmern |

**Prüfskripte laufen nur im Agent-PC**, nie auf dem Rechner der Teilnehmer. Exit-Code `0` heißt „geschafft“.
Sie sollen nichts ausgeben, nichts verändern und **niemals Schlüssel auslesen** – z. B. prüft „Hermes ist
eingerichtet“ nur, ob in `~/.hermes/config.yaml` ein Anbieter und ein Modell eingetragen sind, und liest nie
`~/.hermes/.env` oder `auth.json`.

`agent-pc-laeuft` und `vorlage-vorhanden` prüft Bony's Agents selbst – ohne Code aus dem Paket.

### Startzustand und Startskript

Sobald jemand eine Lektion zum ersten Mal betritt und der Agent-PC fertig ist, sichert Bony's Agents ihren
**Startzustand** – einen Schnappschuss der Festplatte des Agent-PCs (nur auf dem Rechner der Teilnehmer, er kostet
nur den Platz der danach geänderten Daten). Mit **„Zurücksetzen“** bzw. beim **Springen zu einer früheren Lektion**
geht der Agent-PC auf diesen Stand zurück; alles danach Geänderte – auch eigene Dateien – geht verloren, darauf
weist Bony's Agents vorher hin.

Ein optionales **Startskript** (`"start": {"skript": "start/einrichten.sh"}`) läuft vor dem Sichern im Agent-PC,
z. B. um einen Übungsordner und Beispieldateien anzulegen. Springt jemand nach vorn, laufen die Startskripte der
übersprungenen Lektionen der Reihe nach. Startskripte sollen wiederholbar sein (`mkdir -p`, Dateien überschreiben)
und brauchen keine Zugangsdaten. Wird der Agent-PC auf ein anderes Laufwerk verschoben oder unabhängig gemacht,
gehen die Startzustände verloren; sie entstehen beim nächsten Betreten der Lektion neu.

## Geprüfte Kurspakete (Signatur)

Mitgelieferte Kurspakete gelten als geprüft. Andere Pakete können mit dem Release-Schlüssel von Bony's Agents
signiert werden: Im Paket liegen dann

- `pruefsummen.txt` – SHA-256 aller Dateien im Format von `sha256sum` (Pfade relativ, mit `/`), ohne die
  beiden Signaturdateien selbst;
- `pruefsummen.txt.minisig` – minisign-Signatur von `pruefsummen.txt`.

Stimmt die Signatur und passt `pruefsummen.txt` genau zu den Dateien des Pakets (keine fehlt, keine ist dazugekommen,
keine geändert), zeigt die Bibliothek „Geprüftes Kurspaket“. Bei allen anderen Paketen mit Skripten erscheint vor dem
ersten Start der Hinweis **„Dieses Kurspaket führt Skripte im Agent-PC aus“** mit der Liste der Skripte; die
Zustimmung gilt für genau diese Fassung und wird bei geänderten Skripten erneut eingeholt.

## `quiz.json`

```json
{
  "fragen": [
    {
      "frage": "Was unterscheidet einen Agenten von einem Chatbot?",
      "antworten": ["Er ist schneller", "Er führt mit Werkzeugen selbst Schritte aus", "Er braucht kein Internet"],
      "richtig": 1,
      "erklaerung": "Ein Agent handelt: Er führt Befehle aus, legt Dateien an, öffnet Webseiten."
    }
  ]
}
```

1–30 Fragen, je 2–6 Antworten, `richtig` zählt ab 0. Das Ergebnis bleibt auf dem Rechner der Teilnehmer.

## JSON-Schema

Bony's Agents prüft `paket.json` beim Laden selbst (mit verständlichen Meldungen). Das Schema hilft beim Schreiben
in Editoren, die JSON-Schema können (z. B. VS Code: `"$schema"` braucht es nicht in der Datei – Schema-Zuordnung in
den Einstellungen).

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Kurspaket von Bony's Agents (paket.json)",
  "type": "object",
  "required": ["format", "format_version", "id", "name", "beschreibung", "stufe", "version"],
  "properties": {
    "format": {"const": "bonys-agents-kurspaket"},
    "format_version": {"type": "integer", "minimum": 1},
    "min_version": {"type": "string", "pattern": "^[0-9]+(\\.[0-9]+){0,3}$"},
    "id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{1,58}[a-z0-9]$"},
    "name": {"type": "string", "minLength": 1, "maxLength": 120},
    "beschreibung": {"type": "string", "minLength": 1, "maxLength": 2000},
    "stufe": {"enum": ["anfaenger", "fortgeschritten", "experte"]},
    "version": {"type": "string", "pattern": "^[0-9]+(\\.[0-9]+){0,3}$"},
    "sprache": {"type": "string", "pattern": "^[a-z]{2}(-[A-Z]{2})?$"},
    "autor": {"type": "string", "maxLength": 120},
    "lizenz": {"type": "string", "maxLength": 60},
    "dauer_minuten": {"type": "integer", "minimum": 0, "maximum": 6000},
    "pause_minuten": {"type": "integer", "minimum": 0, "maximum": 1440},
    "teilnehmer": {
      "type": "object",
      "properties": {"min": {"type": "integer", "minimum": 1, "maximum": 1000},
                     "max": {"type": "integer", "minimum": 1, "maximum": 1000}}
    },
    "zielgruppe": {"type": "string", "maxLength": 500},
    "kosten": {"type": "string", "maxLength": 300},
    "voraussetzungen": {"type": "array", "maxItems": 30, "items": {"type": "string", "minLength": 1, "maxLength": 300}},
    "lernziele": {"type": "array", "maxItems": 30, "items": {"type": "string", "minLength": 1, "maxLength": 300}},
    "quellen": {
      "type": "array", "maxItems": 30,
      "items": {"type": "object", "required": ["titel", "url"],
                "properties": {"titel": {"type": "string", "maxLength": 200},
                               "url": {"type": "string", "pattern": "^https://", "maxLength": 500}}}
    },
    "entwurf": {"type": "boolean"},
    "rezept": {
      "type": "object",
      "properties": {
        "name": {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$"},
        "desktop": {"enum": ["cinnamon", "xfce", "kde", "gnome", "mate", "lxqt"]},
        "apps": {"type": "array", "maxItems": 40, "items": {"type": "string", "pattern": "^[a-z0-9-]{1,40}$"}},
        "ram_mb": {"type": "integer", "minimum": 1024, "maximum": 262144},
        "cpus": {"type": "integer", "minimum": 1, "maximum": 64},
        "disk_gb": {"type": "integer", "minimum": 32, "maximum": 1024},
        "username": {"type": "string", "pattern": "^[a-z_][a-z0-9_-]{0,31}$"},
        "keyboard": {"type": "string", "pattern": "^[A-Za-z0-9_()-]{1,40}$"},
        "timezone": {"type": "string", "pattern": "^[A-Za-z0-9_+/-]{1,64}$"},
        "vorlage": {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$"},
        "vorlage_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"}
      }
    },
    "lektionen": {
      "type": "array", "maxItems": 100,
      "items": {
        "type": "object",
        "required": ["ordner", "titel"],
        "properties": {
          "ordner": {"type": "string", "pattern": "^[0-9]{2}-[a-z0-9][a-z0-9-]{0,58}$"},
          "titel": {"type": "string", "minLength": 1, "maxLength": 120},
          "dauer_minuten": {"type": "integer", "minimum": 0, "maximum": 1440},
          "art": {"type": "string", "maxLength": 60},
          "ziel": {"type": "string", "maxLength": 500},
          "pruefung": {
            "type": "object",
            "properties": {
              "typ": {"enum": ["skript", "agent-pc-laeuft", "vorlage-vorhanden"]},
              "skript": {"type": "string", "pattern": "^[^/\\\\.][^\\\\]*\\.(sh|py)$"},
              "loesung": {"type": "string", "pattern": "^[^/\\\\.][^\\\\]*\\.(sh|py)$"},
              "aufgabe": {"type": "string", "maxLength": 300},
              "geschafft": {"type": "string", "maxLength": 300},
              "noch_nicht": {"type": "string", "maxLength": 500},
              "zeitlimit": {"type": "integer", "minimum": 1, "maximum": 300},
              "als": {"enum": ["benutzer", "root"]}
            }
          },
          "start": {
            "type": "object",
            "required": ["skript"],
            "properties": {
              "skript": {"type": "string", "pattern": "^[^/\\\\.][^\\\\]*\\.(sh|py)$"},
              "zeitlimit": {"type": "integer", "minimum": 1, "maximum": 1800},
              "als": {"enum": ["benutzer", "root"]}
            }
          }
        }
      }
    }
  }
}
```

## Mitgelieferte Kurspakete

Im Quellcode liegen sie im Ordner `kurspakete/` (im Programm unter `bonys_agents/resources/kurspakete`, beide
Editionen): „Einführung in Hermes Agent“ (fertig, zugleich der Beispielkurs der Handbücher), aus der Reihe
„Agenten, MCP-Apps und n8n“ die fertigen Pakete „Was ist ein MCP-Server?“ und „n8n-Grundlagen“ (ab 0.24.0) sowie
fünf Entwürfe (`"entwurf": true`). Jede Release-Aktion signiert sie (`packaging/kurspakete.py`) und hängt sie als `.bonyspaket`
samt `kurspakete-index.json` an – die Vorlage für `index.json` im Repository unten.

## Kurspakete in Kursen

Ein Kurs kann ein Kurspaket mitbringen:

- **Kurs über das Bony-Netz:** Der Kursleiter lädt die gepackte Datei zur Zentrale hoch (höchstens 25 MB,
  `PUT /api/v1/kurse/{id}/kurspaket`, siehe API.md von bonys-netz). Die Teilnehmer holen sie automatisch; sie muss zur
  SHA-256 der Zentrale passen und wird wie jeder Import vollständig geprüft. In der Bibliothek steht sie dann als
  „aus einem Kurs“. Ist der Inhalt gleich einem vorhandenen Paket (z. B. dem mitgelieferten), bleibt das vorhandene.
  Ein selbst erstelltes Paket mit derselben Kennung wird nie überschrieben.
- **Schulung im eigenen Netz:** Die Freigabe liefert das Paket zusätzlich unter `GET /bonys/v1/kurspaket` aus
  (gleicher Code und Fingerabdruck wie die Vorlage).
- **Fortschritt:** Die Anleitung meldet nur die aktuelle Lektion (ab 1) und ob ihre Prüfaufgabe geschafft ist
  (`true`, `false` oder `null`) – an die Zentrale bzw. an `POST /bonys/v1/fortschritt` (höchstens 1 KB). Quiz,
  Dateien und Ausgaben von Skripten verlassen den Rechner nie.

## Kurspakete aus dem Internet

Die Bibliothek kann eine Liste aus einem öffentlichen GitHub-Repository laden (`index.json`):

```json
{
  "format": "bonys-agents-kurspaket-katalog",
  "pakete": [
    {"id": "einfuehrung-hermes-agent", "name": "Einführung in Hermes Agent", "version": "1.0.0",
     "stufe": "anfaenger", "dauer_minuten": 120, "beschreibung": "…",
     "datei": "pakete/einfuehrung-hermes-agent-1.0.0.bonyspaket",
     "sha256": "…64 Hex-Zeichen…", "groesse": 123456}
  ]
}
```

`datei` ist relativ zur Adresse von `index.json` (oder eine volle `https://`-Adresse). Bony's Agents lädt nur über
HTTPS, vergleicht Größe und SHA-256 und prüft das Paket vollständig, bevor es in die Bibliothek kommt.

## Prüfen beim Laden

Beim Import, beim Download und beim Öffnen der Bibliothek prüft Bony's Agents jedes Kurspaket vollständig und
meldet Fehler verständlich, z. B. *„paket.json: „stufe“ muss „anfaenger“, „fortgeschritten“ oder „experte“ sein
(gefunden: „profi“).“* oder *„Lektion 3 „Übung 1“: Prüfskript „pruefung/x.sh“ fehlt.“* Fehlerhafte Pakete in der
Bibliothek stehen mit ihrer Meldung über der Liste.
