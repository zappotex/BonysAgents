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

- **Auftrag:** „Muss vor 1.0“ aus `docs/review-1.0-teil2.md` umsetzen (Bony, 28.10.2026: „erledige muss vor 1.0“).
- **Bearbeiter:** Claude Code
- **Koordination:** Phaseone0815
- **Status:** umgesetzt in drei Repos, **nichts committet, nichts deployt** (siehe Protokoll unten).
- **Grenzen:** Commit/Push je Repo nur nach Bonys Ja; Zentrale-Update auf dem Server macht Bony (`git pull` + `install.sh`); Bony's-VPN- und Agents-Release nur nach Freigabe.

## Freigaben von Bony (2026-10-28, im Chat erteilt)

- Der erste Block darf über die lokale Intake-Schicht hinausgehen: Moderationsmodell, lokaler Dialog, **Annahme- und Prüfdienst auf der Domain `kurse.bony23.de`** im bestehenden Docker/Caddy-Stack der Schulungsseite (eigener Dienst `portal`, Prüfung auf dem Server, Pakete bleiben Daten).
- Auslieferung wie bei Schulungsseiten-Bundles: Claude baut das Bundle, **Bony lädt es hoch und deployt selbst**.
- Claude hat auf Bonys Wunsch einen eigenen SSH-Zugang, begrenzt auf das Projektverzeichnis `bonys-schulung-web`: `docker compose ps/logs/exec portal …`, Test-Token anlegen, Upload-Tests. Entscheidungen (`entscheiden`), Deploys, `sudo`, andere Dienste und alles außerhalb nur nach Rückfrage.
- Katalog-Entscheidungen: Ort `kurse.bony23.de/katalog/`; Community-Quelle in der App standardmäßig an; mitgelieferte Paket-IDs werden abgelehnt; neue Version ersetzt die alte im Katalog.
- Test-Einreichungen und Test-Token wurden am 2026-10-28 auf Bonys Wunsch gelöscht; der SSH-Zugang für Claude bleibt vorerst bestehen.
- Veröffentlichungsschranke gilt weiter: Nichts wird ohne Bonys Ja öffentlich geschaltet (Veröffentlichen/Rücknahme am echten Server noch nicht getestet).

## Bekannter Stand (2026-10-28)

Alles uncommitted im Arbeitsbaum, nichts committet/gepusht/getaggt.

| Teil | Dateien | Stand |
|---|---|---|
| Intake | `src/bonys_agents/kurspaket_portal.py`, `tests/test_kurspaket_portal.py` | fertig, 16 Tests; Meldungen bereinigt, reservierte IDs, Katalogfelder im Bericht |
| Moderation | `kurspaket_moderation.py`, `tests/test_kurspaket_moderation.py` | fertig; hashverketteter Verlauf, menschliche Entscheidung mit Akteur und Begründung |
| Dialog | `gui/moderation_dialog.py` (lokal + online), `kurspaket_moderation_client.py`, `gui/main_window.py`, `tests/test_kurspaket_moderation_gui.py`, `tests/test_editions.py` | fertig; **eingebunden** (Menü ⋯ → „Kursportal: Moderation …“, nur Kursleiter-Edition), lokale Ablage `<Datenordner>/kursportal-ablage` |
| Annahme-Dienst | `packaging/kursportal-server/` (Server, Compose, Caddyfile, Bundle-Skript, README), `tests/test_kursportal_server.py` | Bundle v3 **auf Bonys Server deployt** (durch Bony); Token, Rate-Limits, Abweisung getestet |
| Katalog | `kurspaket_katalog.py`, `tests/test_kurspaket_katalog.py`, `docs/dev/plan-kursportal-katalog.md` | Server-Teil fertig und deployt; Katalog aktuell leer |
| App-Seite Katalog | `kurspaket.py` (`COMMUNITY`, `KatalogEintrag.community`, `katalog_alle`, `community_an/setzen`), `kurslauf.geprueft`, `gui/kurspaket_bibliothek.py` (`KatalogDialog` mit Schalter), `tests/test_kurspaket.py` | fertig; Community Standard **aus** (seit 28.10., nach einmaliger Zustimmung), Herkunft „Community, von der Moderation geprüft“, nie geprüft/mitgeliefert |

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

- Prüfliste durchgesehen und entschieden (28.10.2026, siehe Abschnitt 5 der Prüfliste): Punkte 1–15 und alle neun Restrisiken vertretbar, kein Einreicher-Token vorerst, Moderator nur Bony, SSH-Zugang von Claude bleibt bis nach Bonys App-Test.
- Online-Dialog der App von Bony am echten Server getestet (28.10.2026, siehe Protokoll); Katalogeintrag in der App von Bony bestätigt; offen: SSH-Zugang von Claude bis Bonys „fertig“.

## Neue Produktideen

### Kurs „Stricken lernen"

- Entwurf liegt unter `kurspakete/stricken-lernen/`.
- Version `0.1.0`, aktuell `entwurf: true`.
- Fünf Lektionen, Ablaufplan, Handout und zwei Quizdateien.
- Die praktische Tätigkeit findet mit echten Nadeln und Garn statt; Bony's Agents begleitet digital.
- ElevenLabs-Sprechprobe mit Voice-ID `SfNQWfFVL6TQ3DIRvFyM` gefällt Bony.
- Audio ist geplant, aber noch nicht in das Kurspaket eingebaut. Das Dateiformat muss vorher geprüft werden.

