# Plan: Schulungen – Agent-PCs weitergeben

Agent-PCs (genauer: **Vorlagen**) an andere Rechner weitergeben, z. B. für eine Schulung: Der Kursleiter
richtet einen Agent-PC einmal ein, macht daraus eine frische Vorlage und gibt sie an die Teilnehmer weiter.

Jede Sitzung liest zuerst diese Datei und aktualisiert am Ende den Abschnitt [Stand](#stand).

## Ziele

- Eine Vorlage wird zu **einer Datei** (`NAME-VERSION.bonys`), die man per USB-Stick, Cloud oder Netzwerk
  weitergibt und mit einem Klick (oder per Drag & Drop) importiert.
- In der Datei stecken **keine Geheimnisse** des Kursleiters (Anmeldungen, Tokens, Schlüssel, Verläufe).
  Das wird vor jedem Export im Image geprüft, nicht nur angenommen.
- **Keine Lizenzverstöße**: Nicht frei weitergebbare Programme (Claude Code, Obsidian) werden vor dem Export
  aus der Kopie entfernt und beim Empfänger aus der offiziellen Quelle neu installiert.
- Jeder Agent-PC, der aus einer weitergegebenen Vorlage entsteht, bekommt **eigene Identität**: neue
  Maschinen-ID, neue SSH-Hostschlüssel, neue Geheimnisse (z. B. Mission Control).
- Im Kursraum (LAN) oder im VPN (Bony's VPN/WireGuard) geht die Weitergabe auch **ohne Datei-Herumreichen**.

## Stufen

### Stufe 1 – Paketformat `.bonys` (Export/Import als Datei) ✅ erledigt (0.17.0)

- **Format**: unkomprimiertes tar mit
  1. `manifest.json` (immer das erste Element, schnell lesbar),
  2. `preview.png` bzw. `preview.jpg` (optional, Vorschaubild),
  3. `disk.qcow2` – komprimiert (`qemu-img convert -c`) und eigenständig (kein Backing-File).
- **Manifest**: Formatkennung und -version, Name, Beschreibung, Ersteller, Exportdatum, Erstelldatum der
  Vorlage, Mindestversion von Bony's Agents, Architektur (`amd64`/`arm64`), Desktop(s), Debian-Version,
  Benutzername, Tastatur, Zeitzone, installierte Apps mit Versionen, Apps zum Neu-Installieren, empfohlene
  RAM/CPU/Festplatte, Größe und SHA-256 jeder Datei, Ergebnis der Frisch-Prüfung.
- **Export** (`templates`-Ansicht bzw. `bonys-agents template export NAME DATEI`):
  1. Nur von frischen Vorlagen. Bei Klonen (mit persönlichen Daten) wird „frisch machen“ angeboten: Die
     persönlichen Daten werden dann nur in der Export-Kopie entfernt, die Vorlage bleibt unverändert.
  2. Eine Überlagerung der Vorlage startet ohne Netz (wie beim Erstellen einer Vorlage).
  3. **Frisch-Prüfung** im Image (siehe Sicherheitsregeln). Funde werden verständlich angezeigt (nur Art und
     Pfad, nie Inhalte) und blockieren den Export, bis bereinigt ist.
  4. Nicht weitergebbare Apps entfernen (`AppSpec.redistributable=False`, Entfernen über `AppSpec.uninstall`).
  5. Versionen der Apps abfragen, Passwort-Hashes sperren, verallgemeinern (wie beim Erstellen einer
     Vorlage, inkl. Nullen des freien Platzes), danach **zweite Prüfung** – streng, jetzt auch Hostschlüssel,
     Maschinen-ID und Geheimnisse von Mission Control. Ein Fund hier bricht ab.
  6. `qemu-img convert -c` → SHA-256 → tar. Fortschritt in Prozent, jederzeit abbrechbar (räumt auf).
- **Import** (Datei wählen oder Drag & Drop auf das Vorlagen-Fenster bzw. `template import DATEI [--create NAME]`):
  Manifest anzeigen (Inhalt, Ersteller, Größe, Architektur), Formatversion und Mindestversion prüfen,
  SHA-256 beim Entpacken prüfen, `qemu-img check`, eigenständig? → als Vorlage übernehmen. Optional direkt
  einen Agent-PC daraus (Name, Speicherort, RAM/CPU). Danach die vermerkten Apps über „Programme hinzufügen“.
- **Erster Start** eines Agent-PCs aus einer Vorlage (gab es schon, gilt auch hier): cloud-init sieht eine neue
  Instanz → neue Maschinen-ID; SSH-Hostschlüssel, xrdp- und snakeoil-Zertifikate neu; Passwort neu; Mission
  Control erzeugt seine Geheimnisse beim ersten Start neu (Platzhalter `__GENERATE__`).
- **Architektur**: Passt sie nicht (z. B. amd64-Vorlage auf einem Mac mit Apple-Chip), deutliche Warnung
  („läuft nur sehr langsam“, Emulation mit TCG) und als Alternative das **Rezept**: Desktop, Apps,
  Tastatur, Zeitzone aus dem Manifest → ein neuer Agent-PC wird mit dem passenden Debian-Image normal
  eingerichtet (`template import DATEI --recipe NAME`).
- Das alte Format `.bonys-template` (bis 0.16) lässt sich weiter importieren, exportiert wird nur noch `.bonys`.

### Stufe 2 – Freigabe im Netzwerk (LAN oder VPN) ✅ erledigt (0.17.0)

- **Kursleiter**: Vorlagen-Ansicht → „Im Netzwerk freigeben“. Ein eingebauter HTTPS-Server (Python-Standard-
  bibliothek, nur solange freigegeben, Standardport **47110**, wählbar) liefert genau eine `.bonys`-Datei aus
  (einmal erzeugt, unter `<Speicherort>/_templates/.freigabe-cache/` zwischengespeichert, solange die
  Vorlage sich nicht ändert).
  Anzeige: Freigabe-Code (z. B. `4711-BONY`: 4 Ziffern + 4 Buchstaben ohne verwechselbare Zeichen),
  Adresse(n) des Rechners, QR-Code mit `bonys://ADRESSE:PORT?code=…&fp=…`, Liste der Teilnehmer mit
  Fortschritt, Knopf „Freigabe beenden“.
- **Sicherheit**: selbstsigniertes Ed25519-Zertifikat pro Freigabe (ohne neue Abhängigkeit: X.509 in
  `share.make_certificate`, signiert mit `signing.ed25519_sign`), Fingerabdruck SHA-256 wird bei beiden
  angezeigt bzw. kommt im QR-Code/über mDNS mit, Zugriff nur mit Code (Header `X-Bonys-Code`, konstante
  Vergleichszeit, 5 Fehlversuche je Adresse → 1 min Sperre, 100 insgesamt → Freigabe endet), automatisches
  Ende nach einstellbarer Zeit (Standard 120 min), nur GET/HEAD auf `/bonys/v1/info` und `/bonys/v1/download`,
  keine anderen Dateien erreichbar.
  Firewall: Hinweise für Windows (Abfrage „Zugriff zulassen“ – nur „Private Netzwerke“), macOS und Linux
  (ufw/firewalld: Port nur vorübergehend, nichts dauerhaft öffnen).
- **Teilnehmer**: „Schulung beitreten“ → Freigaben im gleichen Netz per mDNS/Zeroconf finden
  (`_bonys-agents._tcp`, eigenes kleines mDNS in `mdns.py`, verträgt sich mit Avahi), alternativ Adresse+Code
  eintippen oder QR-Inhalt einfügen (VPN: kein mDNS). QR-Code über das Paket `qrcode` (BSD, reines Python). Fingerabdruck wird
  geprüft (TOFU nur nach Bestätigung, wenn keiner mitkam). Download mit Fortschritt und Restzeit, Fortsetzen
  per HTTP-Range, SHA-256-Prüfung, dann weiter wie Import (Stufe 1).
- **Bandbreite**: höchstens N gleichzeitige Downloads (Standard 4, einstellbar), der Rest wartet in einer
  Schlange (Position wird dem Teilnehmer angezeigt).
- **CLI**: `bonys-agents share NAME [--port P] [--timeout MIN] [--max-downloads N]`,
  `bonys-agents join ADRESSE CODE [--fingerprint FP] [--create NAME]`.

### Stufe 3 – Live-Vorführung (A) und Hilfe-Modus (B) ✅ erledigt (0.18.0)

Ab 0.19.0 liegen Server und Kursleiter-Dialoge in `trainer/` (`trainer/present.py`, `trainer/helpdesk.py`,
`trainer/gui/…`, Seiten und noVNC unter `trainer/resources/`), siehe `docs/editionen.md`.

**A – Vorführen** (`present.py`, `rfb.py`, `websocket.py`, `gui/present_dialog.py`, Seiten unter
`resources/present/`):

- **VNC nur lokal:** QEMU startet jeden Agent-PC zusätzlich mit `-vnc unix:PFAD,share=force-shared,lossy=on`
  (Socket in `$XDG_RUNTIME_DIR/bonys-agents-UID/` bzw. Temp-Ordner, Ordner 0700; Windows: `127.0.0.1:N`,
  Port 5900–5999). VNC lässt sich zur Laufzeit **nicht** hinzufügen (QMP `display-update` braucht ein schon
  vorhandenes VNC, geprüft in QEMU 8.2 `ui/vnc.c`) – laufende Agent-PCs aus älteren Versionen brauchen einen
  Neustart (Dialog: „Jetzt neu starten“). `runtime.json` → `vnc`, `VM.vnc_available()/vnc_connect()`.
- **noVNC 1.7.0** (MPL-2.0) holt `packaging/fetch-novnc.py` beim Bauen aus dem GitHub-Release (feste SHA-256),
  nur `core/`, `vendor/pako/` und Lizenztexte nach `src/bonys_agents/resources/novnc/` (gitignored, im Wheel per
  hatch `artifacts`). Eingebunden in build-deb.sh, build-setup.ps1, release.yml (Windows/macOS).
- **Server:** HTTPS wie Stufe 2 (`share.Guarded`: Code, 5 Fehlversuche → 1 min Sperre, 100 → Ende, Zeitlimit),
  Zertifikat aber **ECDSA P-256** (Browser können kein Ed25519; reines Python in `share.make_certificate(kind="ec")`,
  mit subjectAltName). Standardport **47120**. Startseite `/` (Name + Code, Code kommt aus dem QR-Code hinter `#`),
  `POST /bonys/v1/present/join` → Cookie (HttpOnly, Secure, SameSite=Strict; gespeichert nur als SHA-256),
  `/view`, `/novnc/core|vendor/*.js` (nur mit Cookie), `GET /bonys/v1/present/status`, WebSocket
  `/bonys/v1/present/ws` (Origin muss passen), `GET /bonys/v1/info` (mit Code, `kind: present` – „Kurs beitreten“
  erkennt so Vorführungen). CSP ohne Inline-Skripte. mDNS wie Stufe 2 mit `kind=present`.
- **Zuschauen serverseitig erzwungen** (`rfb.ClientFilter`): Handshake nur Sicherheitstyp None, ClientInit immer
  „geteilt“; durch gehen nur SetPixelFormat, SetEncodings (Weißliste ohne Extended Clipboard, QEMU-Tastatur/-Ton,
  XVP, Fence, ContinuousUpdates; JPEG-Qualität/Kompression setzt der Proxy) und FramebufferUpdateRequest.
  Key/Pointer nur, wenn `allow_input()` (für B), ClientCutText/XVP/QEMU-Nachrichten immer verworfen, Unbekanntes
  beendet die Verbindung. QEMU schickt seine Zwischenablage nur an Clients mit Extended Clipboard
  (`ui/vnc-clipboard.c`) – also auch nichts in Gegenrichtung.
- **Proxy-Schleife** je Zuschauer in einem Thread mit `select` (TLS-Sockets nie aus zwei Threads),
  FramebufferUpdateRequests gedrosselt auf die Bildrate (low 5, medium 10, high 20 Bilder/s; über 8 Zuschauern
  anteilig weniger; CPU des Prozesses > 80 % → weniger), zusammengefasst (eine vollständige Anfrage bleibt
  vollständig).
- **Pause** trennt alle Zuschauer vom VNC (WebSocket-Code 4001) und lässt keine neuen zu – kein einziges Bild,
  auch nicht die Antwort auf eine schon gestellte Anfrage. Die Seite zeigt „Gleich geht's weiter“ und verbindet
  danach neu. Entfernen: 4003, Adresse 5 min gesperrt. Ende: 4000 (Zeit, Agent-PC aus, Kursleiter).
- **Teilnehmer in Bony's Agents:** „Kurs beitreten“ listet Vorführungen (mDNS) und öffnet sie im Browser; auch
  beim Eintippen der Adresse (`share.IsPresentation`).
- **CLI:** `bonys-agents present NAME [--port P] [--timeout MIN] [--max-viewers N] [--quality low|medium|high]`.

**B – Hilfe-Modus** (umgesetzt, siehe Stand; Vorgaben aus dem Auftrag):

- Teilnehmer (der Schulung beigetreten) → „Hilfe anfordern“ (optional Nachricht) beim eigenen Agent-PC →
  Kursleiter sieht Liste „Hilfe-Anfragen“ mit Benachrichtigung (Name, Nachricht, Zeit, „Ansehen“).
- Ansehen erst nach Zustimmung des Teilnehmers („Erlauben/Ablehnen“), „Steuerung übernehmen“ nur mit **zweiter**
  Zustimmung; Teilnehmer kann jederzeit beenden oder auf „nur ansehen“ zurückstufen; gut sichtbarer Hinweis
  beim Teilnehmer (wenn möglich auch im Agent-PC).
- Technik: Verbindung **vom Teilnehmer zum Kursleiter** (ausgehend, HTTPS/WebSocket, Code + Fingerabdruck wie
  Stufe 2), tunnelt den lokalen VNC-Socket des Teilnehmers; Eingaben prüft **der Teilnehmer** (gleicher
  `rfb.ClientFilter` mit `allow_input` = „Steuerung erlaubt“). Zwischenablage nie, nur der Agent-PC sichtbar.
  Beim Kursleiter Ansicht im Browser (noVNC) bzw. aus Bony's Agents heraus.
- Protokoll beim Teilnehmer: wann wer zugesehen/gesteuert hat (ohne Bildinhalte).
- Bausteine sind da: `websocket.FrameParser`/`Connection(client=True)`, `rfb.ClientFilter(allow_input=…)`,
  `present.pump_viewer` (Schleife Browser ↔ VNC) als Vorlage für die Brücke Kursleiter-Browser ↔ Tunnel.

### Stufe 4 – Kursleiter-Dashboard (nächster Schritt nach Stufe 3)

- Übersicht aller Teilnehmer-Agent-PCs (Status, Fortschritt), Einladung per Code.
- „Alle auf Anfang zurücksetzen“ (Agent-PC aus der Vorlage neu erstellen bzw. Snapshot zurückspielen –
  nur mit Zustimmung auf dem Teilnehmer-Rechner).
- Dateien (Übungsmaterial) an alle Agent-PCs verteilen.

## Sicherheitsregeln

- Nie Inhalte von Geheimnissen ausgeben: Die Frisch-Prüfung meldet nur **Art und Pfad** eines Fundes. Logs,
  Manifest, Tests und Repo enthalten keine echten Geheimnisse (Tests nur mit Dummy-Werten).
- Export nur von frischen Vorlagen; das Original (Vorlage) wird nie verändert – alles passiert in einer
  Überlagerung ohne Netz.
- Geprüft wird u. a.: `~/.hermes/.env` und weitere Token-Dateien (Claude, OpenClaw, GitHub-CLI, Git, npm,
  netrc, Docker), `/etc/wireguard`, VPN-Verbindungen im NetworkManager, SSH-Schlüssel (Benutzer und root),
  Browser-Profile (Brave, Chromium, Firefox: Verlauf, Cookies, Logins), Telegram-Sitzung, Schlüsselbund,
  Mission-Control-Geheimnisse und -Daten, Shell-Historien, cloud-init-Daten (enthalten das Passwort des
  Seeds), Passwort-Hashes in `/etc/shadow` (werden in der Kopie gesperrt).
- Nicht frei weitergebbare Programme verlassen den Rechner nie, sie werden beim Empfänger aus der offiziellen
  Quelle installiert.
- Import: Prüfsumme muss stimmen, Festplatte muss eigenständig und konsistent sein, tar-Einträge nur die
  erwarteten Namen (kein Pfad-Trick), Manifest-Werte werden geprüft (Name, Architektur, Apps nur bekannte IDs).
- Netzwerk (Stufe 2): nur lesend, nur mit Code, nur solange freigegeben, Zertifikat pro Freigabe, nichts
  dauerhaft an der Firewall öffnen.
- Vorführung (Stufe 3): VNC nie im Netz, nur lokal; Eingaben der Zuschauer verwirft der Proxy (nicht nur noVNC);
  Pause = keine Verbindung zum Bildschirm; Server nur, solange die Vorführung läuft.
- Vor jedem Befehl mit `sudo` nachfragen.

## Stand

- **2026-10-15 (Sitzung 1)**: Plan angelegt. **Stufe 1 und Stufe 2 umgesetzt** (Version 0.17.0).
  - Neu: `bonysfile.py` (Format, Frisch-Prüfung, Export/Import, Rezept), `share.py` (Freigabe/Beitreten),
    `mdns.py`, `gui/share_dialogs.py`; `AppSpec.redistributable/uninstall/version`; Vorlagen-Fenster mit
    „Weitergeben (.bonys) …“, „Im Netzwerk freigeben …“, Drag & Drop; Hauptfenster „Schulung beitreten“;
    `VMConfig.reinstall` (nicht mitgelieferte Apps, „Programme hinzufügen“ schlägt sie vor); Vorlagen
    fremder Architektur laufen auf Wunsch emuliert (TCG).
  - Verallgemeinern löscht jetzt auch `/root/.ssh` (cloud-init legt dort `authorized_keys` an – die strenge
    Prüfung hatte das beim ersten echten Export gefunden).
  - Tests: `tests/test_bonysfile.py`, `tests/test_share.py`, Dialoge in `tests/test_gui_layout.py`.
  - **Echter Test (bestanden)**: `vorlage-agent-pc-3` exportiert (3,6 GB, beide Frisch-Prüfungen sauber,
    Obsidian/Claude Code entfernt), importiert unter `_schulung-test/lib`, zwei Agent-PCs daraus (`kurs-pc`,
    `kurs-pc-2`): eigene Rechnernamen, Maschinen-IDs, SSH-Hostschlüssel und Mission-Control-Geheimnisse,
    root gesperrt, `/etc/wireguard` leer. Freigabe auf diesem Rechner: Beitritt aus `kurs-pc` (curl/openssl:
    Fingerabdruck, 403 bei falschem Code, 404/405, Abbruch + Fortsetzen, Prüfsumme) und mit `bonys-agents join`
    über das Heimnetz inkl. Import; mDNS-Suche findet die Freigabe (auch Avahi sieht sie). Ein zweiter
    physischer Rechner war nicht verfügbar.
  - Testdaten liegen in `/media/zappotex/bonysagent/BonysAgents/_schulung-test/` (Agent-PCs `kurs-pc`,
    `kurs-pc-2`, Vorlagen `kurs-import`, `kurs-join`) – können gelöscht werden.
- **2026-10-15**: Stufe 1 und 2 vom Nutzer getestet und abgenommen, veröffentlicht als Release v0.17.0.
- **2026-10-15 (Sitzung 2)**: **Stufe 3 A (Vorführen) umgesetzt**, Version 0.18.0 (veröffentlicht als v0.18.0,
  nach Test und OK des Nutzers – siehe unten).
  - Tests: `tests/test_present.py` (Filter mit echten RFB-Nachrichten, auch byteweise; WebSocket-Rahmen;
    VNC nur lokal; Server: Code/Ratenbegrenzung, fremde Origin, Pfad-Tricks, Eingaben kommen nie an,
    Bildrate, Pause, Entfernen, Höchstzahl, Ende bei Ausschalten/Zeitablauf, ECDSA-Zertifikat),
    `test_share.py` (Adressen ohne Docker-Brücken, VPN erkannt), Dialoge in `test_gui_layout.py`.
  - **Echter Test (lokal, ein Rechner)**: `agent-pc-3` mit neuem Code gestartet (Socket 0700), Vorführung per
    CLI und Dialog, Zuschauer: Chrome (headless, gesteuert per DevTools) über die LAN-Adresse. Bild live;
    Angriff mit rohen RFB-Nachrichten am noVNC-view_only vorbei (Rechtsklick, Strg+Alt+T, Tippen, Zwischenablage,
    QEMU-Taste, XVP-Reset) → nichts passiert, „34 Eingaben verworfen“; Gegenprobe direkt am Socket öffnet das
    Kontextmenü. Pause/Weiter (Seite verbindet neu), Entfernen. Last: 30 simulierte Zuschauer mit
    Vollbild-Anfragen → Proxy-Prozess < 10 % CPU, Bildrate automatisch 2,7/s je Zuschauer; Engpass ist dann das
    Kodieren in QEMU (ein VNC-Arbeits-Thread für alle Zuschauer) – Idee: bei sehr vielen Zuschauern ein
    gemeinsamer Bild-Strom (würde Neu-Kodieren im Proxy brauchen).
  - Noch offen für den Nutzer: zweites Gerät (Handy/Laptop) im WLAN, echte Browser-Zertifikatswarnung
    (Safari/iOS: WebSocket zu selbstsignierten Zertifikaten), Windows/macOS.
- **2026-10-15 (Sitzung 2, Fortsetzung)**: **Stufe 3 B (Hilfe-Modus) umgesetzt** (ebenfalls 0.18.0).
  - Neu: `helpmode.py` (HelpDesk im Kurs-Server, HelpClient beim Teilnehmer, Protokoll
    `schulung/hilfe-protokoll.log`), `websocket.Mailbox/serve` (Brücke Kursleiter-Browser ↔ Tunnel ohne
    gleichzeitigen TLS-Zugriff), `Presentation` ohne Bildschirm = Hilfe-Schalter (ein Code für beides,
    `set_screen/clear_screen`, `keep_running`), Seite `/help/<Sitzung>#t=Schlüssel` (`help.html|help.js`, nur von
    127.0.0.1; Sitzung im Pfad, weil ein offener Tab bei nur anderem `#…` nicht neu lädt; noVNC wird erst nach der
    Anmeldung geladen), `gui/course_ui.py` (CourseHub, HelpDeskDialog, HelpManager, HelpRequestDialog,
    HelpBanner, Zustimmungsdialoge), `VM.guest_notify` (notify-send im Gast über den Gast-Agent), Knopf
    „Hilfe anfordern …“, Menü „Kursleitung: Hilfe-Anfragen …“, Vorführen-Fenster nicht mehr modal.
  - Tests: `tests/test_helpmode.py` (falscher Code/Fingerabdruck, Ratenbegrenzung, ohne Zustimmung kein Bild und
    kein Tunnel, Steuerung erst nach zweiter Zustimmung, „nur ansehen“ sofort, Beenden trennt < 1,5 s, Protokoll
    ohne Bildinhalte, Kursleiter-Ansicht nur lokal, gemeinsamer Server), GUI-Layout. Gesamt: 409 bestanden.
  - **Echter Test (ein Rechner)**: Teilnehmer `agent-pc-3` verbindet sich über die LAN-Adresse, Anfrage erscheint,
    Zustimmung → Kursleiter-Ansicht in Chrome zeigt den Agent-PC; Rechtsklick des Kursleiters ohne Steuerung →
    nichts, nach zweiter Zustimmung → Kontextmenü öffnet sich, nach „Nur ansehen“ → wieder nichts; Beenden trennt
    die Ansicht. Gefunden und behoben: Deadlock beim Zurückstufen, noVNC-Laden ohne Schlüssel, Tab-Wiederverwendung.
  - Noch offen für den Nutzer: zweiter Rechner bzw. zweites Benutzerkonto, Zustimmungsdialoge in der echten App,
    Benachrichtigung im Agent-PC (notify-send im Gast nicht geprüft).
- **2026-10-15**: Nachtrag Windows (CI): Vorführen-Fenster war 914 px breit (fünf Knöpfe in der festen Knopfzeile) →
  „Hilfe-Anfragen …“ und „Zuschauer entfernen“ unter die Zuschauerliste; VNC-Pfadtest plattformfest. Nutzer hat
  getestet („Test war gut“) → **Release v0.18.0 veröffentlicht** (alle Release-Jobs grün, APT-Quelle liefert 0.18.0).
- **2026-10-15 (Sitzung 3)** – Auftrag in drei Teilen (A Stufe 3 prüfen, B zwei Editionen, C neues Hintergrundbild),
  Release erst nach Test und OK des Nutzers. Version wird 0.19.0.
  - **Teil A erledigt:** Stufe 3 war vollständig umgesetzt und getestet – nichts fehlte. Die geforderten Fälle stehen
    in `test_present.py` (Zuschauer-Eingaben verworfen, falscher Code abgelehnt/gesperrt) und `test_helpmode.py`
    (ohne Zustimmung kein Bild, ohne zweite Zustimmung keine Steuerung). 409 Tests grün.
  - **Teil B (Editionen) umgesetzt** (Details: `docs/editionen.md`): Kursleiter-Code in `src/bonys_agents/trainer/`
    (`share_server.py` = Server-Teil aus `share.py`, `present.py`, `helpdesk.py` = HelpDesk aus `helpmode.py`,
    `announce.py` = mDNS-Advertiser, `cli.py` = share/present, `gui/` = ShareDialog, PresentDialog,
    CourseHub/HelpDeskDialog, `resources/present`, `resources/novnc`). Hauptpaket: `edition.py` (EDITION, IS_TRAINER),
    `vncbridge.py` (pump_viewer), `share.py` (Protokoll `PROTOCOL=1`, `check_protocol`, Teilnehmer),
    `helpmode.py` (nur HelpClient). Pakete: `packaging/editions.py`, Spec mit `-- --edition`, `check-edition.py`,
    `build-deb.sh [anwender|kursleiter]`, `.iss` mit `/DEdition=` (gleiche AppId + InstallDelete), dmg mit
    Laufwerksname, release.yml/ci.yml/apt-repo für beide. Tests: `--edition anwender|kursleiter`, Marker
    `kursleiter`, `test_editions.py`, `test_share.py` (Teilnehmer) + `test_share_server.py` (Server).
  - Teil B committet (339bd24), Tests: Kursleiter 424, Anwender 373 grün; beide .deb lokal gebaut und geprüft.
  - **Teil C (Hintergrundbild) umgesetzt:** Bild 1536×1024 (3:2), PNG ohne Transparenz, 1,3 MB → JPEG 179 KB
    (`resources/wallpaper.jpg`, nicht hochgerechnet), Randfarbe `#010101` (`desktops.WALLPAPER_BORDER`). Altes Bild
    (SHA-256 cd4e20c6…, identisch in 0.3–0.18) nur noch als Prüfsumme in `wallpaper.OLD_SHA256`. Neues Modul
    `wallpaper.py` (Gast-Skript check/auto/force, Test-Präfix `BONYS_WP_ROOT`), `vm.guest_run(via_stdin=True)`
    (Skript > 128 KB), CLI `wallpaper NAME [--check|--force]`, Knopf in der Detailansicht, Klon-Erststart
    (`/usr/local/sbin/bonys-wallpaper-update`). Echt getestet: agent-pc-3 (Cinnamon) live umgestellt, Klon `wp-test`
    aus `vorlage-agent-pc-1` bekam das Bild beim ersten Start, Xfce darin (alter Zustand nachgestellt) live
    umgestellt, eigenes Xfce-Bild blieb. README zeigt keinen Agent-PC-Hintergrund – nichts zu tauschen.
    Test-Agent-PC `wp-test` kann gelöscht werden.
  - Teil C committet (7bf0b7e). **Gesamttest (Version 0.19.0, beide .deb gebaut):** Anwender-.deb installiert (Update
    von 0.18) → Agent-PC `gesamttest` aus Vorlage erstellt, neues Bild sichtbar → Kursleiter-.deb (ersetzt
    bonys-agents, Agent-PCs auch laufende da, `present` da, Startmenü „Bony's Agents Kursleiter“, Paketquelle bleibt)
    → Zusammenspiel: Kursleiter führt `gesamttest` vor, gebaute Anwender-Version erkennt die Vorführung, Browser-
    Zuschauer (curl) „live“, Hilfe-Anfrage aus Anwender-Code ohne trainer/ kommt beim Kursleiter an; Kursleiter gibt
    `vorlage-agent-pc-1` frei, Anwender-Version lädt und importiert sie als `kurs-gesamttest-019` → zurück auf
    Anwender (Kursleiter-Teile weg, alles andere da). Tests: Kursleiter 435, Anwender 383, ruff sauber.
  - Dabei gefunden und behoben: `join` auf eine Vorführung meldete „Fehler“ statt die Browser-Adresse; ein zweites
    Strg+C beim Beenden von share/present konnte „release unlocked lock“ auslösen (weitere Strg+C werden beim
    Aufräumen jetzt ignoriert).
  - Testdaten (können gelöscht werden): Agent-PCs `wp-test` (Xfce), `gesamttest`, Vorlage `kurs-gesamttest-019`.
    Installiert ist bonys-agents 0.19.0 (Anwender); bonys-agents-kursleiter steht noch als „config-files“ (harmlos,
    `sudo apt purge bonys-agents-kursleiter` räumt es weg).
  - **Wartet auf Test und OK des Nutzers**, danach Tag v0.19.0 (CI vorher abwarten).
- **Offen / Ideen**: Stufe 4 (Kursleiter-Dashboard) als nächster Schritt (gehört nach `trainer/`); Doppelklick auf `.bonys` öffnet Bony's Agents (MIME-Typ im
  .deb, Datei-Argument der App).
