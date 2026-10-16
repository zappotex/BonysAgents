# Durchsicht vor Version 1.0

Stand: 15.10.2026, geprüft wurde Bony's Agents **0.19.0** (Commit `2724fad`), dazu in Kurzform bonys-vpn 1.0.1 und
bonys-agents-mission-control 0.1.0. Es wurde **nur geprüft** – kein Code, kein Paket, kein Release geändert.

Vorgehen: Überblick über Repo, Doku, Workflows und Pakete; danach acht getrennte Prüfungen (Bedienung, Robustheit,
Sicherheit Netzwerk, Sicherheit Eingaben/Downloads, Code-Qualität, Pakete/CI, Doku/Lizenzen/Datenschutz,
Nachbarprojekte). Die wichtigsten Funde wurden anschließend noch einmal selbst am Code nachgeprüft (Spalte „Beleg“).
Ausgeführt: komplette Testsuite, ruff, gitleaks (Historie, Arbeitsordner, gebaute .deb), Inhalt der .deb-Pakete,
eine Wegwerf-Test-VM im Scratchpad für den Ausbruchs-Nachweis (wieder gelöscht).

**Umsetzung (Stand 16.10.2026):** Alle „Muss vor 1.0“-Punkte sind umgesetzt (Commits ab `d0fe944`, je Punkt im
CHANGELOG unter „Unveröffentlicht“): S-01–S-04, P-01–P-04, R-01–R-03, R-05, R-06, L-01–L-03, U-03–U-05, D-01,
D-03, D-04. P-05/P-06: Anleitung für SmartScreen (README „Windows: erster Start“) und Gatekeeper (README
„macOS → Erster Start“) vorhanden; echte Signatur (Authenticode, Apple-Developer-ID) braucht ein bezahltes Konto –
Entscheidung des Projekts. Offen aus „Sollte vor 1.0“: alles ab S-05 (Liste unten). Noch nicht in einem echten
Agent-PC geprüft: die neue Fehler-Markierung der Einrichtung (R-02) bei einer kompletten Ersteinrichtung.

---

## Zusammenfassung (10 Zeilen)

1. **Gesamteindruck:** sehr sorgfältig gebautes Projekt – 435 Tests grün, ruff sauber, keine Geheimnisse in Historie oder Paketen, signierte Updates, vorbildlicher Root-Helfer in bonys-vpn.
2. **Größtes Risiko (kritisch, nachgewiesen):** Ein Programm *im* Agent-PC erreicht über 10.0.2.2 die QEMU-Steuerung (QMP) auf 127.0.0.1 des Hosts – ohne Anmeldung – und kann damit **Befehle auf dem echten Rechner ausführen**. Das hebelt den Kernnutzen „KI-Agent sicher in einer VM“ aus.
3. **Hoch:** Importierte Festplatten (`.bonys`, Vorlagen) dürfen per qcow2-`data_file` auf Host-Dateien zeigen (z. B. SSH-Schlüssel) – nachgewiesen.
4. **Hoch:** Die APT-Paketquelle signiert Pakete, ohne die minisign-Signatur der Releases zu prüfen; fehlt `SHA256SUMS`, wird gar nicht geprüft.
5. **Hoch:** Beim „Kurs beitreten“ wird ein per mDNS (im WLAN fälschbar) gelieferter Fingerabdruck ohne Rückfrage als vertrauenswürdig behandelt.
6. **Datenverlust-Risiken:** Verschieben löscht die Quelle ohne `fsync` des Ziels; `vm.json` wird nicht atomar geschrieben; veraltete PID-Datei kann einen *fremden* Agent-PC hart ausschalten.
7. **Lizenzen:** pycdlib (LGPL) ist entgegen dem Lizenzhinweis nicht austauschbar gebündelt; Lizenztexte für mitgelieferte OpenSSL, krb5, libjpeg, ICU, Qt-Drittteile fehlen.
8. **Laien:** englische „Yes/No“-Knöpfe, rohe englische Fehlertexte (QEMU, `[Errno …]`), kein Absturzprotokoll, SmartScreen/Gatekeeper ohne Signatur, README nennt veraltete Dateinamen, kein Datenschutz-Abschnitt.
9. **Reif für 1.0? Noch nicht.** Grund: der kritische VM-Ausbruch, die ungeprüfte APT-Kette und die Lizenzpflichten. Alles ist mit überschaubarem Aufwand lösbar (≈ 6–8 Sitzungen, siehe unten).
10. Nach den „Muss“-Punkten ist das Projekt aus meiner Sicht 1.0-tauglich; Signatur unter Windows/macOS ist vor allem eine Kosten-/Vertrauensfrage.

---

## Tabelle aller Funde

Schwere: **kritisch / hoch / mittel / gering**. Aufwand: **klein / mittel / groß**.
Beleg: ✔ = selbst nachgeprüft bzw. per Experiment bestätigt, (C) = durch Code-Lesen des Prüfagenten belegt,
(V) = Vermutung/abgeleitet, nicht praktisch ausprobiert.

### Sicherheit (S)

