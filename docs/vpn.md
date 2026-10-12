# Bony's VPN in Bony's Agents

[Bony's VPN](https://github.com/zappotex/bonys-vpn) ist seit Bony's Agents 0.15 ein **eigenes Projekt** mit eigenen
Paketen (`bonys-vpn`, im Agent-PC zusätzlich `bonys-vpn-agentpc`). Dort stehen das Sicherheitskonzept
(`docs/sicherheit.md`), die Oberfläche und die offizielle Schnittstelle (`docs/cli.md`). Hier steht nur, wie
Bony's Agents es nutzt. Bis 0.14 steckte eine eingebaute Fassung im Code von Bony's Agents (unter `/usr/local`
im Agent-PC, im .deb auf dem Host).

## Schnittstelle und Version

- Bony's Agents spricht nur über `bonys-vpn … --json` und den Root-Helfer `bonys-vpn-helper` (als root über
  den Gast-Agent) mit Bony's VPN – nie über dessen Python-Code.
- `vpnlink.SCHEMA = 1` und `vpnlink.MIN_VERSION = "1.0.0"`. Jede Statusabfrage prüft `schema` und `version`
  (`vpnlink.compat`): alte, eingebaute Fassung (`legacy`, ohne `schema`), zu altes Paket (`outdated`) oder
  neueres Schema (`newer`: Bony's Agents ist zu alt, Steuerung dann nur im Agent-PC). Bei `legacy`/`outdated`
  zeigt der Reiter „VPN“ den Knopf **„VPN-App aktualisieren“**.
- Eine .conf liest Bony's Agents nur, prüft sie grob (`vpnlink.inspect_conf`: Abschnitte, Schlüsselformat,
  Hook-Zeilen – Fehlermeldungen nennen nur Zeilennummern) und reicht sie direkt in den Agent-PC. Die
  vollständige Prüfung macht der Helfer. Auf dem Host bleibt nichts: kein Feld in `vm.json`, keine Zeile in
  Protokollen oder Fortschrittstexten, nichts in Vorlagen-Metadaten. `VpnSetup` zeigt die Daten auch in `repr`
  nicht. Konfigurationen mit Hook-Zeilen lehnt Bony's Agents ab – sie lassen sich nur im Agent-PC über
  Bony's VPN mit dessen Warnung importieren.

## Installation im Agent-PC