### Musik oder Radio beim privaten Lernen

- Spätere optionale Audioebene neben dem Kurs.
- Bewusste Aktivierung, keine automatische Wiedergabe.
- Lokale Musik oder sauber unterstützte Streams prüfen.
- Pause, Lautstärke und Quellenwechsel; Audio darf Kursanweisungen nicht überdecken.
- Noch kein aktueller Programmierauftrag.

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

### 2026-10-28 – Claude Code (Push)

Auf Bonys Ja gepusht: `f4fa626..c5b1d66` auf `main` (`zappotex/BonysAgents`). Kein Tag, kein Release, keine Auslieferung an Nutzer. Das Kursportal (Intake, Moderation, Annahme-Dienst, Community-Katalog, App-Seite, eingebundener Moderationsdialog) ist damit öffentlich im Repository; der Server-Betrieb bleibt unverändert (Bundle v4 durch Bony deployt, Katalog leer). Offen: Sicherheitsprüfung des Servers durch Bony; Termin zum Aufräumen von Test-Einreichungen, Test-Token und SSH-Zugang (bleiben vorerst bestehen).

### 2026-10-28 – Claude Code (Aufräumen)

Auf Bonys Auftrag am Server gelöscht: alle 10 Test-Einreichungen (sämtlich vom Test-Token, vorher geprüft) samt Verläufen und das Test-Token `bony-test` (`tokens.json` leer). Danach: Liste leer, Einreichen mit dem alten Token → 401, Katalog weiter leer. Das Token-Duplikat im Scratchpad wurde ebenfalls entfernt. **Der Server hat jetzt kein gültiges Einreicher-Token mehr**; für weitere Tests oder echte Einreicher: `token-neu <name>`. Der SSH-Zugang für Claude bleibt auf Bonys Wunsch bestehen; Entfernen des Schlüssels ist noch offen.

### 2026-10-28 – Claude Code (Moderations-Schnittstelle, Phase 1)

Lokal umgesetzt, nicht committet, nicht deployt, **kein Bundle gebaut**:
- `kurspaket_moderation.py`: Schreibsperre je Einreichung (`fcntl.flock` + Thread-Sperre); Prüfen und Anhängen in `entscheiden` bilden eine Einheit. Test mit 8 gleichzeitigen Entscheidungen (genau eine gewinnt, Kette gültig); ohne Sperre scheitert er in 16 von 20 Läufen.
- `packaging/kursportal-server/portal_server.py`: Moderator-Token (`moderatoren.json`, nur Hash, Rechte 600), `GET /moderation/liste` und `/moderation/einreichung/<id>` (feste Felder, bereinigte Texte, kein Dateiname/Hash/Fundwert, `kette_ok`), eigene Fehlversuchs- und Rate-Limits (10/Min, 60/Min), Einreicher-Token → 403, Moderator-Token auf `/einreichen` → 401. Neue Befehle: `moderator-neu|-liste|-entfernen`, `token-liste|-entfernen`.
- `stack/Caddyfile`: Route `GET /moderation/*` zum Portal (`caddy validate` → gültig).
- Tests: `tests/test_kursportal_server.py` (13), `tests/test_kurspaket_moderation.py`; vollständige Suite 807 bestanden, 1 übersprungen, `ruff` sauber.
Offen: Phase 2 (`POST /moderation/entscheiden/<id>`, Akteur vom Token), dann Client/Dialog, Original ansehen, Bundle v5. Die Sicherheitsprüfliste (`docs/dev/pruefliste-kursportal-server.md`) ist vor dem Deploy um die Moderationsschnittstelle zu erweitern. Noch nicht am echten Server oder in einem lokalen Container-Stack durchgespielt.

### 2026-10-28 – Claude Code (Moderations-Schnittstelle, Phase 2)

`POST /moderation/entscheiden/<id>` (Body `{"nach","begruendung"}`, ≤ 16 KiB): Akteur ist der Moderator des Tokens (ein `akteur` im Body wird ignoriert); Fehler 400/401/403/404/409 (Übergang nicht erlaubt, reservierte ID)/411/413/422/429; nach Erfolg Katalogabgleich (`katalog_ok` in der Antwort). Caddy: `POST /moderation/entscheiden/*` mit 16-KB-Grenze (`caddy validate` gültig). Tests: `tests/test_kursportal_server.py` 17 grün (4 neue); weder Server noch Container-Stack noch echter Server durchgespielt.

### 2026-10-28 – Claude Code (Moderations-Schnittstelle, Phase 3)

Client `kurspaket_moderation_client.py` (nur HTTPS bzw. 127.0.0.1, 10 s Zeitlimit, 2 MiB Antwortgrenze, keine Weiterleitungen, Schema- und Zeichenbereinigung; Token in `kursportal-moderator.json` mit Rechten 600, getrennt von den Einstellungen; Token wird erst nach erfolgreicher Verbindung gespeichert, ein abgelehntes verworfen). Dialog: Umschalter „Lokal / Online“, Aktualisieren, Abmelden; Akteur-Feld im Online-Modus aus; Anzeige jetzt **immer Klartext** (auch lokal), Warnung bei verändertem Verlauf. Die Anfragen laufen synchron (10 s Zeitlimit) – bei einem lahmen Server friert der Dialog kurz ein; bei einem einzigen Moderator bewusst einfach gehalten. Tests: `tests/test_kurspaket_moderation_client.py` (6, gegen den echten Server-Handler auf einem lokalen Port); vollständige Suite 817 bestanden, 1 übersprungen, `ruff` sauber, 6 von 6 Läufen ohne Absturz.