| Nr. | Bereich | Schwere | Beschreibung | Fundstelle | Vorschlag | Aufwand | Beleg |
|---|---|---|---|---|---|---|---|
| S-01 | VM-Isolation | **kritisch** | QMP (`-qmp tcp:127.0.0.1:…`), Gast-Agent-Kanal (TCP) und SPICE ohne Passwort (`disable-ticketing=on`) lauschen auf 127.0.0.1. Das QEMU-Benutzernetz (slirp) leitet Verbindungen des Gasts zu **10.0.2.2** auf 127.0.0.1 des Hosts um; `restrict=on` ist nur bei der Vorlagen-Arbeitskopie gesetzt. Ein Prozess im Agent-PC (Prompt-Injection, böse Vorlage, kompromittiertes npm-Paket) scannt die Ports und führt über QMP (`migrate exec:…`) **Befehle auf dem Host** aus; über die Gast-Agent-Ports anderer Agent-PCs bekommt er dort root, über deren SPICE Bild und Eingabe. Unter Windows zusätzlich VNC ohne Passwort. Auch andere lokale Benutzer des Hosts können das. | `qemu.py:164,179,183-188,215,236-238`; `vm.py:181`; `templates.py:178` | QMP und Gast-Agent als Unix-Socket im 0700-Ordner (wie VNC in `vm.py:105-116`); SPICE lokal per `unix=on` oder immer mit `password-secret`; Windows: Named Pipe/Passwort, VNC mit Passwort; zusätzlich `-sandbox on,spawn=deny,…` unter Linux. Regressionstest: Befehlszeile darf kein `tcp:127.0.0.1` für QMP/QGA enthalten. | mittel (Linux/macOS), groß (Windows) | ✔ Experiment: Test-VM mit gleichen Optionen, Skript im Gast verband sich mit 10.0.2.2:QMP-Port und legte per `migrate exec:` eine Datei auf dem Host an |
| S-02 | Kurs/Freigabe | **hoch** | Fingerabdruck aus der mDNS-Suche wird als „✓ (aus dem Link bzw. der Suche)“ behandelt, die Vergleichs-Checkbox verschwindet. mDNS ist im WLAN fälschbar → Angreifer kündigt eigenen „Kurs“ an, bekommt den Code, liefert eine manipulierte Vorlage bzw. gibt sich im Hilfe-Modus als Kursleiter aus (sieht/steuert nach Zustimmung den Agent-PC). | `gui/share_dialogs.py:164,176,231,237,247`; `gui/course_ui.py:245,256,281`; `mdns.py:166-213` | Fingerabdruck aus mDNS nur als Vorschlag; immer kurzen Fingerabdruck zeigen und Bestätigung verlangen. Nur Link/QR gilt ohne Rückfrage. | klein | ✔ Code |
| S-03 | Import | **hoch** | Importierte qcow2-Platten dürfen eine externe `data_file` haben (z. B. `/home/…/.ssh/id_ed25519`, `data_file_raw=on`). Geprüft wird nur das Backing-Feld; `qemu-img check` ist zufrieden. Ein Agent-PC aus so einer `.bonys`-Datei sieht die Host-Datei als Festplatte. | `bonysfile.py:805-807`; `templates.py:516-518`; `qemu.py:470-489` | Nach Import `qemu-img info --output=json` prüfen (Format qcow2, kein `data-file`, kein Backing) – besser per `qemu-img convert` in eine eigenständige Datei umschreiben. | klein | ✔ Experiment (Prüfagent) + `grep data_file` leer |
| S-04 | Import / Laufwerke | **hoch** | `vm.json` (und alte `.bonys-template`) werden ohne Typ-/Wertprüfung geladen – auch von jedem automatisch erkannten Laufwerk mit Ordner `BonysAgents`. `username`/`name` landen ungeprüft in Remmina-Profilen und `.rdp`-Dateien (Zeilenumbruch → zusätzliche Einträge, Remmina kennt z. B. Vor-Befehle) und in Gast-Skripten. Szenario: Kursleiter verteilt eine präparierte SSD. | `vm.py:186-191`; `remote.py:121-137,174-184`; `storage.py:256-271`; `templates.py:464-528` (Prüfung nur im neuen `.bonys`-Manifest, `bonysfile.py:402`) | Beim Laden alle Felder gegen Schema prüfen (`NAME_RE`, Benutzer-Regex wie `bonysfile.py:402`, Zahlenbereiche, erlaubte Desktops/Apps); Remmina/.rdp-Werte escapen bzw. ablehnen. | klein–mittel | ✔ Code; Remmina-Befehlsausführung (V) nicht getestet |
| S-05 | Kurs-Server | mittel | RFB-Filter kopiert den Puffer bei jeder Nachricht (`bytes`-Slicing) → quadratischer CPU-Aufwand; 2-MB-Nachricht ≈ 20 s CPU, blockiert über den GIL die ganze Oberfläche. Jeder Teilnehmer mit Code kann das. | `rfb.py:94-98` | `bytearray`/`memoryview` mit Leseposition; Höchstzahl Nachrichten je `feed`. | klein | (C) + Messung im Scratchpad |
| S-06 | Kurs-Server | mittel | Keine Obergrenze für Verbindungen/Threads (`ThreadingHTTPServer`), mehrere WebSockets je Zuschauer, `max_viewers` zählt nur Aktive der letzten 60 s → Slowloris bzw. „Vorführung ist voll“ für echte Teilnehmer. | `trainer/share_server.py:489-493`; `trainer/present.py:206-209,339,640-656`; `trainer/helpdesk.py:384-401` | Verbindungslimit gesamt und je Adresse, ein WebSocket je Zuschauer. | mittel | (C) |
| S-07 | Kurs-Server | mittel | Browser-Zuschauer müssen die Zertifikatswarnung wegklicken; der Fingerabdruck schützt nur den Python-Weg. Im WLAN (ARP-Spoofing) kann Code/Cookie mitgelesen werden. | `trainer/present.py:186-196`; `resources/present/join.js`; `gui/share_dialogs.py:220` | Grenze klar dokumentieren; langfristig Ansicht in Bony's Agents oder lokale CA. | klein (Doku) / groß | (C) |
| S-08 | Kurs-Server | gering–mittel | Nach 100 Fehlversuchen insgesamt beendet sich der Server – jeder im LAN kann damit einen Kurs abschießen. | `trainer/share_server.py:339-355`; `share.py:42` | Statt Beenden globale Bremse bzw. Kursleiter fragen. | klein | (C) |
| S-09 | Kurs-Server | gering | WebSocket: leere Fortsetzungsrahmen wachsen unbegrenzt; Mailbox im Hilfe-Tunnel unbegrenzt. | `websocket.py:156,197-203,251-284`; `trainer/helpdesk.py:438-441` | Fragmentzahl und Mailbox (Bytes) begrenzen. | klein | (C) + Messung |
| S-10 | Hilfe-Modus | gering | Titel/Texte vom Kurs-Server werden in `QMessageBox` als AutoText (HTML) angezeigt → Zustimmungsdialog kann optisch verfälscht werden; wiederholte Anfragen erzeugen Dialog-Flut; „Ansehen“-Zustimmung ohne Zeitlimit. | `helpmode.py:262-271`; `gui/course_ui.py:402-407`; `trainer/helpdesk.py:292-299` | `Qt.PlainText`; Anfragen entprellen; Zustimmung befristen. | klein | (C) |
| S-11 | mDNS | gering | Antwortet auf 0.0.0.0:5353 per Unicast an jede (auch gefälschte) Absenderadresse und nennt alle Adressen inkl. VPN; Status-Endpunkt ohne Code liefert Titel/Restzeit. | `trainer/announce.py:61-71,98-102`; `trainer/present.py:371-375,559-561` | Nur lokale Netze beantworten; bewusst entscheiden, was ohne Code sichtbar ist. | klein | (C) |
| S-12 | Geheimnisse | gering | SPICE-Passwort in `vm.json`, Kurs-Code in `schulung/kurs.json`, Ansicht-Schlüssel als URL auf der Befehlszeile des Browsers; auf exFAT-SSD gibt es keine Dateirechte. Agent-PC-Passwort steht im Klartext im Seed-ISO (0600, wird nach der Einrichtung gelöscht). | `vm.py:473-475`; `gui/course_ui.py:40-47`; `trainer/helpdesk.py:224`; `cloudinit.py:363,426` | Code nicht speichern; Schlüssel per Einmal-Link; Hinweis bei exFAT. | klein | ✔ Code (Seed) / (C) |
| S-13 | Fernzugriff | gering | „Fernzugriff dauerhaft“: SPICE im Heimnetz unverschlüsselt (Bild, Tastatur, Zwischenablage). | `vm.py:815`; `qemu.py:182-190` | Hinweis in der Oberfläche oder SPICE-TLS. | mittel | (C) |
| S-14 | Updates | gering | Geprüfte .deb/Setup.exe liegen zwischen Prüfung und Installation (pkexec/UAC) in einem vom Benutzer beschreibbaren Temp-Ordner (TOCTOU, nur für Schadcode mit gleichen Benutzerrechten). Gleiches in `hostvpn.py` und bonys-vpn. | `updates.py:350-351,370-373,394,403-407`; `hostvpn.py:168-172` | Im erhöhten Skript nach Kopie in root-eigenen Ordner Hash erneut prüfen. | klein | (C) |
| S-15 | Downloads | gering | Debian-Image: SHA512 vom selben Server, GPG-Signatur `SHA512SUMS.sign` wird nicht geprüft. Brave-Schlüssel ohne festen Fingerabdruck; Hermes/OpenClaw/Claude per `curl | bash` ohne Prüfung (bewusst, Fremd-Installer). | `images.py:27-44`; `apps.py:73-78,426,458,520` | Debian-Signatur prüfen (Schlüssel mitliefern); Brave-Fingerabdruck festlegen; Fremd-Installer in der Doku als Vertrauensannahme nennen. | mittel | (C) |

### Pakete, Release, Updates (P)

