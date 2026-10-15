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

### Stufe 3 – Live-Vorführung (Ausblick)

- Kursleiter zeigt seinen Agent-PC live: noVNC im Browser der Teilnehmer, **nur ansehen** (VNC view-only,
  eigener Code wie bei der Freigabe, nur im LAN/VPN, zeitlich begrenzt).
- **Hilfe-Modus**: Der Kursleiter darf den Agent-PC eines Teilnehmers ansehen bzw. steuern – nur nach
  ausdrücklicher Zustimmung des Teilnehmers für genau diese Sitzung, jederzeit beendbar, gut sichtbar
  angezeigt.

### Stufe 4 – Kursleiter-Dashboard (Ausblick)

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
- **Offen / Ideen**: Doppelklick auf `.bonys` öffnet Bony's Agents (MIME-Typ im .deb, Datei-Argument der
  App); Stufe 3 und 4.