### 2026-10-28 – Claude Code (Moderations-Schnittstelle, Phase 4: Inhalt ansehen)

Server: `GET /moderation/original/<id>` nur für Moderatoren, liefert die Paketdatei als `application/octet-stream`/`attachment`, nur wenn ihre SHA-256 noch zum Bericht passt (sonst 409), eigenes Limit 10 Downloads/Minute. Client: `OnlineAblage.original_bereit()` (Größen- und Prüfsummenkontrolle, temporäre Kopie wird gelöscht), `inhalt_lesen()` entpackt mit `kurspaket.entpacken` (alle Schutzgrenzen) und liest Texte und Skripte nur als bereinigten Klartext (je Datei 200 KiB, gesamt 4 MiB); Bilder und Sonstiges werden nicht geöffnet. Dialog: Knopf „Inhalt ansehen …“ (lokal und online) mit schreibgeschütztem Klartext-Fenster. Tests: 4 neue im Client-Modul, 1 neuer im Server-Modul.

### 2026-10-28 – Claude Code (Phase 5 vorbereitet: Bundle v5)

Bundle gebaut: `~/Downloads/bonys-schulung-web-kursportal-v5.tar.gz` (SHA-256 `e35269b2910a85dc451cfc061a68ee16a62b674061648253d2044774c6d18612`), **nicht deployt – Deploy und echter Test durch Bony**. Lokal im Container mit der Härtung aus `docker-compose.yml` (read-only, `cap_drop ALL`, `no-new-privileges`, Nutzer `nobody`) geprüft: 401 ohne Token, 403 mit Einreicher-Token, 200 mit Moderator-Token, Moderator-Token auf `/einreichen` → 401, Einreichung → Liste → Original (byteidentisch) → `published` (Akteur `bony`, trotz `akteur` im Body; Katalog geschrieben) → `withdrawn`; Schreiben außerhalb der Volumes scheitert. **Nicht** geprüft: der Weg über Caddy (nur `caddy validate`) und der echte Server. README um die neuen Befehle und die Schnittstelle ergänzt; Sicherheitsprüfliste um Abschnitt 6 (M1–M12) erweitert.
Für den Deploy durch Bony (wie v3/v4): `scp` des Bundles, `tar -xzf … -C bonys-schulung-web --strip-components=1`, `./deploy.sh`. Danach `docker compose exec portal python /app/server.py moderator-neu bony` (Token einmalig anzeigen, in der App unter „Kursportal: Moderation … → Online“ eingeben). Offene Entscheidung: Wer das Token bekommt, steht (nur Bony) fest; der Server hat weiterhin kein Einreicher-Token.

### 2026-10-28 – Claude Code (Bundle v5 am echten Server geprüft)

Bundle v5 von Bony deployt; Claude hat mit Bonys Ja (Test-Token, kurzes Veröffentlichen/Zurücknehmen) am echten Server über Caddy geprüft: 401 ohne Token auf `/moderation/liste`, `/moderation/entscheiden/…` und `/einreichen`; Einreicher-Token auf `/moderation/liste` → 403; Moderator-Token auf `/einreichen` → 401, auf `/moderation/liste` → 200. Testpaket eingereicht (`approved`, ohne Befunde), Original byteidentisch, Direktsprung `approved → withdrawn` → 409, `published` → Katalog zeigt den Eintrag (`community: true`), `withdrawn` → Katalog wieder leer, alte Paketdatei → 404. Ein `akteur` im Body wurde ignoriert (Akteur = Token-Name), Verlauf 5 Einträge, `kette_ok` true. Container: Nutzer `nobody`, `/app` schreibgeschützt, kein Internet (Namensauflösung scheitert). `tokens.json` und `moderatoren.json` haben nach dem Schreiben Rechte 600 (die leere Ausgangsdatei hatte 644, der Code setzt beim Schreiben 600 – kein v6 nötig). Danach aufgeräumt: Test-Einreicher- und Test-Moderator-Token entfernt, Test-Einreichung gelöscht, Katalog leer. Übrig: Moderator `bony`, kein Einreicher-Token. Der Katalog war etwa eine Minute öffentlich belegt. Eigener Fehler: Ein Aufruf von `server` über den Wrapper startete im Container einen zweiten Server, der an „Address already in use“ scheiterte; der laufende Dienst war nicht betroffen. Nicht geprüft: Online-Dialog der App gegen den echten Server (braucht Bonys Token). Kein Commit dieser Änderung.

### 2026-10-28 – Claude Code (Prüfliste mit Bony durchgegangen)

Bony hat Abschnitt 5 der Prüfliste entschieden (Punkte 1–15 in Ordnung, alle Restrisiken vertretbar, noch kein Einreicher-Token, Moderator nur Bony, SSH-Zugang bis nach dem App-Test). Zusätzlich lesend am Server per `docker inspect` bestätigt: 768 MiB, 1 CPU, 128 Prozesse, read-only, `cap_drop ALL`, `no-new-privileges`, Port nicht veröffentlicht, Netz `internal`. Nichts geändert. Nicht committet.

### 2026-10-28 – Claude Code (Online-Test der App durch Bony)