| Nr. | Bereich | Schwere | Beschreibung | Fundstelle | Vorschlag | Aufwand | Beleg |
|---|---|---|---|---|---|---|---|
| P-01 | APT-Quelle | **hoch** | Der Workflow prüft nur `SHA256SUMS` aus *demselben* Release, nie `SHA256SUMS.minisig`; fehlt die Datei → `|| continue` (keine Prüfung); `--ignore-missing` lässt nicht gelistete .deb durch; Paketnamen-Liste gilt für beide Quell-Repos (VPN-Release könnte ein `Package: bonys-agents` einschleusen). Danach wird mit dem APT-GPG-Schlüssel signiert → umgeht die minisign-Kette auf dem Haupt-Update-Weg unter Linux. | `.github/workflows/apt-repo.yml:78-84`; `packaging/linux/build-apt-repo.sh:28-29` | `minisign -V` mit dem jeweiligen Schlüssel; ohne Sums/Signatur abbrechen; ohne `--ignore-missing`; Paketnamen je Quell-Repo; Version = Tag. | klein | ✔ Code |
| P-02 | Release | mittel | Release-Workflow läuft auf Tag-Push ohne Tests/ruff und ohne Abhängigkeit von der CI; ein Tag auf einem roten Commit wird signiert und per apt verteilt. Fehlt das minisign-Secret, wird trotzdem veröffentlicht. | `release.yml:26-29,357-360` | Test-Job als `needs`; Tag-Schutz für `v*`; ohne Secret hart abbrechen. | klein | (C) |
| P-03 | Release | mittel | `contents: write` für alle Jobs, Apple-Secrets im `env` des ganzen Jobs, Actions per `@vN` statt Commit-SHA, `persist-credentials` an; `ci.yml` ohne `permissions:`. Bau-Jobs führen ungepinnten Fremdcode aus (pip, choco, brew). | `release.yml:31-32,193-200,374`; `ci.yml` | `permissions: contents: read` global, `write` nur im Release-Job; Secrets nur im Signier-Schritt; Actions auf SHA; `persist-credentials: false`. | klein | (C) |
| P-04 | Build | mittel | Bau-Abhängigkeiten ohne feste Versionen (`PySide6-Essentials>=6.6`, `pip install . pyinstaller`) → nicht reproduzierbar, Qt-Version in THIRD-PARTY kann falsch sein, kompromittierte PyPI-Version landet signiert im Release. | `pyproject.toml:29-30`; `release.yml:121,210`; `build-deb.sh:51` | Lock-Datei mit Hashes nur für Release-Builds (`--require-hashes`). | mittel | (C) |
| P-05 | Windows | hoch (für 1.0) | Setup und .exe nicht Authenticode-signiert → SmartScreen „Unbekannter Herausgeber“ mit nur „Nicht ausführen“ sichtbar; Virenschutz-Fehlalarme. README erklärt den Ausweg nicht. | `packaging/windows/bonys-agents.iss:36-66`; `release.yml:129-138`; `README.md:72` | Mindestens Doku „Weitere Informationen → Trotzdem ausführen“ mit Bild; besser Signatur (z. B. Azure Trusted Signing). | klein (Doku) / mittel | ✔ (kein `SignTool`) |
| P-06 | macOS | hoch (für 1.0) | Nur ad-hoc-signiert, nicht notarisiert; ab macOS 15 nur über Systemeinstellungen „Dennoch öffnen“. Ad-hoc-Signatur ändert sich je Build → Freigaben (lokales Netz, Wechseldatenträger) evtl. nach jedem Update neu. Ablauf für Developer-ID ist vorbereitet. | `packaging/macos/sign.sh:16-21`; `release.yml:233-239,402-408` | Apple-Developer-Konto + Secrets setzen. | mittel (v. a. Kosten) | (C) |
| P-07 | Tests | mittel | Kein CI-Test für Update vom letzten öffentlichen Release, für `apt remove/purge`, Windows-Deinstallation, Debian 12; Windows nur `--version`. | `release.yml:54-86,139-159` | Vorheriges Release holen, installieren, Daten anlegen, neue Version drüber, dann purge prüfen. | mittel | (C) |
| P-08 | .deb | gering | Kursleiter-Paket: `trainer/` wird erst in `postrm` gelöscht → dpkg-Warnung „Verzeichnis nicht leer“, leerer Ordner bleibt. | `packaging/linux/build-deb.sh:225` | `prerm` räumt `trainer/` weg. | klein | (V) |
| P-09 | .deb | gering | Bei `purge` bleibt `/var/lib/bonys-agents/apt-source-disabled`; udev wird beim Entfernen nicht neu geladen; kein `DEBIAN/md5sums`; `debian/copyright` nicht DEP-5. | `build-deb.sh:86-93,214-238,261` | Ergänzen. | klein | (C) |
| P-10 | APT | gering | Kein `Valid-Until` (Freeze-Angriff), Schlüssel ohne Ablauf und ohne Wechselplan, Passphrase per `--passphrase` auf der Befehlszeile. | `build-apt-repo.sh:36,46-51` | `Valid-Until` + regelmäßiges Neusignieren; Schlüsselwechsel in `RELEASE.md`; `--passphrase-fd`. | klein | ✔ Code |
| P-11 | Windows | gering | `x64compatible` erlaubt ARM64; keine Downgrade-Sperre; App meldet „installiert“, sobald das Setup nur gestartet ist (UAC abgelehnt → App beendet, kein Update); Firewall-Regeln, QEMU, WHPX und Temp-Installer bleiben nach Deinstallation (nicht dokumentiert). | `bonys-agents.iss:63,89-90,152-156`; `updates.py:399-407`; `updates_ui.py:136`; `remote.py:269-282` | Beheben bzw. in README „Deinstallation“ nennen; Firewall-Regel per `[UninstallRun]` entfernen. | klein | (C) |
| P-12 | macOS | gering | `Info.plist` ohne `NSLocalNetworkUsageDescription`/`NSBonjourServices` → unverständliche Abfrage bzw. scheiternde Kurs-Suche ab macOS 15; `macos-compat` testet nur Apple-Silicon/Anwender auf macOS 14. | `packaging/bonys-agents.spec:158-172`; `release.yml:299-312` | Schlüssel ergänzen; Matrix erweitern. | klein | (C) |
| P-13 | APT | gering | Stündlicher Zeitplan in `apt-repo.yml` wird von GitHub nach 60 Tagen ohne Repo-Aktivität abgeschaltet → neue VPN-Releases kämen nicht mehr in die Quelle. | `apt-repo.yml:18-19` | Auslösen per `repository_dispatch` aus beiden Repos (VPN hat bereits Token) oder Erinnerung. | klein | (C) |
| P-14 | lokal | gering | Lokale `dist/*.deb` 0.19.0 verlangen `libc6 >= 2.39` (gebaut auf Mint 22), die CI-Pakete 2.35 → lokale Pakete nicht weitergeben. | `dist/` | – | – | (C) |

### Funktionen und Robustheit (R)

