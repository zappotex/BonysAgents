# Plan: Kurspakete (`.bonyspaket`)

Auftrag: `docs/dev/auftrag-kurspakete.md` (Stand 18.10.2026, nicht im Repo – steht in `.gitignore`; wörtlich auch
im Obsidian-Tresor unter *Projekte/Bony's Agents/Plan/Kurspakete – Auftrag und Stand*).
Neue Sitzung: **„Mach weiter laut docs/dev/plan-kurspakete.md“** – zuerst [Stand](#stand) lesen.

## Ziel

Kursleiter erstellen **fertige Kurspakete** von Anfänger bis Experte, speichern und laden sie wieder: Lektionen,
Anleitungen, Startzustände, Prüfaufgaben, Quiz, Ablaufplan und Handout. Durcharbeiten lassen sie sich in **beiden
Editionen**, auch allein (Selbstlern-Modus). Mitgeliefert werden Beispielpakete von Anfänger bis Experte.

## Begriffe

| Begriff | Bedeutung | Code |
|---|---|---|
| **Kurspaket** | der *Inhalt*: Lektionen, Ablaufplan, Handout, Prüfungen, Quiz – Datei `.bonyspaket` | `kurspaket.py`, `gui/kurspaket_*.py` |
| **Kurs** | die *Durchführung*: Bony-Netz-Kurs mit Kurscode, Teilnehmern, Kursraum | `kurse.py`, `gui/kurse_dialog.py`, `trainer/gui/kurse_leiten.py` |
| **Schulung im eigenen Netz** | Freigabe, Vorführen, Hilfe-Schalter (LAN/VPN) | `share*.py`, `trainer/…` |
| **Selbstlern-Modus** | ein Kurspaket ohne Kurs allein durcharbeiten | `kurspaket.py` (Fortschritt), `gui/kurspaket_anleitung.py` |

Beim Anlegen eines Kurses bzw. einer Schulung kann ein Kurspaket gewählt werden (Sitzung 4); ohne Kurspaket bleibt
alles wie bisher. In Oberfläche und Handbüchern nie „Kurs“ für das Paket sagen; Glossar im Benutzerhandbuch.

## Format (Kurzfassung – Schema in `docs/kurspaket-format.md`)

```
einfuehrung-hermes-agent/          Ordner – oder einfuehrung-hermes-agent-1.0.0.bonyspaket (ZIP, gleicher Inhalt)
├── paket.json                     Name, Beschreibung, Stufe, Sprache, Autor, Lizenz (CC-BY-SA-4.0), Version,
│                                  Mindestversion, Dauer, Pause, Teilnehmerzahl, Zielgruppe, Voraussetzungen,
│                                  Lernziele, Quellen, Rezept, Lektionsliste
├── ablaufplan.md                  Kursleitung: Blöcke mit Zeiten, Notizen, Lösungen (Pflicht)
├── handout.md                     Teilnehmer (optional)
├── bilder/
└── lektionen/                     optional – für Anleitung neben dem Agent-PC, Prüfungen, Quiz
    └── 03-hermes-startklar/
        ├── anleitung.md           Schritte für Teilnehmer
        ├── kursleitung.md         optional: Notizen nur für die Kursleitung
        ├── quiz.json              optional
        ├── pruefung/*.sh|*.py     optional – laufen nur im Agent-PC
        ├── start/*.sh             optional – Startzustand, nur im Agent-PC
        └── bilder/
```

- Rezept wie das `.bonys`-Rezept (Desktop, Apps, RAM, CPUs, Festplatte, Benutzer, Tastatur, Zeitzone), dazu
  Namensvorschlag und optional `vorlage` (+ `vorlage_sha256` der `.bonys`-Datei) – kein Festplatten-Abbild.
- Prüfungen: `typ: "skript"` (Skript im Agent-PC, Exit 0 = geschafft) oder eingebaut ohne Code aus dem Paket:
  `agent-pc-laeuft`, `vorlage-vorhanden` (weitere bei Bedarf, z. B. `hermes-eingerichtet` als Vorlage im Editor).
- Ablaufplan und Handout sind dieselbe Markdown-Sprache wie die Handbücher (Kästen `::: tipp`, Felder `.feld`),
  damit `docs/handbuch/erstellen.sh` bzw. dieselbe Vorlage daraus PDFs baut.

## Entscheidungen

1. **Anzeige neben dem Agent-PC: eigenes kleines Fenster in Bony's Agents** („Kurspaket-Anleitung“) – nicht im
   Kursraum. Begründung: Der Selbstlern-Modus hat keinen Kursraum (der braucht Bony-Netz, Internet und WebEngine,
   fehlt unter Linux arm64); das Fenster funktioniert mit allen Desktops und fremden Vorlagen, im Agent-PC muss
   nichts installiert werden; Kursleitungs-Notizen, Quiz-Lösungen und Prüfskripte bleiben auf dem eigenen Rechner
   (der KI-Agent im Agent-PC soll sie nicht lesen oder den Fortschritt fälschen können). Im Kursraum kommt in
   Sitzung 4 nur ein Knopf „Anleitung“, der dasselbe Fenster öffnet. Gegen Fenster-Suchen: schmal, „Immer im
   Vordergrund“ (an), rechts am Bildschirmrand, Position gemerkt.
2. **Paket = ZIP** mit Endung `.bonyspaket`, Ordnerform gleichwertig (Git, Editor). Import entpackt nach
   `Datenordner/kurspakete/<id>/`; geprüft wird vor und während des Entpackens.
3. **ID** aus `paket.json` (`[a-z0-9-]`, 3–60). Gleiche ID = dasselbe Paket → neuere Version „aktualisiert“
   (Fortschritt bleibt), gleiche/ältere nur nach Rückfrage.
4. **Fortschritt** lokal in `Datenordner/kurspakete/fortschritt.json`.
5. **Mitgelieferte Pakete** liegen als Ordner in `kurspakete/` im Repo und kommen ins Programm
   (`resources/kurspakete`, Sitzung 4). Das erste Paket entsteht aus `docs/handbuch/beispielkurs.md` und
   `beispielkurs-handout.md` – nur **eine** Quelle: Ablaufplan und Handout liegen dann im Paket, die Handbuch-PDFs
   werden von dort gebaut (keine Kopie).
6. **Kurspakete aus dem Internet:** `index.json` im öffentlichen Repo **zappotex/bonys-agents-kurspakete**
   (am 19.10.2026 auf Wunsch des Nutzers angelegt: README, Lizenz CC BY-SA 4.0, leere Liste, Ordner `pakete/`),
   Download nur HTTPS, Größe und SHA-256 müssen passen; später zusätzlich signiert (Sitzung 2).
7. **Kostenloses Modell (Hermes-Doku geprüft am 18.10.2026):** Standardweg in allen Unterlagen: `hermes setup`
   → oberster Punkt „Nous“ → Free-Modell (vom Nutzer getestet; die Doku beschreibt Nous Portal als Abo mit
   OAuth-Anmeldung ohne API-Schlüssel, `hermes setup --portal`; kostenlose Modelle nennt sie nicht – im Text daher
   „eigenes Nous-Konto, kostenloses Modell wählen“). Alternative: OpenRouter (`:free`-Modell, eigener
   API-Schlüssel in `~/.hermes/.env`). Befehle laut Doku: `hermes`, `hermes --tui`, `hermes model`,
   `hermes doctor`, `/tools`, `/help`, `/model`; Mindestkontext 64K. Anbieter und Modell stehen in
   `~/.hermes/config.yaml` (`model.provider`, `model.default`) – die Prüfung „Hermes eingerichtet“ liest nur diese
   Einträge, nie `.env` oder `auth.json`.

8. **Startzustand je Lektion (Sitzung 2): Mischform.** Beim ersten Betreten einer Lektion läuft ihr Startskript
   (falls vorhanden) im Agent-PC, danach entsteht ein **interner qcow2-Schnappschuss nur der Festplatte**
   (`bonys-paket-<id>-<NN>`; laufend per Monitor `snapshot_blkdev_internal disk0` nach `sync` im Gast, sonst
   `qemu-img snapshot -c`). Gründe: Platz – nur die danach geänderten Blöcke; Zuverlässigkeit – unabhängig davon,
   was im Gast kaputtgespielt wurde; und er behält, was der Teilnehmer vorher selbst eingerichtet hat (z. B.
   Hermes-Anmeldung mit eigenem Konto), was kein Skript nachbauen könnte. Alle Startzustände schon beim Kursstart
   anzulegen geht aus genau diesem Grund nicht. Zurücksetzen: herunterfahren (nach 90 s hart),
   `qemu-img snapshot -a`, Startzustände späterer Lektionen löschen, neu starten. Gesichert wird erst, wenn der
   Agent-PC fertig eingerichtet ist. `qemu-img resize` geht weiter (getestet mit 8.2); beim Kopieren der Platte
   (Verschieben auf anderes Laufwerk, unabhängig machen, Vorlage) gehen die Schnappschüsse verloren – sie
   entstehen beim nächsten Betreten neu.
9. **Prüf- und Startskripte nur über den Gast-Agent** (`guest-exec` mit `timeout -k 3 N`, `runuser -u <benutzer>`,
   `env -i`, Skript über stdin an `bash -s`/`python3 -`), **kein SSH-Rückfallweg**. Ausgabe wird verworfen.
   Eingebaute Prüfungen (`agent-pc-laeuft`, `vorlage-vorhanden`) prüft die App selbst.
10. **Vertrauen:** mitgeliefert oder `pruefsummen.txt` + `.minisig` (Release-Schlüssel, `UPDATE_PUBLIC_KEY`) und
    Prüfsummen passen genau → „Geprüftes Kurspaket“. Sonst vor dem ersten Start Hinweis mit Skriptliste; die
    Zustimmung (`Fortschritt.skripte_erlaubt`) gilt für die SHA-256 über alle Skripte. Signieren der mitgelieferten
    bzw. ins Repo hochgeladenen Pakete: in Sitzung 4 über die Release-Aktion (minisign, wie SHA256SUMS).

## Sicherheitsregeln

- Keine API-Keys, Tokens, Passwörter oder Zugangsdaten in Kurspaketen; Editor prüft vor Speichern/Export wie beim
  `.bonys`-Export und blockiert.
- Prüf- und Startskripte laufen **nur im Agent-PC** (Gast-Agent), nie auf dem eigenen Rechner. Entpackte Skripte
  sind nicht ausführbar (0644). Tests sichern ab, dass kein Code-Pfad ein Paket-Skript lokal startet.
- Prüfergebnis nur „geschafft / noch nicht“ mit Hinweistext aus dem Paket, keine Ausgabe des Skripts; Zeitlimit.
- Fremde Pakete: vor dem ersten Start Hinweis „Dieses Kurspaket führt Skripte im Agent-PC aus“ + Skriptliste.
- Entpacken: keine absoluten Pfade, kein `..`, keine Links/Sonderdateien, Grenzen (200 MB gesamt, 25 MB je Datei,
  2000 Dateien, Tiefe 8), nur erlaubte Endungen, echte Bytes zählen (ZIP-Bombe).
- Markdown ohne HTML, Bilder nur aus dem Paket, Links nur https und nur nach Klick im Browser.
- Kursleiter sehen pro Teilnehmer nur Lektion und „geschafft / noch nicht“, nur solange der Kurs läuft.
- Kein sudo und keine Programminstallation ohne Rückfrage; Geheimnisse nie im Klartext; nur offizielle Quellen.

## Sitzungsplan

**Sitzung 1 – Format, Bibliothek, Anzeige:** Format + Schema + Validierung + Entpack-Schutz; Bibliothek
„Kurspakete“ (Import Datei/Drag & Drop, Löschen, Aktualisieren, optional Internet); Anleitungs-Fenster mit
Zurück/Weiter/Fortschritt; Selbstlern-Modus (Agent-PC aus Rezept/Vorlage, Fortschritt).

**Sitzung 2 – Startzustände, Prüfaufgaben, Quiz:** Startzustand je Lektion (Schnappschuss oder Startskript),
„Lektion zurücksetzen“, „Zu Lektion X springen“ mit Warnung; Prüfungen nur im Agent-PC mit Zeitlimit; Hinweis bei
fremden Paketen, optional Signatur/„geprüftes Kurspaket“; Quiz.

**Sitzung 3 – Editor (Kursleiter):** anlegen/bearbeiten, Lektionen/Blöcke, Markdown-Vorschau, Screenshot,
Prüfskript-Vorlagen („Datei existiert“, „Dienst läuft“, „Hermes eingerichtet“); Startzustand übernehmen;
Speichern/Laden/Duplizieren/Version; Geheimnis-Prüfung; PDF für Ablaufplan und Handout; „Kurspaket prüfen“.

**Sitzung 4 – Kurse, Beispielpakete, Abschluss:** Kurspaket beim Bony-Netz-Kurs und bei der Schulung wählen,
Teilnehmer bekommen es automatisch, Kursansicht mit Lektion + „geschafft / noch nicht“; Beispielpaket „Einführung
in Hermes Agent“ vollständig + fünf Entwürfe; Editionstrennung, `docs/editionen.md`; Handbücher, Glossar,
Bildschirmfotos (Vorführmodus + Texterkennung), README, `docs/kurspaket-format.md`; Tests; echter Test;
pytest/ruff beider Editionen, Minor-Version, .deb (Installation nach Rückfrage), Commit. Release nach OK.

## Vorschläge aus dem Entwurf `kurse/01-ki-agenten-fuer-einsteiger/kurs.md`

**Vom Nutzer am 19.10.2026 alle freigegeben.** In Sitzung 4 einarbeiten, danach die Datei (samt Ordner
`kurse/`) entfernen.

1. **Quizfragen** je Lektion übernehmen: Agent vs. Chatbot (Block 2), Wo liegen deine Dateien (Block 2), Benutzer
   im Agent-PC heißt `agent` (Block 3), Was zeigt `/tools` (Block 3), Was ist eine gute Aufgabe (Block 4),
   Agent hat etwas kaputtgemacht → aus Vorlage neu (Block 7).
2. **Prüfaufgaben:** Block 3 „Agent-PC läuft“ (eingebaut) und „Hermes eingerichtet“ (nur `model.provider`/
   `model.default` in `config.yaml`), Übung 1 „`~/Kurs/einkaufsliste.txt` existiert, enthält Käse“.
3. **Zusatz-Lektion „Zurücksetzen und Vorlage“** (Agent-PC stoppen/starten, frische Vorlage, zweiten Agent-PC
   daraus) – im Selbstlern-Modus als Lektion 9, im 2-Stunden-Kurs als optionaler Block (Zeitplan bleibt).
   Dazu Lernziel 6 „einen Agent-PC zurücksetzen oder aus einer Vorlage neu erstellen“; Prüfung „Vorlage vorhanden“.
4. **Hermes-Befehle** ergänzen: `hermes --tui` (empfohlene Oberfläche), `/tools`, `/help`, `/model`; Hinweis
   „mindestens 64K Kontext“ und „kostenlose Modelle haben Nutzungsgrenzen“ in die Kursleitungs-Notizen.
5. **Steckbrief:** Voraussetzungen „mind. 8 GB RAM, 40 GB frei“, „Kosten: keine (kostenloses Modell)“.
6. **Kursleitungs-Notizen:** Einstieg „Wer hat schon ChatGPT benutzt?“; Botschaft „Im Agent-PC darf man Fehler
   machen“; Prompt-Injection kurz als Beispiel in Block 7.
7. **Ausblick** in Block 8/Handout: Kurspaket „Hermes über Telegram steuern“, Selbstlern-Modus, Bibliothek.

## Stand

Zuletzt aktualisiert: 19.10.2026 (Sitzung 3 fertig).

### Sitzung 1
- [x] Plan `docs/dev/plan-kurspakete.md`, Auftrag in `.gitignore`
- [x] Hermes-Doku geprüft (Nous/OpenRouter, Befehle, config.yaml) – siehe Entscheidung 7
- [x] Format + Validierung + Entpack-Schutz (`kurspaket.py`), Tests (`tests/test_kurspaket.py`),
      `docs/kurspaket-format.md` mit JSON-Schema (Test prüft Beispiel und Schema gegen den Code)
- [x] Bibliothek „Kurspakete“ (`gui/kurspaket_bibliothek.py`, erster Reiter im Fenster „Kurse“; ohne Bony-Netz
      öffnet das Fenster dort, mit Bony-Netz wie bisher auf Kursleitung/Teilnahme): Import per Datei und
      Drag & Drop, Exportieren, Löschen (nicht mitgelieferte), Aktualisieren bei gleicher ID mit Rückfrage,
      „Aus dem Internet …“ (Platzhalter-Repo, Größe + SHA-256)
- [x] Anleitungs-Fenster (`gui/kurspaket_anleitung.py`): Zurück/Weiter/Abschließen, Lektionswahl, Fortschritt,
      Prüfaufgabe als Text, Kursleitungs-Notizen + Ablaufplan nur in der Kursleiter-Edition, Handout, „Immer im
      Vordergrund“, rechts am Bildschirm, Position gemerkt; Bilder nur aus dem Paket, kein HTML
- [x] Selbstlern-Modus: „Durcharbeiten“ → neuer Agent-PC (Fenster „Neuer Agent-PC“ mit Rezept, Namensvorschlag,
      passende Vorlage) oder vorhandenen wählen; Fortschritt in `kurspakete/fortschritt.json`;
      „Agent-PC zeigen“ wählt/startet ihn im Hauptfenster
- [x] Vorschläge aus dem Entwurf: alle vier Gruppen freigegeben (19.10.2026)
- [x] Repo zappotex/bonys-agents-kurspakete angelegt
- [x] Volle Tests Kursleiter-Edition: 657 grün
- Noch nicht echt getestet (nur offscreen): Durcharbeiten mit echtem Agent-PC, Drag & Drop unter Wayland/X11.
- Hinweis: `MIN_VERSION` ist 0.23.0 – Pakete mit dieser Mindestversion lehnt 0.22.1 ab, bis die Version am
  Ende erhöht wird (Tests nutzen `min_version` 0.1.0).

### Sitzung 2
- [x] Startzustände (`kurslauf.py`, Entscheidung 8), „↺ Zurücksetzen“, „Zu Lektion X springen“ (Auswahlliste:
      „Nur ansehen“ oder „Zurücksetzen“), Warnung vor Verlust eigener Dateien, „Startzustände löschen …“
- [x] Prüfaufgaben nur im Agent-PC über den Gast-Agent, Zeitlimit, Ergebnis „✓/✗ + Hinweis“ (Entscheidung 9)
- [x] Hinweis „Dieses Kurspaket führt Skripte im Agent-PC aus“ mit Skriptliste; Signaturprüfung und
      „Geprüftes Kurspaket“ (Entscheidung 10) – Signieren selbst kommt in Sitzung 4
- [x] Quiz-Dialog (beim „Weiter“ angeboten oder Knopf „Quiz“), Ergebnis nur lokal
- [x] Tests: `tests/test_kurslauf.py` (echte qcow2-Schnappschüsse mit qemu-img/qemu-io, Gast-Agent-Attrappe,
      kein Prozess auf dem Rechner), Fenster-Tests in `tests/test_kurspaket.py`
- Noch nicht echt getestet: Schnappschuss/Zurücksetzen mit laufendem echten Agent-PC, Prüfskript im echten Gast
  (`runuser`, `xdg-user-dir`) – gehört in den echten Test (Sitzung 4).

### Sitzung 3
- [x] Editor (`trainer/gui/kurspaket_editor.py`, Logik `trainer/kurspaket_editor.py`, nur Kursleiter): Knöpfe
      „Neu …“, „Bearbeiten …“, „Duplizieren …“, „Ordner öffnen …“ in der Bibliothek; eigenes Fenster mit
      Gliederung (Steckbrief, Rezept, Ablaufplan, Handout, Lektionen +/−/↑/↓), Markdown mit Vorschau, Kästen,
      Bild einfügen, Bildschirmfoto des Agent-PCs (QMP/HMP `screendump -f png`, mit leerem QEMU 8.2 getestet),
      Kursleitungs-Notizen, Zeiten, Quiz, Prüfung (Vorlagen „Datei existiert“, „Dienst läuft“, „Hermes
      eingerichtet“), Startskript
- [x] „Startzustand übernehmen“ = (a) Rezept aus einem Agent-PC (Desktop, Apps, RAM/CPU/Platte, Benutzer,
      Vorlage) und (b) Startskript aus einem Ordner im Agent-PC (z. B. `~/Kurs`, über den Gast-Agent gepackt
      gelesen, Skript packt ihn als Benutzer wieder aus) – ein Festplatten-Abbild kommt nie ins Paket
- [x] Speichern: erst Bauordner + volle Prüfung, dann Datei-Abgleich (Versteckte/`.git` bleiben, Signatur fällt
      weg); Lektionsordner werden nach Position neu nummeriert; mitgelieferte → „Eigene Fassung“ (gleiche ID)
      oder „Duplizieren“; Version erhöhen (Korrektur/Neue Inhalte/Grundlegend); eigene Skripte gelten als zugestimmt
- [x] Geheimnis-Prüfung (`kurspaket.geheimnisse_suchen`): Schlüssel/Tokens (OpenRouter, Anthropic, sk-, GitHub,
      GitLab, AWS, Google, Slack, Telegram, HF, JWT, private Schlüssel), Passwort-Zuweisungen, Zugangsdaten in
      URLs, E-Mail, Telefon, IBAN; blockiert Speichern im Editor und jeden Export (`packen`); zeigt nie den Wert
- [x] PDF für Ablaufplan/Handout mit der Handbuch-Vorlage (pandoc + typst, eigener Root-Ordner, Kurspaket-Lizenz
      statt Handbuch-Lizenz; Vorlage kommt per pyproject/spec als `trainer/resources/handbuch-vorlage` mit)
- [x] „Kurspaket prüfen“: statisch (Format, Geheimnisse, fehlende Bilder, http-Links, HTML, unbekannte/veraltete
      Apps, Vorlage, Dauer, Python-Syntax per `compile`), optional Links online, optional Test-Agent-PC: je Lektion
      `bash -n`, Startskript, Prüfung vorher (darf nicht erfüllt sein), neues optionales Format-Feld
      `pruefung.loesung` (Lösungsskript) und Prüfung danach; Schnappschuss `bonys-paket-test` und Zurücksetzen
- [x] Tests `tests/test_kurspaket_editor.py` (42), Doku `docs/kurspaket-format.md` (loesung, Geheimnis-Prüfung)
- Noch nicht echt getestet: Bildschirmfoto/Startskript übernehmen/„Kurspaket prüfen“ mit echtem Agent-PC –
  gehört in den echten Test (Sitzung 4). Handbücher/editionen.md: Abschnitt Editor kommt in Sitzung 4.

### Sitzung 4
- [ ] Kurspaket bei Kurs/Schulung, Kursansicht mit Fortschritt
- [ ] Beispielpaket Hermes vollständig, fünf Entwürfe
- [ ] Doku (editionen.md, Handbücher, Glossar, Bilder, README, kurspaket-format.md)
- [ ] Tests, echter Test, Version, .deb, Commit

### Offene Fragen an den Nutzer
- keine