Mit Bonys Ja Test-Einreicher-Token angelegt und `community-testpaket` eingereicht (`approved`). Bony hat in der Kursleiter-Edition aus dem Quellcode (`BONYS_AGENTS_EDITION=kursleiter`; die installierte Fassung hat den Menüpunkt noch nicht) den Moderationsdialog auf „Online“ gestellt: Verbindung mit seinem Moderator-Token, Liste mit der Einreichung und „Inhalt ansehen“ funktionierten. Er hat `published` (Akteur `bony`) und danach `withdrawn` ausgelöst; Server bestätigt: Verlauf 5 Einträge, Katalog zeitweise belegt (10:42–10:49 Uhr), danach leer. **Nicht bestätigt:** ob „Community-Testpaket – Community“ im Online-Katalog der App (Kurse → Kurspakete → Aus dem Internet …) erschien. Danach aufgeräumt: Test-Einreicher-Token entfernt, Test-Einreichung gelöscht; übrig Moderator `bony`, kein Einreicher-Token. Hinweis: Der Weg zum Moderationsdialog (ⓘ-Menü) und zum Katalog (Kurse) war für Bony nicht offensichtlich – ein Hinweis im Handbuch/Tooltip wäre sinnvoll. Nicht committet.

### 2026-10-28 – Claude Code (Katalogeintrag in der App bestätigt)

Bony hat in einem zweiten Durchlauf (Test-Einreichung `approved` → `published` durch Bony 11:20 Uhr → `withdrawn` 11:20, Katalog ca. 26 Sekunden belegt) bestätigt, dass der Eintrag „Community-Testpaket – Community“ im Online-Katalog der App (Kurse → Kurspakete → Aus dem Internet …) erschien. Damit ist die ganze Kette am echten Server abgenommen: Einreichen → Moderationsdialog Online → Freigabe → Veröffentlichen → Katalog in der App → Rücknahme. Test-Einreicher-Token und Test-Einreichung sind wieder entfernt; übrig Moderator `bony`, kein Einreicher-Token, Katalog leer. SSH-Zugang von Claude bleibt auf Bonys Wunsch bestehen. Nächster Vorschlag: Release 0.28.0 mit dem Kursportal (nur auf Bonys Freigabe). Nicht committet.

### 2026-10-28 – Claude Code (Release 0.28.0 vorbereitet)

Auf Bonys Auftrag „Release 0.28.0 vorbereiten“: `__version__` 0.28.0, `CHANGELOG.md` (Community-Katalog, Kursportal-Moderation, Annahme-Server-Quelltext), `CLAUDE.md` (Stand), Handbuch-Quellen (`benutzer.md`: Community-Katalog und Hinweis auf den Schalter; `kursleiter.md`: Abschnitt „Community-Kurspakete prüfen und freigeben“ mit dem Weg ⓘ → „Kursportal: Moderation …“). Tests: 822 bestanden, 1 übersprungen (6:10 Min.), `ruff` sauber, `gitleaks` über `origin/main..HEAD` ohne Funde. **Nicht committet, kein Push, kein Tag.** Hinweis für Bony: Der Community-Katalog ist im Standard an und fragt `kurse.bony23.de` ab. Als Nächstes (jeweils Bonys Ja): Version-Commit + Push, CI abwarten, Rückfrage zum Tag `v0.28.0`.

### 2026-10-28 – Claude Code (Datenschutz-Bestandsaufnahme, Release wartet)

Bonys Auftrag: „wir müssen das auch alles rechtlich sicher, DSGVO-sicher machen“; „Ja, Bestandsaufnahme schreiben, Release wartet“. Neu: `docs/dev/datenschutz-kursportal.md` (Datenflüsse D1–D9, am Server bestätigt: Caddy ohne Zugriffsprotokoll, Portal ohne Anfragedaten im Log, Docker-Logs ohne Rotation; offene Punkte, Maßnahmen A/B/C, Fragen an eine Fachperson, Entscheidungen für Bony). Keine Rechtsberatung. **Release 0.28.0 wartet** (Version-Commit ist gepusht, CI-Fix `afc2427` gepusht, Tag nicht gesetzt). Entscheidungen offen: Community-Katalog Standard an oder aus mit Zustimmung; Verantwortlicher; Fachperson. Nicht committet.

### 2026-10-28 – Claude Code (Community-Katalog Standard aus mit Zustimmung)