| Nr. | Bereich | Schwere | Beschreibung | Fundstelle | Vorschlag | Aufwand | Beleg |
|---|---|---|---|---|---|---|---|
| R-01 | Verschieben | **hoch** | Verschieben auf andere Platte: Kopie ohne `fsync`, dann `os.replace`, dann wird die Quelle gelöscht; Prüfung nur über die Größe. SSD sofort abziehen/Stromausfall → Agent-PC weg. Im ganzen `src` gibt es kein `fsync`. | `vm.py:1478-1513` | Dateien + Zielordner `fsync`, erst dann Quelle löschen; optional `qemu-img check`; Hinweis „erst auswerfen“. | klein | ✔ Code |
| R-02 | Einrichtung | **hoch** | Fehlgeschlagene Einrichtungsschritte werden im Gast nur als „WARNUNG“ ausgegeben, danach trotzdem „fertig“. Host wertet das nicht aus → Agent-PC ohne Desktop/Apps, `vm.json` führt sie als installiert; eine mitgebrachte VPN-.conf ist nach Löschen des Seed-ISO verloren. Fremd-Installer (`curl | bash`) ohne `--max-time`, Einrichtungsdienst `TimeoutStartSec=0` → kann ewig hängen. | `cloudinit.py:188-201,259`; `apps.py:426-427,462-463,530-531`; `vm.py:300-302`; `vpnlink.py:239` | Eigene Fehler-Markierung auf der Konsole, Host zeigt „fertig mit Fehlern“ + „Schritt wiederholen“; Apps erst nach `check` eintragen; `--max-time/--retry` überall. | mittel | (C) |
| R-03 | Prozesse | **hoch** | Über `qemu.pid` wird nur geprüft, ob der Prozessname „qemu“ enthält. Nach Absturz/Stromausfall kann die PID einem *anderen* Agent-PC gehören → A zeigt „läuft“, „Ausschalten“/„Löschen“ von A beendet hart B. | `vm.py:233-251` (gründliche Prüfung nur in `_recorded_pid`, 253-270) | Auch hier Befehlszeile (Disk-Pfad) und Startzeit prüfen. | klein | ✔ Code + Experiment (Prüfagent) |
| R-04 | Gleichzeitigkeit | mittel | Keine Sperre zwischen Prozessen (zwei Fenster, GUI + CLI): doppelter Start überschreibt `runtime.json`/`qemu.pid` des ersten; Verschieben während Start in anderem Prozess; `save()` aus alten Objekten verwirft fremde Änderungen. Keine Einzelinstanz der GUI. | `vm.py:440-458,824,1008-1015,1441-1513`; `gui/app.py`; `main_window.py:1003-1006`; `cli.py:330-335` | Datei-Sperre je Agent-PC für start/move/delete/save; Einzelinstanz per `QLocalServer`. | mittel | (C) Wettlauf; Folgen (V) |
| R-05 | Dateien | mittel | `vm.json`/`runtime.json` nicht atomar geschrieben (settings.json schon). Halbe Datei → Agent-PC erscheint als „nicht verfügbar – Laufwerk eingesteckt?“. Kaputte `settings.json` wird still zu `{}` → Speicherorte verschwinden. Fester tmp-Name bei settings.json (zwei Prozesse). | `vm.py:229-230,284,834,1632,1715`; `templates.py:202`; `storage.py:67-83` | tmp + fsync + `os.replace`, `.bak` behalten; „beschädigt“ statt „nicht verfügbar“ anzeigen; tmp-Name mit PID. | klein | ✔ Code + Experiment |
| R-06 | Kompatibilität | mittel | Keine Formatversion in `vm.json`/`template.json`; ältere Programmversion verwirft beim Speichern unbekannte Felder still (Downgrade, SSD am Schulungs-PC mit alter Version). | `vm.py:184-191`; `templates.py:84-88` | `format_version` + `min_version` (wie bei `.bonys`); unbekannte Felder mitführen; neuere Datei nur lesen. | klein–mittel | (C) + Experiment |
| R-07 | Platz | mittel | Mindest-Freiplatz 4 GB (Gast braucht ~16 GB); QEMU pausiert bei vollem Datenträger, die GUI merkt es nicht („wird eingerichtet“ für immer). `make_independent` prüft keinen Platz. | `storage.py:313`; `qemu.py:155-156`; `vm.py:370-377` | ~16 GB als Fehler; QMP `query-status`/`BLOCK_IO_ERROR` auswerten und Hinweis + „Fortsetzen“. | mittel | (C); QEMU-Pause (V) |
| R-08 | Laufwerke | mittel | Gleicher Name an zwei Speicherorten → der zweite Agent-PC ist unsichtbar, Import meldet trotzdem Erfolg. | `vm.py:1384-1394,1420-1434` | Pfad als Schlüssel, doppelte Namen kennzeichnen oder beim Import umbenennen. | mittel | Experiment (Prüfagent) |
| R-09 | Laufwerke | mittel | SSD bei laufendem Agent-PC abgezogen → „nicht verfügbar“, QEMU läuft unsichtbar weiter, kein „Ausschalten“ möglich. | `vm.py:1372-1376,1397-1402` | Laufende Agent-PCs zusätzlich in `data_dir/running/` führen, Knopf „Ausschalten“. | mittel | (C) |
| R-10 | Vorlagen | mittel | Sperre „Vorlage wird erstellt“ prüft nur `pid_exists` → übersteht Neustart (Agent-PC dauerhaft gesperrt, Löschen deaktiviert, kein Ausweg). Versteckte `.arbeitskopie`/`.teil` (viele GB) bleiben liegen; QEMU der Arbeitskopie läuft nach GUI-Absturz verwaist weiter. | `vm.py:354-360`; `templates.py:212-221`; `main_window.py:1129` | Startzeit/Name in der Sperre; beim Programmstart Reste aufräumen. | klein | (C) |
| R-11 | RAM | mittel | Standard ~75 % des Host-RAM und alle Kerne je Agent-PC; beim Start keine Prüfung des freien RAM → zwei Agent-PCs = OOM. | `host.py:33-41`; `vm.py:1598-1599,765ff` | Vor Start warnen; Standard ~50 %/max. 8 GB. | klein | (C) |
| R-12 | Download | mittel | Debian-Image (~450 MB): kein Fortsetzen (Range), kein Wiederholen, nicht abbrechbar; ohne Netz scheitert das Anlegen sogar mit gecachtem Image (Prüfsumme wird zuerst geholt); Meldung `<urlopen error [Errno 111] …>`. Gleichzeitiger Download in dieselbe `.part`. | `images.py:42-44,81-135`; `create_dialog.py:561,633-635` | Fortsetzen/Retry wie `share.py:395-405`; Abbruch; letzte SHA512SUMS cachen; Klartext-Fehler; eindeutiger tmp-Name. | mittel | Experiment (Prüfagent) |
| R-13 | Obsidian | mittel | GitHub-API ohne Anmeldung (60 Anfragen/h/IP) → im Schulungsraum hinter einer NAT-IP scheitert die Installation (still, siehe R-02). | `apps.py:184` | Rückfall über `releases/latest/download` oder Version+SHA mitliefern (wie Mission Control). | klein | (C); Limit (V) |
| R-14 | Anlegen | gering–mittel | Absturz/Strg+C beim Anlegen hinterlässt Ordner ohne `vm.json` → unsichtbar, Name blockiert („Ordner existiert bereits“). | `vm.py:1611-1636,1696-1717` | In `.name.anlegen` bauen und am Ende umbenennen; Reste aufräumen. | klein | Experiment (Prüfagent) |
| R-15 | GUI | gering | Hauptfenster schließen während Löschen/Unabhängig-machen bricht Thread ab → halber Zustand. Verschieben nicht abbrechbar. | `main_window.py:365-367,1303-1311`; `move_dialog.py:126-129` | `closeEvent` wartet/fragt; Abbruch-Event beim Verschieben. | klein | (C); Qt-Verhalten (V) |
| R-16 | Vorlagen | gering | Vorlage umbenennen: scheitert ein `rebase`, zeigen übrige verknüpfte Agent-PCs ins Leere (keine Rücknahme). | `templates.py:381-396` | Erst alle rebasen, bei Fehler zurück. | klein | (C) |

### Benutzererlebnis aus Laiensicht (U)

| Nr. | Bereich | Schwere | Beschreibung | Fundstelle | Vorschlag | Aufwand | Beleg |
|---|---|---|---|---|---|---|---|
| U-01 | Fehlertexte | hoch | Rohe englische QEMU-Ausgabe (bis 2000 Zeichen) bei Startfehlern (VirtualBox läuft, `/dev/kvm` Rechte, zu wenig RAM) – ohne Handlungsschritt. | `vm.py:849`; `templates.py:205`; `main_window.py:1308` | Bekannte Muster übersetzen, Rohtext unter „Details“, „Protokoll öffnen“. | mittel | (C) |
| U-02 | Fehlertexte | mittel | Viele Dialoge zeigen `str(e)`: `[Errno 28] No space left on device`, `KeyError` mit Anführungszeichen, `Connection refused`, `qemu-img convert fehlgeschlagen: <stderr>`. | `gui/workers.py:31,50`; `template_dialogs.py:44,377,618,809,856,896`; `move_dialog.py:31`; `resize_dialog.py:76`; `desktop_dialog.py:32`; `install_dialog.py:43`; `setup_dialog.py:31,43`; `main_window.py:793,872,1463`; `host_vpn.py:40-101`; `qemu.py:400,454,466`; `vm.py:592` | Zentrale `friendly_error(e)` (errno → deutscher Satz, KeyError → Text), Rohtext unter „Details“. | mittel | (C) |
| U-03 | Qt-Texte | mittel | Kein `QTranslator` → „Yes/No“, „OK/Cancel“ und Kontextmenüs englisch (25× `QMessageBox.question`, alle `QInputDialog`). | `gui/app.py:17-41` | `qtbase_de.qm` laden und im PyInstaller-Spec mitpacken. | klein | (C) |
| U-04 | Löschen | mittel | „Agent-PC löschen“ und „Vorlage löschen“ ohne sicheren Standardknopf → Enter löscht. (In `mc_panel.py:306` richtig gelöst.) | `main_window.py:1331-1335`; `template_dialogs.py:850` | Standard „Abbrechen“, eigene Knöpfe „Löschen“/„Behalten“. | klein | (C) |
| U-05 | Absturz | mittel | Kein `sys.excepthook`/Logging; GUI-Builds ohne Konsole → unerwartete Fehler verschwinden still (Knopf tut nichts, App startet nicht), kein Protokoll für Support. | `gui/app.py`; `packaging/bonys-agents.spec:82` | `sys.excepthook`/`threading.excepthook` → `data_dir()/fehler.log` + kurze deutsche Meldung. | klein | (C) |
| U-06 | Windows | hoch | BIOS-Virtualisierung aus: WHPX wird „optimistisch“ gewählt, QEMU fällt still auf Software-Emulation zurück, Statusleiste zeigt trotzdem „whpx“ → Einrichtung dauert Stunden ohne Hinweis. | `host.py:117-119`; `qemu.py:133-134`; `create_dialog.py:228-234`; `main_window.py:238` | Nach Start per QMP prüfen, welcher Beschleuniger aktiv ist; deutlicher Hinweis „Virtualisierung im BIOS einschalten“. | mittel | (C); Verhalten (V) |
| U-07 | QEMU-Fenster | mittel | Schließen des Agent-PC-Fensters mit X = hart ausschalten (wie Stecker ziehen), ohne Hinweis. | `qemu.py:301-309` | `window-close=off` (gtk/sdl) + Hinweis, oder ACPI-Herunterfahren. | klein–mittel | (C) |
| U-08 | Einrichtung | mittel | „Rechner vorbereiten“ öffnet sich bei jedem Start, auch wenn nichts behebbar ist (VT-x aus, Mac ohne Virtualisierung); „Automatisch einrichten“ fragt dann immer wieder vergeblich das Passwort ab. | `main_window.py:258-259`; `deps.py:79-105` | Nur bei behebbaren Punkten öffnen; „Nicht mehr anzeigen“; nach erfolglosem Versuch „von Hand: BIOS“. | klein | (C) |
| U-09 | Abläufe | mittel | Lange Abläufe (Verschieben, Vorlage erstellen, Programme installieren, Updates) nicht abbrechbar, das Fenster-X tut still nichts; `setup_dialog` blockiert beim Schließen bis 30 s. | `create_dialog.py:633`; `install_dialog.py:226`; `setup_dialog.py:249-253`; `move_dialog.py:126`; `template_dialogs.py:246,928`; `desktop_dialog.py:162`; `updates_ui.py:178,343`; `course_ui.py:324` | Mindestens „Läuft noch – bitte warten“; wo möglich Abbruch-Event wie bei Export/Import. | mittel | (C) |
| U-10 | Begriffe | mittel | „Gast-Agent“ und „SSH“ in Meldungen (Verwechslung mit Agent-PC/Hermes Agent). | `install_dialog.py:104,205`; `mc_panel.py:247`; `vpn_panel.py:302`; `vm.py:584,1128,1202` | „Der Agent-PC antwortet gerade nicht direkt – bitte sein Passwort eingeben (wird nicht gespeichert).“ | klein | (C) |
| U-11 | Windows | mittel | `host.detect()` startet PowerShell/CIM (bis 30 s) im GUI-Thread, u. a. im 2-s-Takt des Reiters „Fernzugriff“ → Ruckeln. | `host.py:102-114`; `vm.py:712`; `remote_panel.py:200`; `main_window.py:104,258,1315-1317` | Ergebnis je Sitzung zwischenspeichern. | klein | (C); Wirkung (V) |
| U-12 | Begriffe | gering | Uneinheitlich: „Kurs beitreten“ vs. „Schulung beitreten“; „System prüfen“ → Fenster „Einrichtung“ → Überschrift „Rechner vorbereiten“; „Host“ vs. „dieser Rechner“; „Hinzufügen …“ mehrdeutig; Sie/du gemischt in `trainer/gui/share_dialog.py:226`. | `main_window.py:162-169`; `share_dialogs.py:69`; `setup_dialog.py:52-56`; `create_dialog.py:220-221` | Begriffsliste festlegen und vereinheitlichen. | klein | (C) |
| U-13 | Begriffe | gering | Fachbegriffe in der Hauptansicht: „SSH-Befehl kopieren“, „SPICE“, Reiter „Konsole“ als Standard, CLI-Befehle und `sudo apt install` in GUI-Meldungen, „Paket openssh-client“ auch unter Windows/macOS. | `main_window.py:495,578,581,667`; `vm.py:494,756,1063`; `mission_control.py:442`; `qemu.py:29-59` | Fortgeschrittenes in „Mehr …“; CLI-Hinweise nur in der CLI. | klein | (C) |
| U-14 | Eingabe | gering | Name wird erst nach Klick geprüft, Text verschweigt „ohne Umlaute/Leerzeichen“; TCG-Hinweis nennt nur „in einer VM“. | `vm.py:39,1569`; `create_dialog.py:24-27,116` | Validator im Feld, klarer Text; Hinweise je System. | klein | (C) |
| U-15 | Barrierefreiheit | gering | Nur dunkles Thema, keine `setAccessibleName`, wichtige Hinweise nur im Tooltip (z. B. „Wie Stecker ziehen“). | `main_window.py:555` u. a. | Schrittweise. | mittel | (C) |

