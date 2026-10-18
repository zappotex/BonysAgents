# Plan: Kurse (Kurspakete `.bonyskurs`)

Auftrag vom 18.10.2026 (wörtlich im Obsidian-Tresor unter *Projekte/Bony's Agents/Plan/Plan Kurse*).
Neue Sitzung starten mit: **„Mach weiter laut docs/plan-kurse.md“** – zuerst den Abschnitt [Stand](#stand) lesen.

## Ziele

Ein **Kurs** ist ein fertiges, speicher- und ladbares Schulungspaket (z. B. „KI-Agenten für Einsteiger“) mit
Lektionen, Anleitungen, Startzuständen, Prüfaufgaben und Quiz.

- **Erstellen** nur in der Kursleiter-Edition (Kurs-Editor), **durcharbeiten** in beiden Editionen – auch allein
  zu Hause („Selbstlern-Modus“).
- Mitgelieferte **Beispielkurse** von Anfänger bis Experte; der Einsteigerkurs ist vollständig ausgearbeitet, die
  übrigen zunächst als Gliederung („Entwurf“).
- Offenes, textbasiertes Format: mit jedem Editor bearbeitbar, mit Git versionierbar, klein genug für eine E-Mail.
  Statt eines Festplatten-Abbilds enthält ein Kurs ein **Rezept** (Desktop, Apps, Einstellungen) – läuft so auf
  amd64 und arm64.
- Grundstein für das Kursleiter-Dashboard (Stufe 4 aus dem Schulungsplan): Kursleiter sehen pro Teilnehmer nur
  aktuelle Lektion und „geschafft / noch nicht“.

## Begriffe und Abgrenzung

Im Programm gibt es seit 0.21 schon **„Kurse über das Bony-Netz“** (`kurse.py`, Kurscode, Kursraum) – das sind
*Live-Termine*. Die neuen **Kurspakete** sind der *Inhalt*. Deshalb:

| | Code | Oberfläche |
|---|---|---|
| Kurspaket (Format, Bibliothek, Fortschritt) | `src/bonys_agents/kurspaket.py` | Fenster „Kurse“ → Reiter **„Kurs-Bibliothek“** (beide Editionen) |
| Anleitung neben dem Agent-PC | `src/bonys_agents/gui/kurs_anleitung.py` | eigenes kleines Fenster „Kursanleitung“ |
| Prüfungen, Startzustände, Quiz (Sitzung 2) | `src/bonys_agents/kurspaket.py` / `kurslauf.py` | im Fenster „Kursanleitung“ |
| Kurs-Editor, Kurs-Freigabe, Teilnehmer-Übersicht | `src/bonys_agents/trainer/…` | nur Kursleiter-Edition |
| Beispielkurse (Quelle) | `kurse/NN-name/` im Repo | mitgeliefert, Bibliothek „Mitgeliefert“ |

## Kursformat (Kurzfassung – ausführlich in `docs/kursformat.md`)

```
mein-kurs/                    (Ordner)  oder  mein-kurs-1.0.0.bonyskurs  (ZIP mit demselben Inhalt)
├── kurs.json                 Steuerdatei: Name, Beschreibung, Stufe, Sprache, Autor, Lizenz, Version,
│                             Mindestversion, Dauer, Lernziele, Rezept, Lektionsliste
├── bilder/                   optional: Titelbild
└── lektionen/
    └── 01-was-ist-ein-ki-agent/
        ├── anleitung.md      Schritte für Teilnehmer (Markdown, Bilder relativ, z. B. bilder/schritt1.png)
        ├── kursleiter.md     Notizen und Zeitplan – nur für Kursleiter sichtbar
        ├── quiz.json         optional
        ├── pruefung/         optional: Prüfskripte (laufen nur im Agent-PC)
        ├── start/            optional: Einrichtungsskript für den Startzustand
        └── bilder/           optional
```

- `kurs.json` mit `"format": "bonys-agents-kurs"`, `"format_version": 1`. Stufe `anfaenger`, `fortgeschritten`,
  `experte`. Lizenz Standard `CC-BY-SA-4.0`. `entwurf: true` markiert Gliederungen.
- Rezept wie beim `.bonys`-Rezept (`desktop`, `apps`, `ram_mb`, `cpus`, `disk_gb`, `username`, `keyboard`,
  `timezone`), optional `vorlage` (Name einer lokalen Vorlage bzw. `.bonys`-Datei mit SHA-256), die genutzt wird,
  wenn sie vorhanden ist.
- Lektionsliste in `kurs.json` (Reihenfolge, Titel, Dauer, Art, Ziel, Prüfung mit Hinweistexten und Zeitlimit),
  Inhalte in den Lektionsordnern.
- Der Entwurf `kurse/01-ki-agenten-fuer-einsteiger/kurs.md` bildet sich 1:1 ab: Überblick → `kurs.json`
  (Zielgruppe, Voraussetzungen, Kosten, Lernziele), Ablauf-Tabelle → Lektionsliste, je Lektion Ziel und Schritte →
  `anleitung.md`, Prüfaufgabe → `pruefung/` + Hinweistexte, Quiz → `quiz.json`, Kursleiter-Notiz → `kursleiter.md`.

## Entscheidungen

1. **Anleitung neben dem Agent-PC: eigenes kleines Fenster in Bony's Agents** (nicht eine Kurs-App im Agent-PC).
   Begründung:
   - funktioniert mit allen sechs Desktops und auch mit Agent-PCs aus fremden Vorlagen – im Gast muss nichts
     installiert oder aktuell gehalten werden;
   - die Kursleiter-Notizen, Quiz-Lösungen und Prüfskripte bleiben auf dem eigenen Rechner. Im Agent-PC läuft ein
     KI-Agent mit Datei- und Terminal-Zugriff – er soll die Lösungen nicht lesen und den Fortschritt nicht fälschen
     können (Prompt-Injection: eine Anleitung im Gast wäre für den Agenten eine Eingabe);
   - Fortschritt, „Prüfen“, „Lektion zurücksetzen“ (Schnappschüsse) und später die Teilnehmer-Übersicht brauchen
     ohnehin die App auf dem Rechner; keine zweite Datenverbindung Gast → Rechner nötig;
   - funktioniert schon während der Agent-PC noch eingerichtet wird (Lektion 1–2 sind Theorie).
   Gegen das Fenster-Suchen: schmales Fenster, Schalter „Immer im Vordergrund“ (Standard an), wird beim Öffnen an
   den rechten Bildschirmrand gesetzt; Position wird gemerkt; „Agent-PC anzeigen“ holt das QEMU-Fenster nach vorn.
2. **Paket ist ZIP** (`.bonyskurs`), Ordnerform gleichwertig (Git, Editor). Beim Import wird nach
   `Datenordner/kurse/<kurs-id>/` entpackt; geprüft wird vor dem Entpacken (Pfade, Größe, Anzahl, Dateiarten).
3. **Kurs-ID** = `id` aus `kurs.json` (`[a-z0-9-]`, 3–60 Zeichen). Gleiche ID = derselbe Kurs → Import einer
   neueren Version „aktualisiert“ (Fortschritt bleibt), ältere Version nur nach Rückfrage.
4. **Fortschritt** lokal in `Datenordner/kurse/fortschritt.json` (Kurs-ID → Agent-PC, aktuelle Lektion, erledigte
   Lektionen, Prüfergebnisse, Quiz-Ergebnis). Nichts geht ins Internet.
5. **Beispielkurse** liegen als Ordner in `kurse/` im Repo und werden ins Programm gepackt (Sitzung 4); sie sind
   „mitgeliefert“ und gelten als geprüft.
6. **Kurse aus dem Internet** (optional): `index.json` aus einem öffentlichen GitHub-Repo mit Name, Version, Stufe,
   Download-URL und SHA-256; Download nur über HTTPS, Prüfsumme muss passen. Repo-URL ist bis zur Entscheidung des
   Nutzers ein Platzhalter (`zappotex/bonys-agents-kurse`).

## Sicherheitsregeln

- Keine API-Keys, Tokens, Passwörter oder Zugangsdaten in Kursen. Kurse nutzen kostenlose Modelle oder „eigenen
  Schlüssel / eigenes Konto verwenden“. Der Editor prüft vor dem Speichern/Export auf Geheimnisse und blockiert.
- Prüf- und Startskripte laufen **nur im Agent-PC** (Gast-Agent bzw. SSH des Agent-PCs), nie auf dem eigenen
  Rechner. Kein Code-Pfad führt ein Kurs-Skript lokal aus; Tests sichern das ab.
- Prüfergebnis nur „geschafft / noch nicht“ plus Hinweistext *aus dem Kurs* – keine Ausgabe des Skripts an die
  Oberfläche oder den Kursleiter. Zeitlimit pro Prüfung.
- Prüfungen lesen nie Schlüssel aus (z. B. Hermes: nur „Modell/Anbieter ist eingetragen“, nicht der Schlüssel).
- Fremde Kurse: vor dem ersten Start Hinweis „Dieser Kurs führt Skripte im Agent-PC aus“ mit Liste der Skripte.
- Entpacken: keine absoluten Pfade, kein `..`, keine Links/Geräte, Größenlimit gesamt und je Datei, Anzahl-Limit,
  nur erlaubte Dateiendungen. Markdown wird ohne HTML-Ausführung und ohne Nachladen aus dem Internet angezeigt.
- Kein sudo ohne Rückfrage; keine Geheimnisse im Klartext ausgeben; Programme nur aus offiziellen Quellen.

## Sitzungsplan

### Sitzung 1 – Kursformat, Bibliothek, Kurs-Player
1. Kursformat `.bonyskurs`, JSON-Schema in `docs/kursformat.md`, Validierung mit deutschen Fehlermeldungen,
   sicheres Entpacken.
2. Kurs-Bibliothek (beide Editionen): Liste mit Stufe, Dauer, Beschreibung; importieren (Datei, Drag & Drop),
   löschen, aktualisieren; optional „Kurse aus dem Internet“ (Platzhalter-Repo, Prüfsumme).
3. Kurs starten: Agent-PC aus Rezept (bzw. passender Vorlage) erstellen, Fortschritt pro Kurs merken.
4. Fenster „Kursanleitung“ mit Zurück/Weiter, Lektionswahl und Fortschrittsanzeige.

### Sitzung 2 – Startzustände und Prüfaufgaben
1. Startzustand je Lektion (Entscheidung qcow2-Schnappschuss vs. `start/`-Skript), „Lektion zurücksetzen“,
   „Zu Lektion X springen“, Warnung vor Verlust persönlicher Dateien.
2. Prüfaufgaben nur im Agent-PC, Ergebnis „geschafft / noch nicht“ + Hinweis, Zeitlimit.
3. Hinweis vor dem ersten Start fremder Kurse mit Skriptliste; optional Signatur („geprüfter Kurs“).
4. Quiz am Ende der Lektion (`quiz.json`), Ergebnis lokal.

### Sitzung 3 – Kurs-Editor (nur Kursleiter)
Kurs anlegen, Lektionen hinzufügen/umsortieren/löschen, Markdown mit Vorschau, Bilder (Screenshot des Agent-PCs),
Notizen, Zeiten, Quiz, Prüfskripte mit Vorlagen; „Startzustand aus aktuellem Agent-PC übernehmen“; speichern,
laden, duplizieren, Version erhöhen; Geheimnis-Prüfung vor Export; Handout-PDF (Teilnehmer / Kursleiter);
„Kurs prüfen“ im Test-Agent-PC.

### Sitzung 4 – Schulungsmodus, Beispielkurse, Abschluss
Kurs freigeben (statt nur Vorlage), Teilnehmer-Übersicht; Einsteigerkurs vollständig im Format, fünf weitere als
Entwurf (Hermes-Befehle in der Doku prüfen); Edition-Trennung, `docs/editionen.md`, README „Kurse“; Tests;
echter Test mit Screenshots; pytest/ruff beider Editionen, Minor-Version, .deb, Installation nach Rückfrage.
Release erst nach Test und OK des Nutzers.

## Stand

Zuletzt aktualisiert: 18.10.2026 (Sitzung 1).

### Sitzung 1
- [x] Plan angelegt (`docs/plan-kurse.md`), Entwurf nach `kurse/01-ki-agenten-fuer-einsteiger/kurs.md` verschoben
- [ ] Kursformat + Validierung + sicheres Entpacken (`kurspaket.py`), `docs/kursformat.md` mit JSON-Schema
- [ ] Bibliothek: Liste, Import (Datei/Drag & Drop), Löschen, Aktualisieren, Internet-Liste (Platzhalter)
- [ ] Kurs starten (Agent-PC aus Rezept/Vorlage), Fortschritt pro Kurs
- [ ] Fenster „Kursanleitung“ (Zurück/Weiter, Fortschritt)
- [ ] Tests, ruff, Commit

### Sitzung 2
- [ ] Startzustände, Zurücksetzen, Springen
- [ ] Prüfaufgaben im Agent-PC mit Zeitlimit
- [ ] Hinweis für fremde Kurse, optional Signatur
- [ ] Quiz

### Sitzung 3
- [ ] Kurs-Editor (Kursleiter)
- [ ] Startzustand übernehmen, Speichern/Export mit Geheimnis-Prüfung
- [ ] Handout-PDF
- [ ] „Kurs prüfen“

### Sitzung 4
- [ ] Kurs freigeben + Teilnehmer-Übersicht
- [ ] Einsteigerkurs vollständig, fünf Kurse als Entwurf
- [ ] Doku (editionen.md, README, kursformat.md)
- [ ] Tests beider Editionen, echter Test, Version, .deb, Commit

### Offene Fragen an den Nutzer
- Endgültiges GitHub-Repo für „Kurse aus dem Internet“ (Platzhalter: `zappotex/bonys-agents-kurse`).