Bonys Entscheidungen: Standard aus mit Zustimmung (Frage 1: „ja“), Verantwortlicher privat, Umsetzung ja. Umgesetzt (uncommitted): `kurspaket.community_an()` ist nur noch wahr, wenn Schalter **und** Zustimmung gesetzt sind (`community_zugestimmt`, `community_zustimmung_setzen`, Einstellung `community_zustimmung`; Zurücknehmen schaltet auch aus). `KatalogDialog`: Schalter „Community-Kurspakete anzeigen (fragt kurse.bony23.de an)“, beim ersten Einschalten Dialog `community_zustimmung()` (IP-Adresse sichtbar, nichts gespeichert, kein Zugriffsprotokoll, nicht von Bony's Agents signiert; Buttons „Einschalten“/„Nicht einschalten“), danach nicht mehr gefragt; ohne Zustimmung wird der Community-Server nie angefragt. Tests angepasst und neu (`test_katalog_dialog_community_fragt_vor_dem_ersten_einschalten`). CHANGELOG, Benutzerhandbuch und `docs/dev/datenschutz-kursportal.md` angepasst. Release 0.28.0 weiter nicht getaggt; offen: Datenschutzerklärung/Impressum (Bony privat: Name und Anschrift), Einreichungsbedingungen, Meldeweg, Löschkonzept, Fachperson.

### 2026-10-28 – Claude Code (Release 0.28.0 veröffentlicht; Löschkonzept, Rechtstexte, Bundle v6)

**Release 0.28.0 veröffentlicht** (Bonys ausdrückliches Ja „ja raus damit“): Tag `v0.28.0` auf `0f9ca7a`. Der erste Release-Lauf scheiterte an einem sporadischen Windows-Test (`test_share_server.py::test_info_download_and_fingerprint`, Status „fertig“ wird vom Server erst nach dem Senden gesetzt); nur der fehlgeschlagene Job wurde neu gestartet, dann Erfolg. Release-Seite vollständig (`.deb` amd64/arm64 normal und Kursleiter, `Setup.exe` beide, `.dmg` Apple-Chip/Intel beide, Handbuch-PDFs, Kurspakete, `SHA256SUMS` + `.minisig`), APT-Quelle enthält 0.28.0.

Danach auf Bonys Auftrag („mach 1 bis 4 fertig ohne nachfrage“), **alles uncommitted**:
- **Test repariert:** `tests/test_share_server.py` wartet bis zu 5 s auf den Status „fertig“.
- **Löschkonzept im Server:** `Moderation.loeschen(id, grund, akteur)` (fester Grund `art17|rechtsverstoss|abgelaufen|sonstiges`, menschlicher Akteur, nicht bei `published`, Löschprotokoll `ablage/geloescht.jsonl` nur mit Zeit, ID, Grund, Akteur) und `aelter_als(tage)`; Server-Kommandos `loeschen ID GRUND AKTEUR` und `alt TAGE`; Logrotation für den Portal-Dienst (`max-size 5m`, 3 Dateien); README um „Löschen“ ergänzt. Tests: 3 neu. Die vollständige Suite: 826 bestanden, 1 übersprungen, `ruff` sauber.
- **Bundle v6 gebaut:** `~/Downloads/bonys-schulung-web-kursportal-v6.tar.gz` (SHA-256 `e6fad080746165eb9560704a124d6556b6d60c3784274057da3e5d7aa29b8ca9`), **nicht deployt** (Deploy durch Bony). Lokal im Container mit der Härtung getestet: Einreichen → `loeschen … art17` → Liste leer, Löschprotokoll ohne Namen/Texte, `alt 90` läuft.
- **Rechtstexte (ENTWÜRFE, keine Rechtsberatung)** unter `docs/recht/kursportal/`: Datenschutzerklärung, Impressum, Einreichungsbedingungen, Meldeweg, README mit Fragen an die Fachperson. Platzhalter `<NAME>`, `<ANSCHRIFT>`, `<KONTAKT-E-MAIL>`, `<HOSTER>` trägt Bony selbst ein, nicht im Repository.
Offen: Bonys Durchsicht der Entwürfe, Fachperson, Deploy von Bundle v6, Datenschutzerklärung und Impressum auf `kurse.bony23.de` bereitstellen und in der App verlinken, Log-Rotation für den `web`-Dienst (Schulungsstack, Bonys Entscheidung), erstes Einreicher-Token (nur auf Bonys Freigabe).

### 2026-10-28 – Claude Code (v6 deployt, Commit b4927cc, Datenschutzseite vorbereitet)

Bonys Ja „committen und pushen“: Commit `b4927cc` gepusht, CI grün. Bony deployte Bundle v6; lesend geprüft: Container laufen, `loeschen`/`alt 90` vorhanden (ungültige ID wird abgelehnt), Portal-Logs `json-file 5m × 3`, read-only, 768 MiB, `/katalog/index.json` 200, `/moderation/liste` ohne Token 401, Katalog 0, Moderator `bony`, kein Einreicher-Token.

Danach Bonys Auftrag „Datenschutzseite und Verlinkung vorbereiten“ (**uncommitted**): Caddy liefert `/datenschutz`, `/impressum`, `/einreichungsbedingungen`, `/meldeweg` aus `./rechtstexte/<seite>.html` (neues Volume, nur lesend; eigene CSP mit `style-src 'unsafe-inline'`, sonst bleibt alles `default-src 'none'`); `deploy.sh` legt nur fehlende Seiten als Platzhalter an und überschreibt nie; die App verlinkt `kurspaket.DATENSCHUTZ_URL` im Zustimmungsdialog (Rich Text) und im Katalogfenster. Getestet: Caddyfile gültig; im lokalen Caddy-Container 200 mit eigener CSP für eine Testseite, 404 für nicht vorhandene Seiten und fremde Pfade; Platzhalter-Logik überschreibt vorhandene Dateien nicht; `tests/test_kurspaket.py` 62 bestanden (Link-Assert neu), `ruff` sauber. Die fertigen Texte legt Bony selbst in `rechtstexte/` auf dem Server ab. Bundle v7 wird nach der Vollsuite gebaut, Deploy durch Bony.

### 2026-10-28 – Claude Code (Stand nach Commit c9a43c7 und Bundle v7)

Nachgetragen (lesend geprüft): Commit `c9a43c7` (Rechtstexte-Seiten, Datenschutz-Link in der App) ist gepusht, CI grün. Bundle v7 gebaut (`~/Downloads/bonys-schulung-web-kursportal-v7.tar.gz`, SHA-256 `bb62ff19…7c12d`) und auf dem Server aktiv: `/datenschutz` und `/impressum` liefern 200, derzeit mit dem Platzhalter „Diese Seite wird gerade vorbereitet.“; `/katalog/index.json` 200. Offen: Bony legt die fertigen Texte in `rechtstexte/` auf dem Server ab (Durchsicht der Entwürfe, Fachperson); `web`-Logrotation (Bonys Entscheidung); erstes Einreicher-Token nur auf Freigabe; SSH-Zugang von Claude bis Bonys „fertig“; ungeklärte Dateien `AUFGABE-handbuch.md`, `AUFGABE-tooltips.md` und die Kursleiter-Notiz im Projektstamm.
Bonys Antworten (28.10. abends): Rechtstexte macht Bony später; vorerst kein Einreicher-Token (Bony einziger Nutzer); Claudes SSH-Zugang bleibt; `AUFGABE-handbuch.md` und `AUFGABE-tooltips.md` gelöscht (waren erledigt). Logrotation `web`: erklärt, Entscheidung offen.

### 2026-10-28 – Claude Code (Bundle v8: Logrotation für alle Dienste)

Bonys Ja „bau bundle v8“: `stack/docker-compose.yml` begrenzt jetzt auch die Logs von `counter` und `web` (`json-file`, 5 MB × 3, wie `portal`). Neuer Test `test_alle_dienste_begrenzen_ihre_container_logs` (ohne die Änderung rot). Tests: `PYTHONPATH=src build/venv/bin/python -m pytest tests/test_kursportal_server.py -q` → 20 bestanden; `ruff check src tests` sauber; `docker compose config -q` gültig. Bundle `~/Downloads/bonys-schulung-web-kursportal-v8.tar.gz` (SHA-256 `2637de21…407f`), Unterschied zu v7 nur `docker-compose.yml`. **Nicht deployt** (Deploy durch Bony), nicht committet. Beim Deploy werden alle Container neu erstellt (kurze Unterbrechung der Schulungsseite, Sekunden).

### 2026-10-28 – Claude Code (Bundle v8 am Server geprüft)

Bundle v8 von Bony deployt (erster Versuch ohne Entpacken, zweiter vollständig). Lesend am Server bestätigt: alle drei Container laufen, read-only, Logs `json-file` 5 MB × 3 bei `web`, `counter` und `portal`; `schulung.bony23.de` 200, `/datenschutz` 200, `/katalog/index.json` 200, `/moderation/liste` ohne Token 401. Nicht committet.

### 2026-10-28 – Claude Code (Auftrag A: Durchsicht Teil 2 fertig)

Bericht `docs/review-1.0-teil2.md` (nur geprüft, nichts am Code/Server geändert; fünf getrennte Prüfungen, wichtigste Funde selbst am Code nachgeprüft). Tests: vollständige Suite 827 bestanden, 1 übersprungen; `ruff` sauber; `gitleaks` nur Fehlalarme (Test-Geheimnisse). Tests der Zentrale nicht gelaufen (`fastapi` fehlt). Ergebnis: **noch nicht reif für 1.0** – Isolation im Kurs (Kursleiter-Regel alle Ports, Rollenfälschung im Kursraum, eigener Rechner im Netz ohne shields-up), IP-Adressen im Zugriffsprotokoll der Zentrale, fehlende Rechtstexte der Zentrale; neun „Muss“-Punkte, Aufteilung in fünf Sitzungen. **Nicht committet** – Commit nur nach Bonys OK. Danach geplant: Tor-AppArmor Variante B (Bonys Entscheidung).

### 2026-10-28 – Claude Code (Muss vor 1.0 umgesetzt, nicht committet)

Repos `bonys-agents`, `bonys-netz` (Zentrale + Baustein 0.2.1), `bonys-vpn`. Umgesetzt: Kursleiter-Netzregel nur Port 5959 + `x11vnc -allow` Kursleiter-Rechner; Kursleiter an Identität (`kursleiter_identitaet`), kein `canUpdateOwnMetadata`; `--shields-up` in Bony's VPN + Hinweis Tailscale-App; Zentrale ohne Zugriffsprotokoll, Logrotation aller Dienste; Karten 15 min, `auto_create: false`, Raum bei Pause gelöscht, RemoveParticipant; Regel-Abgleich alle 30 s; Totmannschalter `bonys-hilfe-wache`, Hilfe endet beim Verlassen; Skript-Zustimmung vor jeder Ausführung (inkl. Benutzer), Dialog mit root/Netz/Zugangsdaten und „Skripte ansehen“; Baustein ohne Weiterleitung/http; IP-Hash 24 h, Teilnahmen beim Kursende gelöscht, Kurse enden 7 Tage nach Code-Ablauf, beendete nach 30 Tagen gelöscht; Datenschutzhinweis im Bony-Netz-Dialog, Entwurf `docs/recht/bony-netz/`, TKG-Frage. Tests: Agents 838 bestanden, 1 übersprungen, ruff sauber; Zentrale 9; Baustein 9 (2 übersprungen: shellcheck fehlt, kein Testserver); VPN 191 bestanden, 5 Fehler wie vor der Änderung (lokale Umgebung, CI grün). Offen: Commits/Pushes (Bony), Zentrale-Update auf dem Server (Bony), Releases.

### 2026-10-28 – Claude Code (Zentrale 0.2.1 auf dem Server)

Bony hat die Zentrale aus einem frischen Klon (`~/bonys-netz`, Commit `e0e9b36`) mit `install.sh` aktualisiert; der alte Ordner `~/bonys-netz-server` war kein Git-Klon und wird nicht mehr gebraucht. Von außen geprüft: `/api/v1/info` Version 0.2.1, `/health` headscale true, regeln_aktuell true, `/docs` `/redoc` `/openapi.json` 404, ohne Token 401. Nicht geprüft (kein Zugang zu diesem Server): Container-Protokolle, `livekit.yaml` (`auto_create`). Offen: echter Kurstest mit der neuen App (Quellcode), danach Releases.
- Am Server von Bony bestätigt: `livekit.yaml` Zeile 11 `auto_create: false`; Logrotation 3 × 5 MB bei zentrale, headscale, livekit, caddy.

### 2026-10-29 – Claude Code (Hilfe-Fehler gefunden)

Bonys echter Test: „Bildschirmfreigabe nicht gestartet“. Ursache im Test-Agent-PC `aa-test` nachgestellt (mit Bonys Ja gestartet, danach wieder aus): `-auth guess` verträgt sich nicht mit `-nocmds` – Fehler seit 0.22.0, Hilfe hat nie funktioniert. Fix: Xauthority aus dem Xorg-Aufruf (Rückfall lightdm/`~/.Xauthority`), `-quiet` entfernt, Grund aus dem Agent-PC in der Meldung. Im Agent-PC geprüft: x11vnc lauscht, `-allow` weist fremde Adresse ab („denying client … does not match“), Totmannschalter stoppt ohne Klopfen nach ca. 21 s und löscht den Passwortordner. Nicht committet.

### 2026-10-29 – Claude Code (Release 0.28.1 und Bony's VPN 1.1.0)

Auf Bonys Ja veröffentlicht: Bony's Agents `v0.28.1` (auf `3b9ed9d`, 26 Dateien, APT) und Bony's VPN `v1.1.0` (auf `a074e48`, APT). Vorher CI rot durch zwei nur lokal grüne Tests (macOS-`stat`, vorhandene Xauthority) – repariert. Offen: echter Kurstest mit 0.28.1, Tor-AppArmor (Variante B).

### 2026-10-29 – Claude Code (Tor-AppArmor Variante B)

Bonys Auftrag „mach die Tor-Korrektur Variante B“. Befund: Debian 13 liefert torbrowser-launcher 0.3.7 ohne `userns,` im Profil (Warnleiste), ab 0.3.9 steht es drin. Umgesetzt (`apps.TOR_APPARMOR`): bei Installation und bei „Agent-PC aktualisieren“ `userns,` in `/etc/apparmor.d/local/torbrowser.Browser.firefox`, nur wenn es im Profil fehlt und AppArmor ≥ 4; lädt das Profil nicht, wird die Zeile wieder entfernt. Debian-13-Profil mit der Zeile per `apparmor_parser -Q -K` übersetzt (ok). Test mit nachgebautem apparmor_parser (4 Fälle). Nicht committet; nicht in einem echten Agent-PC mit Tor Browser geprüft.

### 2026-10-29 – Claude Code (Passwortfrage beim Start)

Bony: Beim Start eines Agent-PCs fragt die App nach dem Passwort „für SSH“ – verunsichert Nutzer. Ursache: Gast-Agent antwortet beim Hochfahren noch nicht, `guest_run`, `stream`, `vpnlink`, `netz.nachtraeglich_verbinden` fragten sofort. Neu: `VM.gast_agent_abwarten` (bis 150 s nach dem Start), danach erst `NeedsPassword` mit verständlichem Text `vm.GAST_AGENT_FEHLT`. Tests ergänzt. Nicht committet.
- Echt geprüft in tor-test (Debian 13, torbrowser-launcher 0.3.7, AppArmor 4.1): vorher `DENIED userns_create profile=torbrowser_firefox`, nach der Korrektur Namensraum erlaubt; zweiter Lauf ändert nichts.

### 2026-10-29 – Bony (echter Kurstest)

Bony hat die Kursfunktionen mit 0.28.1 auf zwei Rechnern getestet: „alles hat funktioniert, der Bildschirm war bei Helfen verfügbar“. Damit ist die Hilfe über das Bony-Netz erstmals echt bestätigt (Zentrale 0.2.1, `-allow`, Rollen über Identität).
- Getestet: Hilfe anfordern, annehmen, Bildschirm sichtbar, beenden. **Noch offen** für den nächsten Probekurs: Teilnehmer-App hart beenden (Totmannschalter ~30 s), Kurs > 15 min (Kartenerneuerung), Teilnehmer entfernen (sofort raus).

### 2026-10-29 – Claude Code (Release 0.28.2)

Veröffentlicht (Bonys Freigabe ohne weitere Rückfrage): Tag `v0.28.2` auf `aadcbb9` – Tor-Browser-Sandbox (echt in tor-test geprüft), keine Passwortfrage beim Hochfahren. Windows-Testjob im Release-Lauf wegen Zeitlimit abgebrochen, neu gestartet, grün; 26 Dateien, APT 0.28.2. Offen: Probekurs (Totmannschalter, Kurs > 15 min, Entfernen).

### 2026-10-29 – Phaseone0815

Abschnitt „Neue Produktideen“ ergänzt: Strickkurs, geplante ElevenLabs-Audioebene und spätere Musik-/Radio-Idee.

### 2026-10-29 – Claude Code (STATUS wiederhergestellt)

Phaseones Ergänzung hatte die Datei auf einer veralteten Fassung (Stand 0.27.1) neu geschrieben, das Protokoll vom 28./29.10. fehlte. Auf Bonys Ja die Fassung aus `8e4f511` wiederhergestellt und Phaseones Abschnitt „Neue Produktideen“ übernommen. **Bitte vor dem Schreiben immer die aktuelle Datei lesen und nur ergänzen.**
Befunde zum Strickkurs: `kurspakete/stricken-lernen/` liegt noch nicht in diesem Repository – Validatorprüfung steht aus. Das Kurspaket-Format erlaubt derzeit keine Audiodateien (`ENDUNGEN` in `src/bonys_agents/kurspaket.py` nur Text, JSON, Skripte, Bilder); gesprochene Lektionen brauchen eine Formaterweiterung. **Entscheidung erforderlich (Bony):** Vorschlag für die Audio-Erweiterung ausarbeiten (nur Dokument, keine Codeänderung). Nichts committet.

### 2026-10-29 – Claude Code (Vorschlag Audio-Erweiterung)

Auf Bonys Ja: Vorschlag `docs/dev/plan-kurspaket-audio.md` (nur Dokument, kein Code geändert). Kern: optionales Lektionsfeld `audio` mit Pflicht-Transkript, nur Ogg/Opus mit Kopfprüfung, Grenzen 10 MB/Datei und 100 MB gesamt, `format_version` bleibt 1, neue `min_version`; Portal mindestens `needs_review`; Wiedergabe im Anleitungsfenster ohne Autoplay; Editor muss `audio` erhalten (heute ginge es beim Speichern verloren). Musik/Radio als späterer App-Teil (nicht im Paketformat), mit Vorrang für Kursansagen. **Entscheidung erforderlich (Bony):** sechs Punkte in Abschnitt 5 des Vorschlags. Strickkurs-Ordner liegt weiterhin nicht im Repository. Nichts committet.

### 2026-10-29 – Claude Code (Beginn: Musik & Radio in der App)

Bony: „wir übergehen mal kurs es geht im moment nur Musik und Radio soll man in der app zur verfügung haben“. Entscheidungen (Rückfrage): Leiste unten in der Statusleiste + Fenster „Musik & Radio“; kleine feste Senderliste (öffentlich-rechtlich) **und** eigene Sender; eigene Musik per Ordner **und** einzelne Dateien. Strickkurs/Audio im Paket ruht. In Arbeit, nicht committet.

### 2026-10-29 – Claude Code (Musik & Radio umgesetzt, wartet auf Bonys Test)

Neu: `src/bonys_agents/musik.py` (Sender, eigene Sender nur `https`, `.m3u`/`.pls` als Daten, Ordnersuche ohne verlinkte/versteckte Ordner, max. 5000 Titel, Einstellungen mit Bereinigung), `src/bonys_agents/gui/musik_ui.py` (Leiste in der Statusleiste, Fenster „Musik & Radio“ mit Tabs Radio/Eigene Musik; Qt Multimedia erst beim ersten Abspielen geladen; kein Autoplay; ohne Qt Multimedia keine Leiste), `gui/main_window.py` (Leiste einbinden, beim Schließen stoppen), `tests/test_musik.py` (30 Tests, nachgebauter Player). Bau: `packaging/bonys-agents.spec` nimmt Qt Multimedia mit (war ausgeschlossen); `packaging/collect-licenses.py` legt Qt-Multimedia-Drittteile und FFmpeg (LGPL-2.1+) bei. CHANGELOG „Unveröffentlicht“.
Tests: `QT_QPA_PLATFORM=offscreen PYTHONPATH=src build/venv/bin/python -m pytest tests/test_musik.py tests/test_gui_layout.py tests/test_editions.py -q` → 62 bestanden; `ruff check src tests packaging/…` sauber. Echt (stumm, Qt-Player): alle sechs Sender erreichen „BufferedMedia“ und spielen.
Nicht geprüft: Installationspaket-Bau (Größe ca. +20 MB durch FFmpeg, Lizenz-Sammler mit FFmpeg) – erst in CI/Release; vollständige Suite. Offen: Nutzungsbedingungen der Sender-Streams (öffentlich-rechtlich, offizielle Adressen); Vorrang für Kursansagen (Ducking) erst mit gesprochenen Lektionen. Nichts committet.
- Nachtrag (Bonys Wunsch „ich hätte als sender lieber https://hirschmilch.de/homepage“): feste Senderliste ersetzt durch die acht Hirschmilch-Kanäle (offizielle MP3-Streams `hirschmilch.de:7000`, aus deren `.pls`; alle acht echt stumm abgespielt, `BufferedMedia`). Bedingungen von Hirschmilch: nur private, nicht kommerzielle Nutzung, keine Weiterverbreitung – die App verlinkt nur den Stream. `tests/test_musik.py` 30 bestanden.
- Nachtrag (Bony): Text „Lerne auch mit Musik:“ vor dem Player – gelb (`WARN`), fett, Schreibschrift **Pacifico** (OFL-1.1, mitgeliefert unter `src/bonys_agents/resources/fonts/` mit Lizenztext; aus `github.com/google/fonts`). `THIRD-PARTY-LICENSES` um Qt Multimedia, FFmpeg 9.0.1 (LGPL-2.1+) und Pacifico (mit OFL-Text) ergänzt. `tests/test_musik.py` 30 bestanden, `ruff` sauber.
- Nachtrag: Buchstabenabstand 1,5 px (`QFont.AbsoluteSpacing`) – die Schreibschrift war zu eng. `tests/test_musik.py` 30 bestanden, `ruff` sauber.