### Dokumentation (D)

| Nr. | Bereich | Schwere | Beschreibung | Fundstelle | Vorschlag | Aufwand | Beleg |
|---|---|---|---|---|---|---|---|
| D-01 | README | hoch | Installationstabelle nennt Dateinamen von **0.15.0**; Kursleiter-Dateien fehlen. Laien suchen genau diese Dateien. | `README.md:72-75` | Versionsneutral oder beim Release einsetzen. | klein | ✔ |
| D-02 | Laien-Doku | mittel | Es fehlen: Systemanforderungen (praktisch ≥ 6–8 GB RAM, ≥ 20 GB frei, CPU-Virtualisierung), FAQ/Fehlerbehebung, „Fehler melden“ (kein Issue-Link, keine `SECURITY.md`, Kontakt nur über YouTube), vollständige Deinstallation inkl. Daten, Schnellstart mit Screenshots der App (`docs/images` hat nur 2 macOS-Systemdialoge). README ist eine 954-Zeilen-Datei. | `README.md`; `docs/images/` | „Schnellstart“ (1 Seite, Bilder) + `docs/handbuch`, `docs/faq`, `docs/datenschutz`; `SECURITY.md`, Issue-Vorlagen. | mittel–groß | ✔ |
| D-03 | Datenschutz | mittel | Kein Datenschutz-Abschnitt. Update-Prüfung täglich standardmäßig an (IP + Version an api.github.com); Rechnername geht per mDNS ins LAN und an den Kursleiter (siehe Tabelle unten); `CONTRIBUTING.md` verspricht „kein Code, der Daten ohne Zustimmung nach außen sendet“. | `updates.py:35-38,176`; `trainer/present.py:238-241`; `share.py:251-275`; `helpmode.py:136` | Abschnitt „Datenschutz“ mit Tabelle; beim ersten Start Update-Prüfung erfragen oder klar ankündigen; Anzeigename statt Hostname. | klein | (C) |
| D-04 | Repo | mittel | Interne Arbeitsnotizen im öffentlichen Repo (`docs/plan-schulung.md`, `docs/plan-vpn-obsidian.md` mit lokalen Pfaden, README verweist darauf); unversioniert und nicht ignoriert: `Audio/` (267 MB, u. a. kommerzieller Musiktitel), neue `Bilder/`, `docs/Bonys-Agents-Zusammenfassung.md`, `docs/Mission-Control-Integration.md`, Streudatei `" + unit + r.service"` (Rest eines Entwicklungs-Probelaufs, kein Fehler im ausgelieferten Code). Ein `git add -A` würde das veröffentlichen. | `.gitignore`; `docs/`; `README.md:630` | `Audio/`, Video-Bilder in `.gitignore`; Pläne in den Obsidian-Tresor oder `docs/dev/`; Streudatei löschen. | klein | ✔ |
| D-05 | README | gering | `--apps`-Standard laut README `brave,telegram,hermes`, tatsächlich zusätzlich `xrdp`; RDP-Benutzer nicht fest „agent“; Codeübersicht ohne `storage.py`, `remote.py`, `screen.py`, `wallpaper.py`, `progress.py`; Qt-Version 6.12 (README) vs. 6.11.2 (THIRD-PARTY). 18 von 22 Stichproben stimmten. | `README.md:116,247,645,884-925`; `apps.py:30` | Korrigieren. | klein | ✔ (`--apps`) |
| D-06 | CHANGELOG | gering | 0.19.0 „noch nicht veröffentlicht“, obwohl Tag existiert; ältere Versionen nur auf GitHub; keine Daten. `pyproject.toml`: „Development Status :: 3 - Alpha“. | `CHANGELOG.md:3,6`; `pyproject.toml:16` | Vermerk/Status anpassen, Datum ergänzen. | klein | ✔ |
| D-07 | Mitwirkende | gering | `CONTRIBUTING.md` ohne Editionen (`pytest --edition`), `fetch-novnc.py`, PYTHONPATH-Falle, Bauweg; Beispiel `apt-get install codium` funktioniert nicht; kein Architekturüberblick; Docstrings nur bei ~40 % der öffentlichen Funktionen; kein mypy/pyright. | `CONTRIBUTING.md:32-44` | Ergänzen, kurzes `docs/architektur.md`. | klein–mittel | (C) |

### Recht und Lizenzen (L)

*Hinweise, keine Rechtsberatung. Für 1.0 eine fachkundige Prüfung von L-01 bis L-04 empfehlenswert.*

