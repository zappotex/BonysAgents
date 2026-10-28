# Zusammenarbeit Phaseone ↔ Claude

## Zweck

Diese Datei ist die gemeinsame Übergabestelle für Phaseone0815 und Claude Code. Beide arbeiten am selben Repository, aber nicht im selben Chat. Deshalb wird der aktuelle Auftrag und Stand hier sichtbar dokumentiert.

## Verbindliche Arbeitsweise

1. Vor jeder Arbeit `CLAUDE.md` und diese Datei lesen.
2. Vor Beginn den Auftrag unter **Aktueller Block** mit Agent, Status und Datum eintragen.
3. Während längerer Arbeit kurze Checkpoints ergänzen.
4. Nach Abschluss echte Tests, geänderte Dateien, Risiken und den nächsten Schritt eintragen.
5. Keine Commits, Pushes, Tags, Releases, Deployments oder Serveränderungen ohne ausdrückliche Freigabe von Bony.
6. Keine Geheimnisse, Tokens, Passwörter oder privaten Daten eintragen.
7. Der aktive Bearbeiter besitzt den aktuellen Block. Der andere Agent liest und ergänzt nur Übergaben, keine konkurrierenden Änderungen.

## Aktueller Block

- **Auftrag:** Kursportal – App-Seite des Community-Katalogs (zweite Katalogquelle „Community“, standardmäßig an, klar gekennzeichnet).
- **Bearbeiter:** Claude Code
- **Koordination:** Phaseone0815
- **Status:** Umgesetzt und getestet (2026-10-28), uncommitted. Offen: echter Test mit einem veröffentlichten Testpaket (braucht Bonys Ja).
- **Grenzen:** kein Commit, Push, Tag oder Release; Deployments und Serveränderungen nur durch Bony bzw. im von Bony ausdrücklich freigegebenen Rahmen (siehe „Freigaben von Bony“).

## Freigaben von Bony (2026-10-28, im Chat erteilt)

- Der erste Block darf über die lokale Intake-Schicht hinausgehen: Moderationsmodell, lokaler Dialog, **Annahme- und Prüfdienst auf der Domain `kurse.bony23.de`** im bestehenden Docker/Caddy-Stack der Schulungsseite (eigener Dienst `portal`, Prüfung auf dem Server, Pakete bleiben Daten).
- Auslieferung wie bei Schulungsseiten-Bundles: Claude baut das Bundle, **Bony lädt es hoch und deployt selbst**.
- Claude hat auf Bonys Wunsch einen eigenen SSH-Zugang, begrenzt auf das Projektverzeichnis `bonys-schulung-web`: `docker compose ps/logs/exec portal …`, Test-Token anlegen, Upload-Tests. Entscheidungen (`entscheiden`), Deploys, `sudo`, andere Dienste und alles außerhalb nur nach Rückfrage.
- Katalog-Entscheidungen: Ort `kurse.bony23.de/katalog/`; Community-Quelle in der App standardmäßig an; mitgelieferte Paket-IDs werden abgelehnt; neue Version ersetzt die alte im Katalog.
- Test-Einreichungen, Test-Token und der SSH-Zugang bleiben auf Bonys Wunsch erst einmal bestehen.
- Veröffentlichungsschranke gilt weiter: Nichts wird ohne Bonys Ja öffentlich geschaltet (Veröffentlichen/Rücknahme am echten Server noch nicht getestet).

## Bekannter Stand (2026-10-28)

Alles uncommitted im Arbeitsbaum, nichts committet/gepusht/getaggt.

| Teil | Dateien | Stand |
|---|---|---|
| Intake | `src/bonys_agents/kurspaket_portal.py`, `tests/test_kurspaket_portal.py` | fertig, 16 Tests; Meldungen bereinigt, reservierte IDs, Katalogfelder im Bericht |
| Moderation | `kurspaket_moderation.py`, `tests/test_kurspaket_moderation.py` | fertig; hashverketteter Verlauf, menschliche Entscheidung mit Akteur und Begründung |
| Dialog | `gui/moderation_dialog.py`, `gui/main_window.py`, `tests/test_kurspaket_moderation_gui.py`, `tests/test_editions.py` | fertig; **eingebunden** (Menü ⋯ → „Kursportal: Moderation …“, nur Kursleiter-Edition), lokale Ablage `<Datenordner>/kursportal-ablage` |
| Annahme-Dienst | `packaging/kursportal-server/` (Server, Compose, Caddyfile, Bundle-Skript, README), `tests/test_kursportal_server.py` | Bundle v3 **auf Bonys Server deployt** (durch Bony); Token, Rate-Limits, Abweisung getestet |
| Katalog | `kurspaket_katalog.py`, `tests/test_kurspaket_katalog.py`, `docs/dev/plan-kursportal-katalog.md` | Server-Teil fertig und deployt; Katalog aktuell leer |
| App-Seite Katalog | `kurspaket.py` (`COMMUNITY`, `KatalogEintrag.community`, `katalog_alle`, `community_an/setzen`), `kurslauf.geprueft`, `gui/kurspaket_bibliothek.py` (`KatalogDialog` mit Schalter), `tests/test_kurspaket.py` | fertig; Community Standard an, Herkunft „Community, von der Moderation geprüft“, nie geprüft/mitgeliefert |

