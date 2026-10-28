# Bony-Netz in Bony's Agents

Stand: Aufgaben 01 (Baustein und Einstellungen), 02 (Agenten-PCs ins Netz), 04 (Kurse verwalten), 05 (Kursraum) und
06 (Hilfe-Funktion) aus `bony-netz-paket`. Aufgabe 03 steht in Bony's VPN.

| Was | Wo |
|---|---|
| Gemeinsamer Baustein (wie in Bony's VPN, **nicht hier ändern**) | `src/bony_netz/` (Version in `__init__.py`) |
| Tests des Bausteins (unverändert übernommen) | `tests/test_bony_netz_baustein.py` |
| Logik für Bony's Agents (Zustand, Server wechseln, Instanz anlegen/löschen) | `src/bonys_agents/netz.py` |
| Fenster „Bony-Netz“ (Menü → „Bony-Netz …“) | `src/bonys_agents/gui/netz_dialog.py` |
| Agenten-PCs ins Netz: Schlüssel, Beitritt im Gast, Geräteliste, Entfernen | `src/bonys_agents/netz.py` (unterer Teil) |
| Einrichtungsschritt bzw. Klon-Erststart, Seed-Datei, Vorlagen ohne Tailscale-Identität | `src/bonys_agents/cloudinit.py` |
| Häkchen beim Erstellen | `gui/create_dialog.py`; Netz-Symbol, Kontextmenü, Löschen: `gui/main_window.py` |
| Kurse (Aufgabe 04): Logik ohne Qt | `src/bonys_agents/kurse.py` |
| Fenster „Kurse“ (Knopf im Kopf), Reiter „Teilnahme“ | `src/bonys_agents/gui/kurse_dialog.py` |
| Reiter „Kursleitung“, „Neuer Kurs“, Kursansicht (nur Kursleiter-Version) | `src/bonys_agents/trainer/gui/kurse_leiten.py` |
| „Der Kurs X hat begonnen“ | `gui/main_window.py` (`_check_kurse`) |
| Tests gegen eine Test-Zentrale auf 127.0.0.1 (mit Kurs-Endpunkten) | `tests/test_netz.py`, `tests/test_kurse.py` |
| Kurspaket im Kurs (Baustein 0.2.0, Zentrale 0.2.0): hochladen, holen, Fortschritt melden | `src/bonys_agents/kurse.py` (`kurspaket_hochladen`, `kurspaket_fuer_kurs`, `fortschritt_melden`), Fenster wie oben, `gui/kurspaket_anleitung.py` |
| Hilfe-Funktion (Aufgabe 06): Logik ohne Qt, x11vnc im Agent-PC | `src/bonys_agents/hilfe.py`, `vncauth.py` |
| Hilfe beim Teilnehmer: Rückfrage, Hinweis mit „Beenden“ | `src/bonys_agents/gui/hilfe_ui.py` |
| Hilfe beim Kursleiter: Betrachter (noVNC/TigerVNC), Brücke | `trainer/gui/hilfe_fenster.py`, `trainer/hilfe_betrachter.py`, `trainer/resources/hilfe/` |

Baustein ersetzen: `src/bony_netz/` und `tests/test_bony_netz_baustein.py` durch die neue Fassung aus dem Paket
überschreiben, in Bony's VPN ebenso. Ruff-Ausnahmen für den Baustein stehen in `pyproject.toml`
(`per-file-ignores`), damit er unverändert bleiben kann. Ausgeliefert wird er im Wheel (`pyproject.toml`) und
in allen PyInstaller-Programmen (.deb, Windows, macOS); `packaging/check-edition.py` prüft, dass er drin ist.

Alle Tests setzen `BONY_NETZ_ORDNER` auf einen Testordner (`tests/conftest.py`) – die echte Anmeldung wird nie
angefasst.

## Baustein 0.1.1

Fehler in 0.1.0 (gefunden beim ersten echten Klon mit Bony-Netz, 17.10.2026): Das Beitrittsskript las `/etc/os-release`
direkt ein, dessen `NAME="Debian GNU/Linux"` überschrieb den Gerätenamen – `tailscale up` scheiterte, sobald Tailscale
erst installiert werden musste. In 0.1.1 korrigiert, in beiden Projekten und im Paket (`bony-netz-paket.tar.gz`, die
alte Fassung liegt daneben als `bony-netz-paket-0.1.0.tar.gz`). Betroffene Agent-PCs: Rechtsklick → „Mit dem
Bony-Netz verbinden“ (Tailscale ist dann schon da).

## Notizen zum Baustein (0.1.0) – nicht hier angepasst

- `Zentrale._anfrage()` wirft bei einer Antwort, die kein JSON ist (z. B. eine Webseite mit Status 200),
  einen rohen `json.JSONDecodeError` statt `ZentraleFehler`/`NetzFehler`. Ebenso ein `KeyError`, wenn
  `instanz_registrieren()` kein `token` bekommt. `bonys_agents.netz` fängt das ab und meldet „Unter … antwortet
  kein Bony-Netz-Server“. Besser wäre es im Baustein selbst (für Bony's VPN genauso).
- `info()` prüft nicht, ob wirklich eine Zentrale antwortet (Felder `server_name`, `login_server`) – macht hier
  `netz.server_info()`.
- `test_baustein.py` und die Module haben keine SPDX-Lizenzzeile; ruff meldet E501 (Zeile im Skript) und UP037.

## Aufgabe 02: Agenten-PCs ins Netz – wie es läuft

- Agenten-PCs werden über cloud-init (Seed-ISO, NoCloud) eingerichtet. Neu installiert: Einrichtungsskript mit
  Schritten als Dienst `bonys-provision.service` (darüber kommen auch Brave, Telegram, Hermes). Aus einer Vorlage:
  `bonys-clone-firstboot` über `runcmd`. Der Beitritt nutzt genau diese Wege:
  - neu installiert: **Schritt 2** „Mit dem Bony-Netz verbinden“, gleich nach Sprache/Tastatur (so früh, weil der
    Schlüssel nur 60 Minuten gilt; ein Fehlschlag erscheint wie andere Schritte als „fertig mit Fehlern“),
  - aus einer Vorlage: im Erststart-Skript, vor dem Import einer WireGuard-Konfiguration (Kill-Switch).
- `vm.create(..., bony_netz=True)` holt den Geräteschlüssel erst nach Download und Festplatte, direkt vor dem
  Seed-ISO. Das Beitrittsskript aus `bony_netz.erstbeitritt_skript` liegt nur im Seed-ISO (`bony-netz.sh`, wie
  `bonys-vpn.conf`); das Seed-ISO löscht die App nach der Einrichtung. Im Gast wird es nach
  `/root/bony-netz-beitritt.sh` (700) kopiert, nach fremden apt-Läufen einmal als root ausgeführt und danach
  gelöscht (auch bei einem Fehler). Erledigt: `/var/lib/bonys-agents/bony-netz.done`.
- Netzname (`geraetename(Name des Agent-PCs)`) steht in `vm.json` als `netz_name`; die `geraet_id` wird über den
  Namen in `zentrale.geraete()` gefunden.
- Nachträglich verbinden: über `VM.guest_run` (Gast-Agent, sonst SSH mit Passwort) – das Skript geht base64-kodiert
  über die Standardeingabe. Der Schlüssel wird erst geholt, wenn klar ist, dass der Befehl ankommt.
- Vorlagen: `generalize_script` löscht `/var/lib/tailscale` und die Erledigt-Markierung (nur lokal, kein
  `tailscale logout` – das nähme den Original-Agent-PC aus dem Netz).

### Offen / Hinweise

- Kill-Switch von Bony's VPN: Ist er an, geht ohne WireGuard-Tunnel auch Tailscale nicht ins Internet (der Beitritt
  selbst läuft vorher).
- Wird ein Agent-PC gelöscht, während der Server nicht erreichbar ist, bleibt das Gerät auf dem Server. Ein neuer
  Agent-PC mit demselben Namen bekommt von Headscale dann womöglich einen abgewandelten Namen und erscheint als
  „nicht verbunden“. Eine Geräteliste zum Aufräumen gibt es noch nicht.

## Aufgabe 04: Kurse – wie es mit der Schulung im eigenen Netz zusammenpasst

Die vorhandene Schulung (Vorlage freigeben, „Schulung beitreten“, Vorführen, Hilfe-Schalter) läuft ohne Server direkt
zwischen den Rechnern im selben Netz (LAN oder VPN) mit eigenem Code und Fingerabdruck. Sie bleibt **unverändert**.
Die Kurse über das Bony-Netz kommen daneben:

- Ein Knopf **„Kurse“** (früher „Kurs beitreten“) öffnet das Fenster „Kurse“. Darin „Kursleitung“ (nur
  Kursleiter-Version, Modul in `trainer/` – fehlt in der Anwender-Version ganz) und „Teilnahme“. Der bisherige Weg
  steht unten als „Schulung im Netzwerk beitreten …“ (öffnet `JoinDialog` wie früher).
- Ohne Bony-Netz (aus oder keine Instanz) zeigt das Fenster einen Hinweis mit „Bony-Netz …“ und fragt die Zentrale
  nicht; die Schulung im eigenen Netz geht trotzdem.
- Später (Aufgaben 05/06) sollen Kursraum und Hilfe für Bony-Netz-Kurse dieselben Fenster nutzen: Kursansicht →
  „Kursraum öffnen“, Teilnehmerliste → „Helfen“. Der Hilfe-Schalter im eigenen Netz bleibt für Kurse ohne Internet.

Umsetzung:
- `kurse._aufruf` deutet einen 404 der Zentrale **nicht** als „kein Bony-Netz-Server“ (anders als `netz._fragen`):
  „Code abgelaufen“ kommt als 404 mit Meldung für den Nutzer. Antworten ohne JSON ergeben weiter `KeinBonyNetz`,
  ein 401 meldet die Instanz ab (wie überall).
- Gemerkt in `konto.extra`: `kursleiter_name` (Kursleiter) und `anzeigename` (Teilnehmer). `ist_kursleiter` wird
  nach `instanz()` bzw. dem Einlösen in `konto.json` nachgetragen (sieht auch Bony's VPN).
- Agent-PC-Auswahl: `zentrale.geraete()`, online zuerst. **Ohne** den Rechner selbst, wenn Bony's VPN ihn verbunden
  hat (`konto.extra["vpn_rechner"]`, gleiche Instanz) – sonst könnte ein Teilnehmer dem Kursleiter versehentlich
  den eigenen Rechner öffnen. Neben dem Netznamen steht der Name des Agent-PCs auf diesem Rechner.
- Abfragen: Kursliste und Kursansicht alle 15 s, solange sichtbar; „Teilnahme“ und die Meldung im Hauptfenster
  höchstens jede Minute. Das Hauptfenster fragt beim Start einmal und danach nur weiter, solange es Teilnahmen gibt
  (nach dem Fenster „Kurse“ wieder einmal).
- „Kursraum öffnen/betreten“: seit Aufgabe 05 das Fenster „Kursraum“ (unten).

### Offen / Hinweise
- Echt zu prüfen (Fertig-wenn): Kurs anlegen, zweiter Rechner mit anderer Instanz tritt bei; nach „Kurs starten“
  `ping` vom Kursleiter (Rechner über Bony's VPN oder Agent-PC) auf genau diesen Agent-PC, nicht auf andere des
  Teilnehmers; nach „Pausieren“/„Beenden“ sofort weg; Teilnehmer untereinander nie. Das regelt die Zentrale
  (Headscale-Regeln) – die App zeigt nur an.
- Was die Zentrale bei einem erneuten Beitritt nach „Entfernen“ tut, steht nicht in API.md; die App zeigt dann
  einfach die Meldung der Zentrale.

## Aufgabe 05: Kursraum

- Logik ohne Qt: `bonys_agents/kursraum.py` (Eintrittskarte, LiveKit-Twirp `MutePublishedTrack`/`RemoveParticipant`
  mit der Kursleiter-Karte, Regeln für Seite und Berechtigungen). Fenster: `gui/kursraum_fenster.py`. Seite:
  `resources/kursraum/` (`index.html`, `kursraum.js`, `kursraum.css`), dazu `vendor/livekit-client.umd.js` – nicht im
  Repository, `packaging/fetch-livekit.py` holt Version 2.22.3 mit fester SHA-256 (wie noVNC).
- Die Seite kommt über das eigene Schema `kursraum://app/…` (sicher, nicht „lokal“, damit sie wss/https zum
  LiveKit-Server darf). `vorbereiten()` meldet es vor der QApplication an (`gui/app.py`). Die Karte geht nur per
  QWebChannel an die Seite; LiveKit schreibt das Token auch in seinen eigenen Meldungen nur als `<redacted>`.
- Berechtigungen: Qt 6.8+ `permissionRequested`, davor `featurePermissionRequested`; erlaubt nur Kamera, Mikrofon
  und Bildschirm für `kursraum://app`. **Bildschirm teilen braucht `QWebEngineSettings.ScreenCaptureEnabled`** –
  ohne kommt sofort „AbortError: Invalid state“, ohne dass Qt überhaupt fragt. Nur beim Kursleiter an.
  `desktopMediaRequested` (Qt 6.7+) öffnet eine Auswahl Bildschirm/Fenster.
- Geprüft (17.10.2026, Linux/X11, Qt 6.12 und 6.8.3): getDisplayMedia, Mikrofon, Ende-zu-Ende mit
  `livekit-server --dev` (zwei Fenster: Chat, Hand, Stummschalten per Twirp, Freigabe, Bildschirm auf der Bühne,
  Entfernen, Raum gelöscht, abgelaufene Karte, sauberes Verlassen – 23/23), dazu das gebaute PyInstaller-Paket in
  einem eigenen X-Server (Xephyr) und `wss://` gegen den echten Kursraum-Server (falsche Karte → richtige Meldung).
- **Wayland:** Die offiziellen Qt-Wheels sind ohne PipeWire gebaut → keine Bildschirmaufnahme. Der Knopf erklärt
  das (`kursraum.WAYLAND_HINWEIS`); Kamera, Ton und Chat gehen. Windows und macOS sind hier nicht getestet.
- Fenster: eigenständig (ohne Elternfenster), „Kurse“ und Kursansicht sind nur noch fenstermodal – sonst wäre der
  Kursraum gesperrt, solange sie offen sind. Ein Fenster je Kurs; Schließen wartet auf `room.disconnect()` (höchstens
  3 s). Offene Kursräume gehen mit dem Hauptfenster zu.
- „Sprechen nur nach Freigabe“: Datennachricht `freigabe` `{pflicht, erlaubt: [identity]}` vom Kursleiter (nur von
  Teilnehmern mit `{"rolle": "kursleiter"}` angenommen), an neue Teilnehmer gleich beim Eintreten. Handzeichen
  bekommen Nachzügler ebenso.

### Paket
- Abhängigkeit `PySide6-WebEngine` (ab 6.12 eigenes Wheel, zieht `PySide6-Addons` nach). Etwa +290 MB im
  Programmordner. **Linux arm64 ohne Kursraum** (Entscheidung 17.10.2026): Dort bleibt es bei Qt 6.8.0.2, und dessen
  WebEngine (PySide6-Addons, aarch64) braucht `libwebp.so.6`, `libevent`, `libminizip`, `libopus` aus dem System –
  `libwebp.so.6` gibt es auf Ubuntu 22.04/Debian 12 nicht (Release-Lauf scheiterte daran). „Kursraum betreten“ zeigt
  dort `kursraum.KEIN_WEBENGINE_ARM`, der Selbsttest wertet das als OK. Mit Qt 6.12 für arm64 ginge es, das .deb
  bräuchte dann aber glibc 2.39 (kein Debian 12/Raspberry Pi OS bookworm mehr).
- Bauplan: `QtNetwork`, `QtWebEngineCore` und **`QtPrintSupport`** dürfen nicht ausgeschlossen sein (die
  Python-Bindung von QtWebEngineCore braucht QtPrintSupport – sonst „could not import module
  PySide6.QtWebEngineCore“). Das Druck-Plugin (CUPS, Avahi, GnuTLS) bleibt draußen. NSS, ALSA, GBM, DRM, xkbfile,
  Xtst kommen vom System (Depends im .deb); NSS lädt zur Laufzeit eigene Module des Systems.
- .deb: `QtWebEngineProcess` braucht ausdrücklich `chmod 755`. AppArmor-Profil `packaging/linux/apparmor-bonys-agents`
  (für `/opt/bonys-agents/BonysAgents` – Chromiums Hauptprozess legt die Namensräume an, per strace geprüft), nur mit
  AppArmor 4 nach `/etc/apparmor.d/`. Ohne Profil unter Ubuntu 24.04+ (Quelltext) schaltet die App die Sandbox ab
  (`kursraum.sandbox_abschalten`).
- macOS: `NSCameraUsageDescription`/`NSMicrophoneUsageDescription` in Info.plist, Entitlements `device.camera`,
  `device.audio-input`; `sign.sh` signiert `QtWebEngineProcess.app` vor dem Framework.
- Lizenzen: THIRD-PARTY-LICENSES (livekit-client und die darin gebündelten Bibliotheken, Qt WebEngine/Chromium);
  `collect-licenses.py` legt `QtWebEngine-Chromium.txt` an (Chromium-Lizenz der eingebauten Fassung, Verweis auf
  die vollständige Liste der Chromium-Drittkomponenten bei Qt).
- Selbsttest: `bonys-agents selftest` prüft „Kursraum (Qt WebEngine, livekit-client)“ – fällt im CI auf allen
  Systemen auf, wenn etwas fehlt.

### Offen / Hinweise
- Echt zu prüfen (Fertig-wenn): Kursleiter und zwei Teilnehmer auf drei Rechnern, eines per Handy-Hotspot; Bild/Ton
  hin und her; Bildschirm teilen beim Kursleiter; Chat/Hand; Stummschalten/Entfernen; Kurs beenden → alle fliegen
  raus, erneuter Eintritt abgelehnt. Windows und macOS (Bildschirmaufnahme-Freigabe!) sowie Ubuntu 24.04 (AppArmor)
  bisher nur nach Quelltext/Doku, nicht ausprobiert.
- Ob die Zentrale beim **Pausieren** den LiveKit-Raum schließt, steht nicht in API.md. Falls nicht, bleiben
  Verbundene bis zum Beenden im Raum; neue Eintritte lehnt die Zentrale (409) ab.

## Aufgabe 06: Hilfe-Funktion

Entscheidungen (18.10.2026): Betrachter **„Beides“** – noVNC eingebettet als Standard, TigerVNC als Rückfall; dieser
Rechner kommt **über Bony's VPN** ins Netz (Agents prüft nur und bietet Bony's VPN an).

- Nachrichten im Kursraum (zuverlässig, JSON, immer mit `destinationIdentities`): `hilfe-anfrage {id}` nur vom
  Kursleiter (ab Zentrale 0.2.1 an seiner Identität `kursleiter_identitaet` von der Zentrale erkannt – Metadaten kann ein
  Teilnehmer nicht mehr ändern; die Anfrage nennt mit `von` die Adresse des Kursleiter-Rechners, nur von dort nimmt
  x11vnc an), `hilfe-zusage {id, ip, port, modus, passwort, pc}` und
  `hilfe-absage {id, grund?}` nur an ihn und nur als Antwort auf seine offene Anfrage, `hilfe-ende` von der Seite,
  die beendet, `hilfe-bitte {an}` = „Hilfe anfordern“ (nur ein 🆘 in der Liste des Kursleiters). Entschieden wird
  in Python, nie auf der Seite: Beim Teilnehmer `gui/hilfe_ui.TeilnehmerHilfe`, beim Kursleiter
  `trainer/gui/hilfe_fenster.KursleiterHilfe`.
- Teilnehmer: Den Agent-PC findet `hilfe.agent_pc` über `mein_geraet_id` der Teilnahme → Netzname → `vm.json`
  (`netz_name`). Rückfrage „Nur ansehen“ / „Ansehen und bedienen“ / „Ablehnen“, nach 60 s „Ablehnen“, Enter und Esc
  lehnen ab. Eine Hilfe zur Zeit.
- x11vnc (`hilfe.start_skript`, über den Gast-Agent wie `netz.nachtraeglich_verbinden`, Skript per stdin): als
  systemd-Einheit `bonys-hilfe` mit `RuntimeMaxSec=1800`; `-listen <tailscale ip -4> -noipv6 -rfbport 5959 -once
  -timeout 120 -passwdfile rm:/run/bonys-hilfe/passwort -nevershared -nosel -noremote -nocmds -norc`, bei
  „Nur ansehen“ `-viewonly`. Das Einmal-Passwort (8 Zeichen, VNC kann nicht mehr) schreibt bashs eingebautes
  `printf` in die Datei, x11vnc löscht sie nach dem Lesen. Das Skript wartet, bis `ss` die 100.x-Adresse zeigt.
  Mit `von` aus der Anfrage zusätzlich `-allow <Kursleiter-Rechner>`. **Totmannschalter:** Einheit
  `bonys-hilfe-wache` stoppt x11vnc, wenn `/run/bonys-hilfe/lebt` älter als 30 s ist; die App des Teilnehmers
  erneuert die Datei bei jeder Statusprüfung (alle 3 s). Die Zentrale (ab 0.2.1) gibt dem Kursleiter nur Port 5959
  frei, nicht den ganzen Agent-PC.
  Neue Agent-PCs bringen x11vnc mit (`desktops.COMMON_PACKAGES`), alte installieren es beim ersten Mal aus Debian.
  Kein SSH-Rückfall: Antwortet der Gast-Agent nicht, sagt die App das.
- Ende beim Teilnehmer: „Beenden“ im Hinweis (über allen Fenstern, auch Schließen des Hinweises), `hilfe-ende` vom
  Kursleiter, Kursraum verlassen/getrennt, Kurs nicht mehr „läuft“ (alle 15 s gefragt), x11vnc von selbst zu Ende
  (alle 3 s `systemctl is-active`). Protokoll wie im LAN-Hilfe-Modus (`helpmode.log_file`).
- Kursleiter: Die Zusage wird gegen die Zentrale geprüft (`hilfe.zusage_pruefen`): nur 100.64.0.0/10, und genau die
  `geraet_ip` dieses Teilnehmers, sonst keine Verbindung. Betrachter eingebettet: `HilfeFenster` lädt
  `kursraum://app/hilfe/index.html` (Seiten und noVNC über `kursraum_fenster.ZUSATZ` unter demselben Schema),
  noVNC verbindet sich mit `hilfe_betrachter.Bruecke` – Port nur auf 127.0.0.1, geheimer Pfad, Origin
  `kursraum://app`, genau eine Verbindung, danach ist der Port zu. Das Passwort geht per QWebChannel an noVNC.
  Rückfall (kein Qt WebEngine, z. B. Linux arm64): TigerVNC `vncviewer -PasswordFile=<Datei 600>` (Format von
  `vncpasswd`, DES in `vncauth.py`), Datei nach 20 s bzw. beim Ende gelöscht; ohne TigerVNC ein Hinweis.
- Beim Kursstart prüft die Kursansicht (`hilfe.rechner_im_netz`: eigene Tailscale-Adresse in der Geräteliste der
  Instanz) und bietet sonst Bony's VPN an (Linux; Windows/macOS: Hinweis auf die Tailscale-App mit Anmeldeserver).
  „Helfen“ gibt es im Kursraum je Teilnehmer und in der Kursansicht (öffnet den Kursraum und fragt dann).

### Offen / Hinweise
- Echt zu prüfen (Fertig-wenn): ohne Zustimmung keine Verbindung (auch mit bekannter Adresse – x11vnc läuft dann
  nicht); „Nur ansehen“ ohne Eingaben; „Beenden“ trennt sofort; nach Pause/Ende keine neue Verbindung (Zentrale);
  im Agent-PC `ss -tlnp` zeigt nur `100.x.y.z:5959`.
- Kill-Switch von Bony's VPN im Agent-PC: ob er eingehende Verbindungen über `tailscale0` durchlässt, ist nicht
  geprüft (Hinweis auf die Ausnahme 100.64.0.0/10 aus Aufgabe 03).
- GDM (GNOME) mit automatischer Anmeldung: x11vnc nimmt `-display :0 -auth guess` – wie `guest_notify`. Falls GDM
  die Sitzung auf `:1` legt, wäre das anzupassen.