| Nr. | Bereich | Schwere | Beschreibung | Fundstelle | Vorschlag | Aufwand | Beleg |
|---|---|---|---|---|---|---|---|
| L-01 | LGPL | hoch | pycdlib (LGPL-2.1) liegt als Bytecode im PYZ-Archiv der Programmdatei, nicht als austauschbare Datei in `_internal` – entgegen dem Text in THIRD-PARTY-LICENSES. Austauschbarkeit (LGPL-2.1 §6) vermutlich nicht erfüllt. Ähnlich, weniger heikel: Python-Teile von PySide6/shiboken6. | `THIRD-PARTY-LICENSES:26-28`; `packaging/bonys-agents.spec:73-93` | `module_collection_mode={'pycdlib': 'py'}` (lose .py), oder pycdlib durch eigenen Code/`xorriso` ersetzen; Text anpassen. | klein–mittel | ✔ (im .deb kein pycdlib-Ordner) |
| L-02 | Lizenztexte | hoch | Mitgelieferte Teile ohne Lizenztext: OpenSSL 3 (Apache-2.0 verlangt Kopie), krb5, libjpeg, ICU, Qt-Drittteile (harfbuzz, pcre2, libpng, zlib, md4c, libwebp, libtiff …), Python-Bestandteile (libmpdec, expat, libffi, bzip2, xz). Für Windows/macOS fehlt das komplett; fürs .deb wird nur auf das Zielsystem verwiesen. Umgekehrt listet THIRD-PARTY Bibliotheken, die gar nicht gebündelt werden. | `THIRD-PARTY-LICENSES:13-60`; `.deb: /opt/bonys-agents/_internal/libssl.so.3, libcrypto.so.3, libkrb5*, libjpeg.so.8, libicu*` | Beim Bauen je Plattform aus dem tatsächlichen Inhalt erzeugen (`pip-licenses --with-license-file`, Qt-Attributions, Python-`LICENSE.txt`). | mittel | ✔ (Inhalt `_internal`) |
| L-03 | LGPL-3 | mittel | Quellangebot für Qt/PySide6 nur allgemein auf download.qt.io; Version im Release wegen ungepinnter Builds nicht sicher. | `THIRD-PARTY-LICENSES:30-35`; siehe P-04 | Versionen festlegen, genauen Quell-Link je Release. | mittel | (C) |
| L-04 | `.bonys` | mittel–hoch | Wer eine `.bonys` weitergibt, verbreitet Debian (GPL-Pakete), Telegram (GPL-3), Brave-Binärdateien, Docker-Images – ohne Hinweis auf Quellpflichten. Ob Brave die Weitergabe in VM-Images erlaubt, ist ungeklärt. (Claude Code und Obsidian werden korrekt entfernt.) | `bonysfile.py:14,252,679`; `apps.py:45` | Hinweis im Export-Dialog/README (Quellen über sources.debian.org/Flathub), Paketliste ins Manifest; Brave-Bedingungen prüfen, ggf. `redistributable=False`. | mittel | (C) |
| L-05 | Bilder | mittel | Hintergrundbilder sind KI-generiert (C2PA: ChatGPT/GPT-4o); Herkunft/Lizenz der Bilder und des Logos nirgends angegeben; „Name und Logo ausgenommen“ trägt bei KI-Bildern womöglich nicht. | `Bilder/hintergrund_program.png` → `resources/background.jpg`, `wallpaper.jpg` (`packaging/make-resources.py:56,64`); `README.md:946-948` | Abschnitt „Bilder und Logo“ (Herkunft, Lizenz); Logo-Herkunft klären. | klein | (C) |
| L-06 | GPL-Hinweise | gering | „Über“-Fenster ohne Gewährleistungsausschluss (GPL-3 „Appropriate Legal Notices“) und ohne Quelltext-Link. SPDX fehlt in 21 Nicht-Python-Dateien (Skripte, Workflows, JS/HTML). | `gui/about_dialog.py:49-58` | Eine Zeile + Link; SPDX ergänzen. | klein | (C) |
| L-07 | Datenschutz | gering | Homebrew-Installation ohne `HOMEBREW_NO_ANALYTICS`. Markennamen (Claude, Hermes, OpenClaw, Telegram, Brave, Obsidian, WireGuard®) beschreibend genutzt – Zeile „Marken gehören ihren Inhabern, keine Verbindung“ sinnvoll. | `deps.py:192` | Ergänzen. | klein | (C) |

### Code-Qualität und Tests (Q)

| Nr. | Bereich | Schwere | Beschreibung | Fundstelle | Vorschlag | Aufwand | Beleg |
|---|---|---|---|---|---|---|---|
| Q-01 | Tests | mittel | Ungetestet: eigentliche Selbstinstallation der Updates (`install_linux/windows/macos`, Neustart), Image-Download + Hash (`images.ensure_image`), `vm.delete` (nur indirekt), QMP nur über Fakes; GUI ohne Test: `move_dialog`, `desktop_dialog`, `resize_dialog`, `setup_dialog`, `remote_panel`, `location_picker`, `workers`. Kein Coverage-Lauf. | `updates.py:376-436`; `images.py:68` | Unit-Tests mit Fake-Opener/monkeypatch (Muster existiert); `pytest-cov` in CI. | mittel | (C) |
| Q-02 | Tests | mittel | Zeitabhängige Tests (`sleep` + harte Annahmen, Negativ-Prüfungen nach `sleep(0.3)`, Bildraten-Grenzen) – auf langsamen CI-Rechnern wackelig. | `tests/test_core.py:1365,1372`; `tests/test_present.py:335-342`; `tests/test_helpmode.py:148-184` | `_wait(cond, timeout)`, Rückmeldungen statt Schlafen. | klein | (C) |
| Q-03 | Struktur | mittel | Große Dateien/Funktionen: `vm.py` 1728 Z. („Gott-Klasse“ VM), `main_window.py` 1515, `cli.py` 1495; `_detail_page` 284 Z., `build_parser` 233 Z., `CreateDialog.__init__` 228 Z. | `gui/main_window.py:469`; `cli.py:1242`; `gui/create_dialog.py:48` | Nach 1.0 schrittweise aufteilen. | groß | (C) |
| Q-04 | Doppelungen | mittel | Zehn fast gleiche QThread-Worker; `mc_panel` ≈ `vpn_panel`; Aufräumblock in `create`/Klonen doppelt; Statuszeile mit Fortschritt vierfach. | `gui/workers.py:13,34`; `gui/mc_panel.py:205-237` ≈ `gui/vpn_panel.py:258-290`; `vm.py:1625-1640` ≈ `1708-1722` | Generischer `FnWorker`, Basisklasse `GuestAppPanel`, Hilfsfunktion. | klein–mittel | (C) |
| Q-05 | Muster | mittel | Gast-Skripte werden per `r"""…""" + KONST + r"""…"""` zusammengesetzt – fehleranfällig (die Streudatei zeigt, wie leicht das schiefgeht). | `mission_control.py:225-245,383-405`; `wallpaper.py:77` | `string.Template`/f-Strings mit `shlex.quote`; `bash -n`-Test für jedes erzeugte Skript. | mittel | ✔ |
| Q-06 | Toter Code | gering | Ungenutzt: `hostvpn.supported()`, `screen.guest_check_script()`; nur in Tests: `vm.vms_dir`, `VM.install_app`, `apps.required_by`, `cloudinit.personal_data_paths`, `share_server.locked`, `templates.export` u. a.; viele Kompatibilitätszweige „bis 0.6/0.14/0.16“. | `hostvpn.py:74`; `screen.py:308`; u. a. | Für 1.0 entscheiden, welche Migrationspfade bleiben; Rest entfernen. | klein | (C) |
| Q-07 | Stil | gering | `ruff format --check` würde 75 Dateien umformatieren (Formatierer wird offenbar bewusst nicht genutzt); 30+ verstreute `sys.platform`-Prüfungen neben `host.detect()`. | – | Entscheidung dokumentieren; zentrale `IS_WINDOWS/…`. | klein | ✔ |

### Nachbarprojekte (N)