## Letzte Tests

- `PYTHONPATH=src build/venv/bin/python -m pytest tests/test_kursportal_server.py tests/test_kurspaket_katalog.py tests/test_kurspaket_portal.py tests/test_kurspaket_moderation.py tests/test_kurspaket_moderation_gui.py tests/test_kurspaket.py -q` → 91 bestanden; `ruff check` sauber.
- Vollständige Suite (28.10., nach App-Seite): `QT_QPA_PLATFORM=offscreen PYTHONPATH=src build/venv/bin/python -m pytest -q` → 797 bestanden, 1 übersprungen; `ruff check src tests` sauber.
- Am echten Server: 401 ohne/falsches Token, Annahme und Prüfung, Stundenlimit (5/h), Fehlversuch-Sperre, mitgelieferte ID → rejected, Katalog-Index 200, Verzeichnisliste 404, POST 405.

## Offene Risiken

- Die Prüfung entpackt fremde ZIPs auf dem öffentlichen Server (abgeschottet: internes Netz ohne Internet, read-only, nobody, Limits). Sicherheitsprüfung durch Bony steht aus.
- Fehlversuch-Sperre kann kurz auch gültige Token ausbremsen (so gebaut).
- Markdown-Anzeige von Paketdaten im Moderationsdialog nicht eigens abgesichert.
- Wird die neueste veröffentlichte Version zurückgezogen, erscheint wieder die vorherige.
- Docker-Gruppe für den Servernutzer ist root-gleichwertig; SSH-Schlüssel nach den Tests entfernen.

## Entscheidung erforderlich (Bony)

- Veröffentlichen/Rücknahme am echten Server testen (macht ein Testpaket kurz öffentlich)?
- Wann Test-Einreichungen, Test-Token und SSH-Zugang aufgeräumt werden.

## Übergabe Phaseone → Claude

Phaseone erwartet nach jedem Arbeitsblock einen vollständigen Bericht mit:

- geänderten Dateien;
- Verhalten und Sicherheitsgrenzen;
- exakten Testkommandos und Ergebnissen;
- offenen Risiken oder Abweichungen;
- Empfehlung für den nächsten Block.

## Übergabe Claude → Phaseone

Claude trägt seinen aktuellen Fortschritt und Abschlussbericht hier ein. Wenn eine Entscheidung von Bony notwendig ist, wird der Punkt als **Entscheidung erforderlich** markiert und nicht eigenständig veröffentlicht.

## Änderungsprotokoll

### 2026-10-28 – Phaseone0815

Gemeinsame Übergabedatei eingerichtet, damit Phaseone und Claude unabhängig vom Chat denselben Projektstand lesen und fortschreiben können.

### 2026-10-28 – Claude Code

Status aktualisiert: Kursportal Schritte 1–5 (server-seitig) umgesetzt, Bundle v3 durch Bony deployt; App-Seite des Community-Katalogs in Arbeit. Details und Freigaben siehe oben.

### 2026-10-28 – Claude Code (App-Seite)

Community-Quelle in der App: URL `kurse.bony23.de/katalog/index.json` (Env `BONYS_AGENTS_COMMUNITY_KATALOG` für Tests), Schalter im Dialog „Kurspakete aus dem Internet“, Fehler der Community-Quelle blockieren die offizielle Liste nicht, bei gleicher ID gewinnt der offizielle Eintrag, `kurslauf.geprueft` ist für Community immer falsch (Skript-Rückfrage bleibt). Nächster Schritt: echter Test (Testpaket veröffentlichen, in der App laden, zurückziehen) – nur mit Bonys Ja.

### 2026-10-28 – Claude Code (echter Test Veröffentlichen/Rücknahme)

Mit Bonys Ja am echten Server getestet (Testpaket `aufgaben-automatisieren` 0.1.0, aus der Test-Einreichung): approved → published → Katalog-Index und Paketdatei öffentlich (200, Prüfsumme stimmt) → App-Logik lädt es als Herkunft `community`, nicht geprüft → withdrawn → Index leer, Datei 404. Verzeichnisliste 404, POST 405. Katalog ist wieder leer; der Verlauf bleibt unveränderlich erhalten.