App-Option **„WireGuard VPN (Bony's VPN)“** (`apps.VPN`, id `vpn`), beim Erstellen oder über „Programme
hinzufügen“ (`bonys-agents install NAME vpn`):

1. `SHA256SUMS` und `SHA256SUMS.minisig` aus dem neuesten offiziellen Release laden
   (`https://github.com/zappotex/bonys-vpn/releases/latest/download/…`, nur HTTPS).
2. Signatur mit `minisign` aus Debian prüfen – derselbe öffentliche Schlüssel wie für die Updates von
   Bony's Agents (`UPDATE_PUBLIC_KEY`). Der signierte Kommentar muss genau diese Version nennen
   („Bony's VPN v1.0.1“), sonst Abbruch. Version mindestens `MIN_VERSION`.
3. `bonys-vpn_<v>_all.deb` und `bonys-vpn-agentpc_<v>_all.deb` laden (`all` = amd64 und arm64; gäbe es Pakete je
   Architektur, nimmt das Skript das passende) und mit `sha256sum -c` gegen die signierte Liste prüfen.
4. `apt-get install` der beiden Dateien – apt zieht `wireguard-tools`, `nftables`, GTK usw. aus Debian.
   Das Paket trägt die APT-Paketquelle (Suite `bonys-vpn`) ein, Updates kommen danach mit „Agent-PC aktualisieren“.
5. Benutzer in die Gruppe `bonys-vpn` (polkit: Bony's VPN ohne Passwort), Verknüpfung `bonys-vpn.desktop`
   auf dem Schreibtisch.

Ist der Kill-Switch an und kein Tunnel verbunden, bricht der Schritt sofort mit Hinweis ab.

## Umstellung alter Agent-PCs (eingebaute Fassung bis 0.14)

- **Automatisch:** Läuft ein Agent-PC mit der App `vpn`, prüft das Hauptfenster einmal je Start im Hintergrund
  über den Gast-Agent (ohne Passwort) den Status. Ist es die alte Fassung oder ein zu altes Paket, läuft derselbe
  Installationsschritt (`vpnlink.update_app`), Meldung in der Statusleiste.
- **Von Hand:** Reiter „VPN“ → „VPN-App aktualisieren“, Kommandozeile `bonys-agents vpn NAME update`.
- Was dabei passiert: Das Paket `bonys-vpn` entfernt die alte Installation unter `/usr/local` (Helfer, CLI,
  Oberfläche, Desktop-Eintrag, Tray-Autostart); eine eingeschaltete Kill-Switch-Unit wird auf die Unit aus dem
  Paket umgestellt. `bonys-vpn-agentpc` macht aus der alten polkit-Regel „Benutzer agent ohne Passwort“ die
  Gruppenmitgliedschaft. Bony's Agents ersetzt die Schreibtisch-Verknüpfung und startet das Tray-Symbol in der
  laufenden Sitzung neu (mit der Umgebung des alten Prozesses). **`/etc/wireguard` (Tunnel und Schlüssel),
  `killswitch.json` und der geladene Kill-Switch bleiben unverändert** – auch während der Umstellung gibt es
  kein ungeschütztes Internet.

## Beim Erstellen

- Dialog „Neuer Agent-PC“, Abschnitt **VPN**: Haken „WireGuard VPN (Bony's VPN)“, optional
  „Konfiguration wählen …“, dann „Automatisch verbinden“ und „Kill-Switch“.
  Kommandozeile: `bonys-agents create NAME --vpn-config DATEI [--vpn-name TUNNEL] [--vpn-autoconnect] [--killswitch]`.
  Mit einer Konfiguration kommt die App „vpn“ automatisch dazu.
- Die Datei kommt als eigene Datei `bonys-vpn.conf` ins Seed-ISO (nicht in user-data, das cloud-init
  im Gast unter `/var/lib/cloud` aufhebt). Das Seed-ISO hat die Rechte `600`.
- Ganz am Ende der Einrichtung, nach allen Downloads, hängt der Gast das ISO nur lesend ein und gibt
  die Datei über die Standardeingabe an `bonys-vpn-helper import NAME`. Danach Autostart und
  Kill-Switch, falls gewählt. Der Kill-Switch kommt zuletzt, damit er keinen Einrichtungsschritt
  vom Internet trennt. Ausgaben des Helfers gehen nach `/dev/null`. Ein Merker
  (`/var/lib/bonys-agents/vpn-config.done`) verhindert einen zweiten Import nach einem Abbruch.
- Sobald die Einrichtung fertig ist, löscht Bony's Agents das Seed-ISO (wie bisher wegen des Passworts).
  Danach liegt die Konfiguration nur noch in `/etc/wireguard` im Agent-PC.
- Aus einer Vorlage geht das genauso (Erststart-Skript des Klons), wenn die Vorlage Bony's VPN enthält.

## Im laufenden Agent-PC

- Detailansicht, Reiter **VPN**: Status (verbunden/getrennt, Tunnel, Adresse, Server, Handshake, Daten),
  „Verbinden“, „Trennen“, „Öffentliche IP prüfen“ (als Benutzer des Agent-PCs über api.ipify.org),
  „Konfiguration importieren …“, Schalter für Autostart und Kill-Switch, bei Bedarf „VPN-App aktualisieren“.
  Ohne Bony's VPN steht dort „VPN-App installieren“ (öffnet „Programme hinzufügen“ mit der VPN-App).
- Weg: Gast-Agent (`guest-exec` als root: `bonys-vpn status --json`, `bonys-vpn up|down|killswitch|autostart`,
  Import über `input-data`, also über die Standardeingabe von `bonys-vpn-helper import NAME`). Antwortet der
  Gast-Agent nicht, per SSH mit `sudo` und dem Passwort des Agent-PCs. Fehlermeldungen laufen auf dem Host noch
  einmal durch einen Schlüsselfilter.
- Kommandozeile: `bonys-agents vpn NAME status [--json] | up [TUNNEL] | down [TUNNEL] | import DATEI
  [--tunnel NAME] [--replace] | killswitch on|off | autostart on|off [--tunnel NAME] | ip | update`.

## Vorlagen

- **Frisch** („Persönliche Daten entfernen“): Autostart aller `wg-quick@`-Dienste aus, alles in
  `/etc/wireguard` gelöscht, Kill-Switch aus (Unit, Tabelle, Regeldatei), in `killswitch.json`
  `enabled: false` und keine aufgelösten Server-Adressen mehr. Die Ausnahmen bleiben.
- **Klon** („Persönliche Daten behalten“): alles bleibt. Dialog und Kommandozeile warnen: Zwei
  Agent-PCs mit demselben Schlüssel werfen sich gegenseitig aus dem Tunnel.
- Freier Platz wird beim Verallgemeinern **immer** mit Nullen überschrieben. `fstrim` allein reicht
  nicht: Es gibt nur ganze 64-KiB-Cluster der qcow2-Datei frei, ein freier 4-KiB-Block in einem sonst
  belegten Cluster behielte seinen Inhalt. Im echten Test stand der Wegwerf-Schlüssel einer
  gelöschten .conf so noch in der Vorlage. Die Arbeitskopie läuft deshalb mit `detect-zeroes=unmap`,
  die Nullen kosten dort keinen Platz.

## Verträglichkeit mit dem Kill-Switch

Geprüft im echten Test (Kill-Switch an, Tunnel getrennt): Gast-Agent, QMP, SSH-Weiterleitung,
Herunterfahren (2,3 s), Fortschrittsanzeige (serielle Konsole), RDP (xrdp über die Weiterleitung),
dynamische Auflösung (spice-vdagent über virtio-serial). „Agent-PC aktualisieren“ geht über den
Tunnel. Ohne Tunnel meldet es: „Kill-Switch an und kein Tunnel verbunden – erst verbinden“ (vorher
hätte apt die Netzfehler als Erfolg gemeldet).

## Eigener Rechner (Host)

### Linux

Der Knopf **„VPN“** oben im Fenster (und ⓘ → Extras → „Bony's VPN für diesen Rechner“) öffnet Bony's VPN, wenn
es installiert ist (`/usr/bin/bonys-vpn-gui`). Sonst erklärt ein Dialog, was passiert, und **„Installieren“**
holt das Paket `bonys-vpn` aus der offiziellen Quelle: aus der APT-Paketquelle von Bony's Agents (wenn
eingerichtet), sonst das .deb aus dem GitHub-Release mit geprüfter minisign-Signatur und SHA-256
(`hostvpn.install`), jeweils über `pkexec`. Das .deb von Bony's Agents enthält von Bony's VPN nichts mehr und
nennt `bonys-vpn` nur unter `Suggests`.

Update von 0.14: Ist `bonys-vpn` nicht installiert, schaltet `preinst` von bonys-agents vorher einen
eingeschalteten Kill-Switch ab – sonst bliebe der Rechner ohne Tunnel offline, ohne Programm zum Abschalten.
Tunnel in `/etc/wireguard` bleiben. Ist `bonys-vpn` installiert, übernimmt es die Dateien (`Replaces:
bonys-agents (<< 0.15)`).

### Kill-Switch auf dem Host und die Agent-PCs

Die Agent-PCs nutzen das QEMU-User-Netz: QEMU ist ein Prozess auf dem Host, ihr Internetverkehr ist also
Verkehr des Hosts und läuft durch `output`. Mit Kill-Switch und Tunnel geht er durch den Tunnel, ohne Tunnel
wird er abgewiesen. Alles, womit Bony's Agents die Agent-PCs steuert, braucht kein Internet und bleibt
erlaubt:

- QMP und Gast-Agent: Unix-Sockets bzw. virtio-serial, kein Netz
- SSH-, RDP- und SPICE-Weiterleitungen (`hostfwd`, 127.0.0.1): Loopback (`lo`) ist erlaubt
- Zugriffe aus dem Heimnetz auf eingeschalteten Fernzugriff: Antworten (`ct direction reply`) sind erlaubt
- DNS im Agent-PC (QEMU-DNS 10.0.2.3 → Resolver des Hosts über `lo` → systemd-resolved): geht, Daten nicht

Geprüft im echten Test (siehe `docs/plan-vpn-obsidian.md`, Sitzung 5). Ohne Tunnel dauert das
Herunterfahren eines Agent-PCs mit Hermes Agent und Telegram-Anbindung länger (gemessen 65 s statt 20 s):
Das Hermes-Gateway versucht beim Beenden weiter Telegram zu erreichen, bis sein eigener Watchdog nach 60 s
abbricht. Das bleibt unter den 90 s, nach denen Bony's Agents hart ausschaltet. Dasselbe passiert bei jedem
Agent-PC ohne Internet, auch mit dem Kill-Switch im Agent-PC.

### Windows und macOS

- **Windows:** „Extras → WireGuard für diesen Rechner installieren …“ → `winget install --id WireGuard.WireGuard
  -e --silent --accept-package-agreements --accept-source-agreements` (Windows fragt nach Administratorrechten).
  Ist `C:\Program Files\WireGuard\wireguard.exe` schon da, öffnet der Menüpunkt die App. Fehlt winget,
  verweist die Meldung auf https://www.wireguard.com/install/.
- **macOS:** Laut https://www.wireguard.com/install/ gibt es die App nur im App Store (ID 1451685025).
  Homebrew und MacPorts liefern nur `wireguard-tools` ohne App, `mas` ist kein offizielles Werkzeug und
  bräuchte die Apple-ID-Anmeldung. Bony's Agents öffnet deshalb `macappstore://apps.apple.com/app/id1451685025`
  (ersatzweise die Webseite) und erklärt die Schritte. Ist `/Applications/WireGuard.app` da, wird sie geöffnet.
- In beiden Fällen verwaltet die offizielle App die Tunnel. Bony's Agents liest oder speichert keine
  Konfigurationen.