| Nr. | Projekt | Schwere | Beschreibung | Fundstelle | Vorschlag | Aufwand | Beleg |
|---|---|---|---|---|---|---|---|
| N-01 | bonys-vpn | mittel | Kill-Switch filtert nur `output`, nicht `forward` → Docker-Container im Agent-PC (Mission Control u. a.) gehen bei Tunnel-Ausfall ungeschützt ins Netz. (Grenze steht in `docs/sicherheit.md:124`, im Agent-PC ist Docker aber der Normalfall.) | `bonys-vpn/src/bonys_vpn/killswitch.py:63-67` | Zweite Kette `hook forward` mit `policy drop`. | mittel | (C) |
| N-02 | bonys-vpn | mittel | Ausnahme `10.0.2.0/24` schließt QEMU-DNS 10.0.2.3 ein → DNS-Leck auch bei aktivem Kill-Switch. | `install.py:52`; `build-deb.sh:168` | Auf 10.0.2.2/32 beschränken; Warnung bei .conf ohne `DNS=`. | klein | (C) |
| N-03 | bonys-vpn | gering–mittel | Kill-Switch fällt still offen (`systemctl restart nftables`/`nft flush ruleset`, Regeldatei lädt nicht). | `data/bonys-vpn-killswitch.service:6-12`; `helper.py:192` | Bei `enabled && !active` warnen/neu laden. | klein | (C) |
| N-04 | bonys-vpn | gering | Kill-Switch-Ausnahmen (DNS für root zu beliebigen Servern, Endpunkt für jeden Prozess); TOCTOU beim Update wie S-14; Actions per Tag. | `killswitch.py:41-52`; `updates.py:362-392`; `release.yml:78` | Einschränken, SHA-Pinning. | mittel | (C) |
| N-05 | Mission Control | mittel | Release-Bundle und `SHA256SUMS` nicht signiert, Docker-Image per veränderbarem Tag (`:0.1.0`); Bony's Agents pinnt nur `install.sh`. `update.sh` prüft nur gegen unsignierte Sums. | `scripts/install.sh:131-148,202-208`; `deploy/compose.yaml:7` | `SHA256SUMS` mit minisign signieren, Image per Digest pinnen, ohne Sums abbrechen. | mittel | (C) |
| N-06 | Mission Control | gering–mittel | root folgt Symlinks beim Anlegen der Desktop-Verknüpfung (Pfad aus nutzergesteuerter `user-dirs.dirs`); gleiches Muster in `bonys-agents/apps.py:321-322`. Im Agent-PC praktisch folgenlos (Benutzer hat sudo). | `scripts/lib.sh:120-171` | Als Benutzer schreiben (`runuser`). | klein | (C) |
| N-07 | Mission Control | gering | Keine Authentisierung/Host-Header-Prüfung (DNS-Rebinding auf 127.0.0.1:18787, nur lesend); `.local.yml` nicht ausgeblendet; `startsWith(distDir)` ohne Trenner; Dev-Server auf 0.0.0.0. Zusammen mit S-01: andere Agent-PCs erreichen den Host-Port über 10.0.2.2. | `server/server.mjs:22-58,141,179,219,248-250`; `package.json:7,10` | Host-Header prüfen, Token nutzen, Regex `ya?ml`, `distDir + sep`. | klein | (C) |

---

## Muss vor 1.0

1. **S-01** VM-Ausbruch über QMP/QGA/SPICE (Unix-Sockets bzw. Passwort, Windows-Lösung).
2. **S-03** Importierte Platten auf `data_file`/Backing prüfen bzw. umschreiben.
3. **S-04** `vm.json`/alte Vorlagen beim Laden validieren; Remmina/.rdp-Werte escapen.
4. **S-02** mDNS-Fingerabdruck nicht ohne Bestätigung vertrauen.
5. **P-01** APT-Workflow: minisign prüfen, ohne Sums abbrechen, Paketnamen je Repo.
6. **P-02 + P-03** Release nur nach grünen Tests; Workflow-Rechte/Secrets eng, Actions auf SHA.
7. **R-01** Verschieben: `fsync` vor dem Löschen der Quelle.
8. **R-03** PID-Prüfung über `qemu.pid` mit Befehlszeile/Startzeit.
9. **R-05 + R-06** `vm.json` atomar schreiben; Formatversion für `vm.json`/`template.json` einführen (nach 1.0 kaum noch nachrüstbar).
10. **R-02** Fehlgeschlagene Einrichtungsschritte sichtbar machen („fertig mit Fehlern“), Timeouts für Fremd-Downloads.
11. **L-01 + L-02** pycdlib austauschbar machen; Lizenztexte aller gebündelten Teile je Plattform beilegen.
12. **U-03 + U-04 + U-05** deutsche Qt-Knöpfe, sicherer Standardknopf beim Löschen, Absturzprotokoll.
13. **D-01 + D-03 + D-04** README-Dateinamen, Datenschutz-Abschnitt, `.gitignore`/interne Dateien aufräumen.
14. **P-05 / P-06 (Entscheidung)** Windows-/macOS-Signatur – mindestens die SmartScreen-/Gatekeeper-Anleitung in die README, Signatur nach Budget.

## Sollte vor 1.0

- **S-05, S-06, S-08, S-09, S-10** Kurs-Server härten (RFB-CPU, Verbindungslimits, kein Abschießen per Fehlversuchen, Plain-Text).
- **R-04** Sperre je Agent-PC + Einzelinstanz der GUI.
- **R-07, R-10, R-11, R-12, R-13, R-14** Platzprüfung/Pause erkennen, Sperren nach Neustart, RAM-Warnung, Download fortsetzbar/abbrechbar, Obsidian ohne API-Limit, halbe Ordner aufräumen.
- **U-01, U-02, U-06, U-07, U-08, U-10** verständliche Fehlertexte, echte Beschleunigung prüfen, QEMU-Fenster-X, Einrichtungsdialog nicht ständig, „Gast-Agent“ ersetzen.
- **D-02** Schnellstart mit Screenshots, Systemanforderungen, FAQ, `SECURITY.md`, Fehler melden, Deinstallation.
- **L-03, L-04, L-05, L-06** Qt-Quellangebot, Hinweis beim `.bonys`-Export, Bildherkunft, Gewährleistungshinweis.
- **P-04, P-07, P-10, P-13** gepinnte Builds, Update-/Purge-Tests in CI, `Valid-Until`, APT-Zeitplan absichern.
- **N-01, N-02, N-05** Kill-Switch `forward` + DNS, Mission Control signieren/Image pinnen.
- **Q-01** Tests für Update-Installation, Image-Download, Löschen.

## Kann später

S-07, S-11, S-12, S-13, S-14, S-15 · P-08, P-09, P-11, P-12, P-14 · R-08, R-09, R-15, R-16 · U-09, U-11 bis U-15 ·
D-05, D-06, D-07 · L-07 · Q-02 bis Q-07 · N-03, N-04, N-06, N-07.

---

## Vorschlag: Aufteilung der „Muss“-Punkte in Claude-Code-Sitzungen

| Sitzung | Inhalt | Punkte | Hinweise |
|---|---|---|---|
| 1 – VM-Isolation | QMP und Gast-Agent auf Unix-Sockets (Linux/macOS), SPICE lokal per Unix-Socket/Passwort, Windows-Lösung (Named Pipe bzw. Passwort, VNC mit Passwort), `-sandbox` unter Linux; Test, dass keine TCP-Steuerports mehr entstehen; Laufzeitdaten alter Agent-PCs migrieren (Neustart nötig → Hinweis). | S-01 | Größter Brocken. Danach mit echtem Agent-PC prüfen (Anleitung unten). Mission-Control-Weiterleitung (N-07) mitdenken. |
| 2 – Import-Härtung | `qemu-img info`-Prüfung bzw. Umschreiben bei `.bonys`/Vorlagen/Laufwerken; Schema-Prüfung für `vm.json`/`template.json`/alte `.bonys-template`; Escapen in Remmina/.rdp; Formatversion einführen. | S-03, S-04, R-06 | Testdateien mit präparierter qcow2 (`data_file`) und bösartiger `vm.json`. |
| 3 – Datenrobustheit | `fsync` beim Verschieben, atomares `vm.json`/`runtime.json`, `.bak`, PID-Prüfung, Einrichtungsfehler sichtbar machen, `--max-time` für Fremd-Downloads. | R-01, R-02, R-03, R-05 | R-04 (Sperren) passt gut dazu, falls Zeit bleibt. |
| 4 – Release-Kette | `apt-repo.yml` mit minisign, Paketnamen je Repo, Release `needs` Tests, `permissions`, SHA-Pinning, harter Abbruch ohne minisign-Secret. | P-01, P-02, P-03 | Kann ohne lokale Builds erfolgen; in GitHub zusätzlich Tag-Schutz für `v*` einrichten (manuell). |
| 5 – Lizenzen | pycdlib als lose `.py` (oder ersetzen), Lizenz-Sammelskript für alle Plattformen, THIRD-PARTY je Paket erzeugen, „Über“-Fenster ergänzen. | L-01, L-02 (+ L-06) | Danach .deb-Inhalt prüfen; Windows/macOS über CI-Artefakte. |
| 6 – Laien-Feinschliff | `QTranslator`, sichere Standardknöpfe, `sys.excepthook` + `fehler.log`, README-Dateinamen, SmartScreen-Anleitung, Datenschutz-Abschnitt, `.gitignore`/interne Dateien. | U-03, U-04, U-05, D-01, D-03, D-04, P-05/P-06 (Doku) | Klein und gut kombinierbar. |
| 7 – Kurs-Vertrauen | mDNS-Fingerabdruck nur nach Bestätigung (+ gleich S-05/S-08/S-10 mitnehmen, alle klein). | S-02 (+ Sollte-Punkte) | Test: falscher TXT-Eintrag → Checkbox muss erscheinen. |