Befund: Das Testpaket trägt die ID eines mitgelieferten Pakets (Einreichung stammt von vor Bundle v3). `entscheiden … published` prüft reservierte IDs nicht erneut; in der App gewinnt dann der offizielle Eintrag. Empfehlung: reservierte IDs auch beim Veröffentlichen/Katalogbau prüfen (Server-Änderung, bräuchte Bundle v4 – Deploy durch Bony).

### 2026-10-28 – Claude Code (Bundle v4: reservierte IDs auch beim Veröffentlichen)

`Moderation.entscheiden(… published)` lehnt IDs mitgelieferter Pakete ab; `katalog_schreiben/erzeugen` lässt sie weg (auch ältere Einreichungen). Neuer Test in `tests/test_kurspaket_katalog.py`. Tests: 95 bestanden (Server, Katalog, Intake, Moderation, Dialog, Kurspaket), `ruff` sauber. Bundle: `~/Downloads/bonys-schulung-web-kursportal-v4.tar.gz` (SHA-256 17dbbafe…b380), **nicht deployt** – Deploy durch Bony wie bei v3 (scp + tar + deploy.sh). Offen: Test-Einreichungen/Token/SSH-Zugang aufräumen (Termin Bony).

### 2026-10-28 – Claude Code (Gesamtsuite nach Bundle v4)

`QT_QPA_PLATFORM=offscreen PYTHONPATH=src build/venv/bin/python -m pytest -q` → 798 bestanden, 1 übersprungen; `ruff check src tests` sauber. Bonys Vorgabe: Claudes SSH-Zugang, Test-Token und Test-Einreichungen bleiben bestehen, die Arbeit ist noch nicht abgeschlossen.

### 2026-10-28 – Claude Code (Bundle v4 am Server geprüft)

v4 durch Bony deployt. Am Server: Dienste `portal`/`counter`/`web` laufen, neuer Code im Container (Sperrtext vorhanden). Erneute Einreichung des Testpakets (reservierte ID) → `rejected` mit Hinweis; `withdrawn → published` → „Übergang nicht erlaubt“; Katalog weiter leer. Die Veröffentlichungssperre selbst (älteres, schon freigegebenes Paket mit reservierter ID) ist nur per Unit-Test belegt – am Server gibt es keine solche Altlast mehr. Neue Test-Einreichung `3323bac9…` (rejected) liegt in der Ablage.

### 2026-10-28 – Claude Code (echter Test mit eigener ID)

Testpaket `community-testpaket` 1.0.0 (2 Lektionen, keine Skripte/Links; liegt nur im Scratchpad, nicht im Repo): eingereicht → automatisch `approved` → `published` (Index, Datei 200, 1066 Bytes, Prüfsumme stimmt) → `KatalogDialog` zeigt „Community-Testpaket – Community“, Laden ergibt Herkunft `community` („Community, von der Moderation geprüft“), `geprueft=False` → `withdrawn` (Index leer, Datei 404). Der Ablauf Einreichen → Veröffentlichen → App → Rücknahme ist damit am echten Server belegt. Test-Einreichung `2f247ca0…` bleibt in der Ablage (Verlauf unveränderlich).

### 2026-10-28 – Claude Code (Moderationsdialog im Hauptfenster)

Menüpunkt „Kursportal: Moderation …“ in der Kursleiter-Edition (Anwender-Edition: nicht vorhanden, per Test belegt). Der Dialog arbeitet auf einer **lokalen** Ablage dieses Rechners (IDs der mitgelieferten Pakete gesperrt) und ändert den Online-Katalog nicht; neu: Knopf „Paketdatei prüfen …“ nimmt eine `.bonyspaket`-Datei als Daten in die lokale Ablage auf (nichts wird ausgeführt). Die Moderation der Online-Einreichungen läuft weiter per Server-Befehl (`entscheiden`); eine Anbindung des Dialogs an den Server gibt es nicht und wäre ein eigener Block.
Gefundener Fehler behoben: Lambda-Verbindung mit `self` hielt den Dialog bis zum Programmende fest → Absturz (Segfault) beim Beenden bei zwei Dialog-Instanzen; jetzt Slot mit `sender()`. Vollständige Suite: 800 bestanden, 1 übersprungen, `ruff` sauber, Exit-Code 0.

### 2026-10-28 – Claude Code (Commit)

Auf Bonys Ja lokal committet (`1757e8b`, 26 Dateien), **nicht gepusht**, kein Tag/Release. Nicht enthalten: `AUFGABE-*.md` und die Kursleiter-Notiz im Projektstamm (nicht Teil dieses Blocks). Privater Pfad in der Server-README durch Platzhalter ersetzt.