Signatur unter Windows/macOS (P-05/P-06) ist vor allem eine Konto- und Kostenentscheidung; die Pipeline ist für macOS schon vorbereitet.

---

## Was ausdrücklich GUT gelöst ist (bei Änderungen nicht kaputt machen)

- **Updates:** minisign (Ed25519, Schlüssel-ID-Abgleich), signierter Kommentar muss *genau* die Version nennen (Schutz vor Rollback), nur HTTPS, nur URLs des offiziellen Releases, Größenlimits, `.part` + `os.replace`, Updates bleiben in der eigenen Edition (`updates.py:224-290`, `asset_for`, `--only-upgrade`).
- **Keine Geheimnisse:** gitleaks findet nichts in 45 Commits, Arbeitsordner und beiden .deb 0.19.0; `Software/` (NoMachine) nie in der Historie; keine Telemetrie.
- **Kein `shell=True`/`os.system`** im ganzen Paket; Argumentlisten überall.
- **`.bonys`-Import:** nur reguläre Dateien mit genau erwarteten Namen, keine Pfade/Links/Geräte (`bonysfile.py:505-518`), Größen- und SHA256-Prüfung je Datei, `format_version`/`min_version` mit verständlicher Meldung, strenge Manifest-Prüfung inkl. Benutzername (`bonysfile.py:381-420`), Abbruch mit Aufräumen.
- **Vorlagen verallgemeinern:** Verlauf-Dateien, `machine-id`, SSH-Host-Keys, cloud-init-Zustand, Leases, Journal werden entfernt (`cloudinit.py:556ff`); Claude Code und Obsidian werden beim Weitergeben entfernt (`redistributable=False`); Geheimnis-Prüfung zeigt nie Inhalte.
- **Nur-Ansehen im Proxy erzwungen** (`rfb.py:503-531`): Key/Pointer nur mit Zustimmung, Zwischenablage/XVP/QEMU-Erweiterungen nie, SetEncodings per Positivliste, Längenfelder begrenzt.
- **Kurs-Server:** Code ≈ 31 Bit mit `hmac.compare_digest`, 5 Versuche/60 s je Adresse, Code nie in URL/Log/mDNS; Fingerabdruck-Pinning bei Link/QR; strikte CSP, `X-Frame-Options DENY`, Cookies `Secure/HttpOnly/SameSite=Strict` (nur Hash gespeichert), Origin-Prüfung, statische Dateien per Positivliste, JS nur `textContent`.
- **Steuern im Hilfe-Modus** nur nach Zustimmung beim Teilnehmer; Rechte liegen nur im Client (`helpmode.py:285,311`).
- **VNC unter Linux/macOS:** Unix-Socket im 0700-Ordner mit Eigentümer-/Symlink-Prüfung (`vm.py:105-116`); `vnc_option` erlaubt nie eine Netzadresse (`qemu.py:206-220`). *Genau dieses Muster ist die Lösung für S-01.*
- **Ersteinrichtung fortsetzbar** nach Abbruch/Stromausfall (Schrittmarkierungen mit `sync`, `dpkg --configure -a`, apt-Sperre), Ursache bei Abbruch (`diagnose.explain_abort`); Seed-ISO mit Passwort 0600 und nach Einrichtung gelöscht.
- **Editionswechsel .deb/Windows** sauber (gegenseitiges `Replaces`, `Provides`, eine AppId, `[InstallDelete]`), in der CI in beide Richtungen getestet; Agent-PCs werden bei Deinstallation nie gelöscht.
- **APT-Quelle:** deb822 mit `Signed-By` auf eigenen Keyring, zwei Suiten gegen `Signed-By`-Konflikte mit bonys-vpn.
- **udev `uaccess`** statt Gruppe `kvm` → keine Neuanmeldung nötig.
- **noVNC** fest auf Version + SHA-256, nur in der Kursleiter-Edition, Lizenzen beiliegend. **Mission Control** fest auf Version + `INSTALL_SHA256`, Port nur an 127.0.0.1, Weiterleitung standardmäßig aus.
- **bonys-vpn Root-Helfer:** feste Unterbefehle, .conf über stdin (≤ 64 KiB), Allowlist-Parser, Hooks nur mit Admin-Passwort, `O_NOFOLLOW`, `flock`, atomar, Schlüssel nie in Ausgaben; Bony's Agents lehnt Hook-Konfigurationen schon auf dem Host ab.
- **Tests:** 435 Tests, vom Internet abgeschottet, CI auf Linux/macOS/Windows × Python 3.10/3.13 und beiden Editionen; erzeugte Gast-Skripte per `bash -n`.

---

## Was NICHT geprüft werden konnte – und wie du es selbst prüfst

| Thema | So prüfst du es |
|---|---|
| **S-01 im echten Agent-PC** | In `runtime.json` des Agent-PCs den `qmp_port` nachsehen. Im Agent-PC ein Terminal öffnen: `timeout 2 bash -c 'cat < /dev/tcp/10.0.2.2/PORT'`. Erscheint eine Zeile mit `{"QMP": …`, ist der Weg offen (nur lesen, nichts weiter senden). Nach der Behebung muss die Verbindung scheitern. |
| Windows (SmartScreen, WHPX ohne BIOS-Virtualisierung, Deinstallation, PowerShell-Ruckeln) | Frische Win-11-VM ohne verschachtelte Virtualisierung: Setup per Edge laden, SmartScreen/UAC ansehen, Agent-PC anlegen, Dauer messen, `qemu.log` nach „WHPX“ durchsuchen; Kursleiter-Setup darüber, dann deinstallieren; danach `wf.msc` (Regeln „Bony's Agents“), `winget list qemu`, Programmordner prüfen. Setup bei VirusTotal hochladen. |
| macOS (Gatekeeper ab 15, Intel, lokales Netzwerk, Freigaben nach Update) | Echter Mac (Intel + Apple-Chip): .dmg per Safari, Erster-Start-Anleitung durchspielen, Kursleiter starten (Abfrage „Lokales Netzwerk“?), Update aus der App, prüfen ob Freigaben erneut kommen; `spctl -a -vv`, `codesign -dv --verbose=4`. |
| .deb entfernen/purge, Update über echte APT-Quelle | VM oder `docker run -it debian:trixie`: 0.18.0 installieren, Daten anlegen, `apt upgrade`; dann `apt purge bonys-agents-kursleiter`, auf dpkg-Warnungen achten, `ls /opt /var/lib/bonys-agents /etc/apt/sources.list.d`. `lintian` auf einem Debian-System. |
| Robustheit unter echten Bedingungen | Test-Agent-PC: (a) auf USB-SSD verschieben und *sofort* abziehen, (b) bei laufender VM SSD abziehen, (c) Datenträger fast voll laufen lassen, (d) zwei Programmfenster + gleichzeitiger Start, (e) WLAN während der Einrichtung trennen. |
| Remmina-Befehlsausführung bei S-04 | Nicht ausprobiert; Wirkung von Zeilen-Injektion hängt von der Remmina-Version ab. |
| Release-Artefakte auf GitHub, Secrets, Tag-Schutz | GitHub → Settings → Actions (Standardrechte „Read“), Rulesets für `v*`, gesetzte `APPLE_*`-Secrets; Releases von Mission Control/VPN mit Quellen vergleichen. |
| Lizenzen | Inhalte der Windows-/macOS-Bündel (lokal nur .deb vorhanden); Brave-Weitergabebedingungen; Herkunft `Bilder/logo.jpg`; ggf. Impressumspflicht (YouTube/kommerzielle Lizenz) – fachkundig prüfen lassen. |
| Kill-Switch zur Laufzeit (N-01 bis N-03), `npm audit` für Mission Control | Benötigt laufenden Agent-PC mit root bzw. Netz; nicht ausgeführt. |
| Echte Testabdeckung | `pytest-cov` war nicht installiert (nichts installiert); Zuordnung oben ist per grep. |

Hinweise zur Prüfung selbst: Ein Prüfagent hat bei einem Experiment kurz den Status deiner echten Agent-PCs unter
`/media/zappotex/bonysagent/BonysAgents` gelesen – geändert wurde nichts (Änderungszeiten geprüft). Der
Ausbruchs-Nachweis lief in einer eigenen Wegwerf-VM im Scratchpad; sie ist beendet. Eine der acht Prüfungen brach
durch einen API-Fehler vorzeitig ab; ihre restlichen Punkte (Entpacken, Shell-Aufrufe, Dateirechte, Verallgemeinerung,
Validierung von `vm.json`) wurden selbst nachgeprüft.
