# Bony's VPN – Sicherheitskonzept

Bony's VPN verwaltet WireGuard-Tunnel im Agent-PC und auf dem eigenen Linux-Rechner (Host).
Der Code liegt in `src/bonys_agents/vpn/`. Er braucht nur die Python-Standardbibliothek und die
Debian-Pakete `wireguard-tools`, `nftables`, `pkexec` und `polkitd`. Für das `DNS`-Feld einer
Konfiguration ruft wg-quick `resolvconf` auf. Den Befehl bringt systemd-resolved mit (so im Agent-PC),
sonst `openresolv`. Ist systemd-resolved aktiv, darf `openresolv` nicht zusätzlich installiert werden. Vom Rest von Bony's Agents hängt er nicht ab und wird deshalb
einzeln in den Agent-PC kopiert.

## Aufbau

| Teil | Läuft als | Aufgabe |
|---|---|---|
| `bonys-vpn` (`cli.py`), `bonys-vpn-gui` (`gui.py`, `model.py`) | Benutzer | Bedienung. Liest .conf-Dateien mit den Rechten des Benutzers |
| `bonys-vpn-helper` (`helper.py`) | root, über `pkexec` | Die wenigen Aktionen, für die root nötig ist |
| `conf.py` | – | Prüft .conf-Dateien und Tunnelnamen, verbirgt Schlüssel |
| `killswitch.py` | – | Baut das nftables-Regelwerk als Text |
| `install.py` | root | Legt die Dateien an ihren Platz (siehe unten) |

## Was der Helfer darf

Nur diese festen Unterbefehle, sonst nichts:

| Befehl | Wirkung |
|---|---|
| `list`, `status [NAME]`, `show NAME` | Tunnel auflisten, Status als JSON, Konfiguration mit verborgenen Schlüsseln |
| `up NAME`, `down [NAME]` | `wg-quick up/down`. `up` trennt vorher einen anderen aktiven Tunnel von Bony's VPN |
| `import NAME [--allow-hooks] [--replace]` | Konfiguration von der **Standardeingabe** prüfen und nach `/etc/wireguard/NAME.conf` schreiben |
| `delete NAME`, `rename ALT NEU`, `export NAME` | Nur für Tunnel, die Bony's VPN selbst angelegt hat |
| `autostart NAME on/off` | `systemctl enable/disable wg-quick@NAME`. Immer nur ein Tunnel |
| `killswitch on [--exception NETZ …] / off / status` | Kill-Switch (siehe unten) |

Eingaben werden so geprüft:

- **Tunnelnamen**: nur `[a-zA-Z0-9_=+.-]{1,15}`, nicht `.` oder `..` und kein `-` am Anfang, damit
  kein Name als Option von `wg-quick` oder `systemctl` gelesen wird. Damit sind Pfade (`../`),
  Shell-Zeichen (`;`, `$()`, Backticks) und Leerzeichen ausgeschlossen. Für den Autostart ist
  zusätzlich kein `+` oder `=` erlaubt, weil systemd diese Zeichen in Unit-Namen nicht zulässt.
- **Keine Pfade**: Der Helfer bekommt nie einen Dateipfad. Die Kommandozeile liest die .conf als
  Benutzer und gibt den Inhalt über die Standardeingabe weiter. So kann niemand den Helfer dazu
  bringen, als root fremde Dateien (etwa `/etc/shadow`) zu lesen. Geschrieben wird nur in
  `/etc/wireguard` und `/etc/bonys-vpn`. Symbolische Links werden dort weder gelesen noch beschrieben.
- **Keine Shell**: `subprocess` läuft nur mit Argumentlisten, festem `PATH`
  (`/usr/sbin:/usr/bin:/sbin:/bin`) und leerer Umgebung. Der Helfer startet mit `python3 -I`, das
  `PYTHONPATH`, `PYTHONHOME` und das Benutzer-`site-packages` ignoriert.
- **Eigene Tunnel**: Was Bony's VPN anlegt, bekommt als erste Zeile `# Verwaltet von Bony's VPN`.
  Löschen, Umbenennen und Exportieren gehen nur bei solchen Tunneln. Andere WireGuard-Konfigurationen
  auf dem Host werden angezeigt und lassen sich verbinden, aber nicht verändern.
- **Sperre**: Jede ändernde Aktion hält eine Dateisperre (`/etc/bonys-vpn/.lock`), damit zwei Aufrufe
  sich nicht in die Quere kommen.

## Prüfung der .conf

- Höchstens 64 KiB, UTF-8, keine Steuerzeichen. Eine BOM und Windows-Zeilenenden werden entfernt.
- Nur die Abschnitte `[Interface]` (genau einmal) und `[Peer]` (mindestens einmal), nur bekannte Felder.
  Doppelte Felder sind nur erlaubt, wo wg-quick sie aneinanderhängt (`Address`, `DNS`, `AllowedIPs`, Hooks).
- Pflichtfelder: `PrivateKey`, `Address`, je Peer `PublicKey` und `AllowedIPs`.
- Schlüssel: 44 Zeichen Base64, ergeben genau 32 Byte.
- `Address`, `AllowedIPs`, `DNS` und `Endpoint` (`host:port` oder `[IPv6]:port`, Port 1–65535)
  werden einzeln geprüft. `SaveConfig = true` wird abgelehnt, weil wg-quick die Datei sonst beim
  Trennen überschreibt.
- **Fehlermeldungen nennen nur Zeile und Feldname, nie den Wert.**

## Warum Hook-Zeilen blockiert sind

`PreUp`, `PostUp`, `PreDown` und `PostDown` sind Shell-Befehle, die wg-quick **als root** ausführt.
Eine fremde .conf, etwa von einem VPN-Anbieter oder aus dem Netz, könnte damit beliebigen Code als
root starten. Der Helfer lehnt solche Konfigurationen deshalb ab. Nur mit dem ausdrücklichen Schalter
`--allow-hooks` werden sie übernommen. Die Oberfläche setzt ihn erst nach einer deutlichen Warnung,
die Kommandozeile heißt dafür `--hooks-erlauben` und zeigt die Warnung ebenfalls. `status` zeigt bei
solchen Tunneln einen Hinweis.

## Wo die Schlüssel liegen

- Nur in `/etc/wireguard/NAME.conf`, Rechte `600`, Besitzer `root:root`. Der Ordner selbst hat `700`.
  Geschrieben wird atomar: temporäre Datei mit `600` im selben Ordner, `fsync`, dann `rename`.
- **Nie** in Ausgaben, Protokollen, `vm.json`, Vorlagen-Metadaten, Tests oder im Repo.
  - `status`, `list` und `show` geben nur nicht geheime Angaben aus. `show` ersetzt `PrivateKey` und
    `PresharedKey` durch `(verborgen)`. Speichert der Editor `(verborgen)` zurück (`import --replace`),
    setzt der Helfer die gespeicherten Schlüssel wieder ein.
  - Live-Werte kommen aus `wg show NAME endpoints|latest-handshakes|transfer`, nie aus `wg show … dump`,
    denn `dump` enthält den privaten Schlüssel.
  - Fehlerausgaben fremder Programme (wg-quick, nft) laufen durch einen Filter, der alles entfernt,
    was wie ein WireGuard-Schlüssel aussieht.
- `export` ist die einzige Ausnahme. Es gibt die Konfiguration mit Schlüssel zurück, die
  Kommandozeile schreibt sie mit Rechten `600` und überschreibt keine vorhandene Datei.
- Die Tests prüfen, dass der private Schlüssel in keiner Ausgabe auftaucht.

## Kill-Switch

Eigene Tabelle `inet bonys_vpn` mit einer Kette am Hook `output` (Richtlinie `drop`). Erlaubt sind:

1. Loopback (`lo`) und die WireGuard-Geräte aller Tunnel
2. Antworten auf Verbindungen, die von außen hereinkommen (`ct direction reply`), etwa SSH zum Agent-PC
3. DHCP (v4/v6) und IPv6-Nachbarsuche, damit die Netzwerkkarte ihre Adresse behält
4. die Endpunkte aller Tunnel (IP + UDP-Port), damit der Tunnel aufgebaut werden kann
5. DNS (Port 53) **nur für root** und, falls vorhanden, für `systemd-resolve`. So lassen sich
   Endpunkt-Namen wie `xyz.myfritz.net` auflösen, bevor der Tunnel steht. Normale Programme
   bekommen ohne Tunnel kein DNS. Mit systemd-resolved können Namensanfragen anderer Programme
   ohne Tunnel über resolved hinausgehen, Daten aber nicht.
6. die Ausnahmeliste (Netze)

Alles andere wird mit „administratively prohibited“ abgewiesen. Programme bekommen so sofort einen
Fehler und hängen nicht.

- **Endpunkt-Namen** werden beim Einschalten, bei `up` und bei Änderungen an den Tunneln neu aufgelöst.
  Klappt das nicht, gelten die zuletzt bekannten Adressen aus `/etc/bonys-vpn/killswitch.json` weiter.
- **Atomar**: Das Regelwerk (`/etc/bonys-vpn/killswitch.nft`) ersetzt die Tabelle in einer einzigen
  `nft -f`-Transaktion. Es gibt also keinen Moment ohne Regeln, und andere Tabellen (Docker, ufw,
  wg-quick) bleiben unberührt.
- **Nach einem Neustart** lädt die Unit `bonys-vpn-killswitch.service` die Regeln vor
  `network-pre.target`, also bevor das Netz hochkommt. Sie hat absichtlich kein `ExecStop`, damit der
  Schutz bis zum Ausschalten bleibt.
- **Ausschalten** (`killswitch off`): Unit deaktivieren, Tabelle löschen, Regeldatei entfernen.
  Danach ist nichts mehr übrig. `install.py --uninstall` schaltet den Kill-Switch ebenfalls ab.
- **Grenzen**: Gefiltert wird nur Verkehr, den dieser Rechner selbst erzeugt. Weitergeleiteter Verkehr
  (Docker-Container, Bridges, libvirt) läuft nicht über `output`. Programme von Bony's Agents mit
  QEMU-User-Netz (die Agent-PCs selbst) sind dagegen erfasst, weil QEMU ein Prozess auf dem Host ist.

## Unterschied Agent-PC / Host

| | Agent-PC | Host |
|---|---|---|
| polkit-Regel | Benutzer `agent` darf **ohne Passwort** (`agent.rules`) | `auth_admin_keep`: Administrator-Passwort, einige Minuten gemerkt (`host.rules`) |
| Kill-Switch-Ausnahmen | `10.0.2.0/24`, das QEMU-User-Netz | keine (eigene Netze per `--ausnahme`, z. B. Drucker im Heimnetz) |
| Einordnung | Der Benutzer `agent` hat im Agent-PC ohnehin `sudo` ohne Passwort. Die Regel erspart nur die Abfrage und ist **keine Sicherheitsgrenze**: Jedes Programm im Agent-PC, auch der KI-Agent, kann den Tunnel steuern, den Kill-Switch abschalten und den Schlüssel lesen | Hier ist der Helfer die Grenze: Ohne Administrator-Passwort geht nichts |

**Warum `10.0.2.0/24` im Agent-PC?** Bony's Agents steuert den Agent-PC über das QEMU-User-Netz:
Die SSH-Weiterleitung (`hostfwd`) kommt von `10.0.2.2`, der Host ist unter `10.0.2.2` erreichbar,
das QEMU-DNS liegt auf `10.0.2.3`. Der Gast-Agent (Befehle, Herunterfahren) läuft über
virtio-serial und braucht gar kein Netz. Ohne diese Ausnahme blieben Steuerung und Herunterfahren
trotzdem möglich, RDP und SSH aber nur eingeschränkt. Weil `10.0.2.3` in dieser Ausnahme liegt,
gehen DNS-Anfragen im Agent-PC bei getrenntem Tunnel weiter an das QEMU-DNS. Daten gehen nicht hinaus.

**Schlüssel im Agent-PC**: Eine .conf wird nur in diesen einen Agent-PC übertragen (Sitzung 4).
Vorlagen „frisch“ löschen Schlüssel und Tunnel. Bei einem Klon bleibt der Schlüssel erhalten, mit
Warnhinweis: Zwei PCs mit demselben Schlüssel werfen sich gegenseitig aus dem Tunnel.

## Installation

`install.py` (als root, nur Standardbibliothek) legt ab:

| Pfad | Inhalt |
|---|---|
| `/usr/local/lib/bonys-vpn/bonys_vpn/` | Das Paket (`conf`, `killswitch`, `helper`, `cli`, `install`) |
| `/usr/local/sbin/bonys-vpn-helper` | Startet den Helfer mit `#!/usr/bin/python3 -I` |
| `/usr/local/bin/bonys-vpn` | Kommandozeile |
| `/usr/local/bin/bonys-vpn-gui` | Oberfläche (GTK 3) |
| `/usr/local/share/applications/io.github.bonys_agents.vpn.desktop` | Desktop-Eintrag |
| `/etc/xdg/autostart/bonys-vpn-tray.desktop` | Tray-Symbol nach der Anmeldung (nur mit `--autostart-tray`, im Agent-PC) |
| `/usr/share/polkit-1/actions/io.github.bonys-agents.vpn.policy` | polkit-Aktion `io.github.bonys-agents.vpn`, gilt nur für genau den Helfer-Pfad |
| `/etc/polkit-1/rules.d/50-bonys-vpn.rules` | Regel für den Agent-PC oder den Host |
| `/etc/systemd/system/bonys-vpn-killswitch.service` | Kill-Switch nach dem Neustart |
| `/etc/bonys-vpn/killswitch.json` | an/aus, Ausnahmen, zuletzt aufgelöste Endpunkte (keine Schlüssel) |

Auf dem eigenen Rechner bringt das .deb von Bony's Agents dieselben Teile an andere Orte mit
(`install.py --variant host --layout system --root PAKETORDNER` beim Paketbau, siehe unten).

```sh
sudo python3 -I install.py --variant agent --user agent --autostart-tray   # Agent-PC
sudo python3 -I install.py --variant host                 # eigener Rechner
sudo python3 -I install.py --uninstall                    # Tunnel in /etc/wireguard bleiben
```

Alle Dateien gehören root und sind nur für root beschreibbar. Sonst könnte ein Benutzer den Code
ändern, den pkexec als root startet.

## Kommandozeile

```text
bonys-vpn list
bonys-vpn status [NAME] [--json]
bonys-vpn up NAME | down [NAME]
bonys-vpn import DATEI.conf|DATEI.zip … [--name NAME] [--hooks-erlauben] [--ersetzen]
bonys-vpn delete NAME [--ja] | rename ALT NEU | export NAME [DATEI]
bonys-vpn autostart NAME an|aus
bonys-vpn killswitch an|aus|status [--ausnahme NETZ …]
```

## Oberfläche

`bonys-vpn-gui` (GTK 3 über `python3-gi`, Tray über Ayatana-AppIndicator) läuft als Benutzer und
ruft für alles, was root braucht, denselben Helfer auf wie die Kommandozeile.

**Warum GTK 3 und nicht PySide6:** Cinnamon, Xfce, GNOME und MATE bauen auf GTK 3 auf, `python3-gi`
gehört schon zur Grundausstattung der Agent-PCs. Dazu kommen nur `gir1.2-gtk-3.0` und
`gir1.2-ayatanaappindicator3-0.1`, zusammen etwa 2 MB. PySide6 aus Debian bräuchte zusätzlich rund
74 MB, selbst wenn die Qt6-Bibliotheken schon da sind (gemessen mit apt in Debian 13, Xfce). Nur unter
KDE Plasma und LXQt (Qt) holt `gir1.2-gtk-3.0` die GTK-3-Bibliotheken nach. Tray-Symbole funktionieren
mit beiden Toolkits gleich (StatusNotifierItem). Keine pip-Pakete.

- **Tray:** StatusNotifierItem (Cinnamon, Xfce, KDE, MATE, LXQt), sonst das klassische Infobereich-Symbol
  (XEmbed). Zeigt der Desktop keine Statussymbole (GNOME ohne Erweiterung), läuft der Hintergrund ohne
  Symbol weiter und meldet nur Abbrüche. Eine Instanz (D-Bus): Ein zweiter Aufruf öffnet das Fenster der
  laufenden.
- **Status ohne ständiges pkexec:** Ob ein Tunnel verbunden ist und wie viele Daten fließen, liest die
  Oberfläche ohne root aus `/sys/class/net`. Den Helfer (`status`) fragt sie nur nach Aktionen, bei
  offenem Fenster alle 10 s (Handshake) und im Hintergrund, wenn 150 s nichts mehr hereinkommt, obwohl
  gesendet wird.
- **Abbruch-Meldung:** Der Tunnel verschwindet ohne eigene Aktion, oder der Server antwortet nicht mehr:
  Handshake älter als 3 Minuten, obwohl mehr als 135 s nach dem letzten gesendet wurde. Ein untätiger
  Tunnel hat nur einen alten Handshake und gilt nicht als abgebrochen.
- **Öffentliche IP:** nur auf Knopfdruck, über `https://api.ipify.org`. Die Oberfläche nennt den Dienst.
- **Editor:** zeigt die Konfiguration mit `(verborgen)` statt Schlüssel (`show`). „Schlüssel anzeigen“ holt
  sie über `export`, nur bei eigenen Tunneln. Vor dem Speichern wird geprüft. Unverändert gelassenes
  `(verborgen)` setzt der Helfer wieder ein. Hook-Zeilen brauchen beim Import und beim Speichern eine
  ausdrückliche Bestätigung.
- **Export** schreibt mit Rechten `600` (atomar). Dateidialoge starten im persönlichen Ordner.
- **Sprache:** Deutsch, auf nicht deutschen Systemen Englisch (`LANGUAGE`, `LC_ALL`, `LC_MESSAGES`, `LANG`).

Im Agent-PC installiert die App-Option „WireGuard VPN (Bony's VPN)“ (`apps.VPN`, standardmäßig aus)
alles: Debian-Pakete, dann `install.py --variant agent --autostart-tray`. Der Code steht als tar.gz
(base64) im Installationsschritt. Beim Erstellen kommt er so über das Seed-ISO in den Agent-PC, beim
Nachinstallieren über den SSH-Weg („Programme hinzufügen“). Im PyInstaller-Paket liegen die
`.py`-Dateien von `vpn/` deshalb zusätzlich als Daten.

## Anbindung an Bony's Agents

Die Seite von Bony's Agents liegt in `src/bonys_agents/vpnlink.py`. Sie liest eine .conf nur, prüft sie
mit derselben Prüfung wie der Helfer (`conf.decode` + `conf.parse`) und reicht sie direkt in den
Agent-PC. Auf dem Host bleibt nichts: kein Feld in `vm.json`, keine Zeile in Protokollen oder
Fortschrittstexten, nichts in Vorlagen-Metadaten. `VpnSetup` zeigt die Daten auch in `repr` nicht.
Konfigurationen mit Hook-Zeilen lehnt Bony's Agents ab. Sie lassen sich nur im Agent-PC über
Bony's VPN mit der Warnung importieren.

### Beim Erstellen

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

### Im laufenden Agent-PC

- Detailansicht, Reiter **VPN**: Status (verbunden/getrennt, Tunnel, Adresse, Server, Handshake, Daten),
  „Verbinden“, „Trennen“, „Öffentliche IP prüfen“ (als Benutzer des Agent-PCs über api.ipify.org),
  „Konfiguration importieren …“, Schalter für Autostart und Kill-Switch. Ohne Bony's VPN steht dort
  „VPN-App installieren“ (öffnet „Programme hinzufügen“ mit der VPN-App).
- Weg: Gast-Agent (`guest-exec` als root, `bonys-vpn status --json`, Import über `input-data`, also
  über die Standardeingabe des Helfers). Antwortet der Gast-Agent nicht, per SSH mit `sudo` und dem
  Passwort des Agent-PCs. Fehlermeldungen laufen auf dem Host noch einmal durch den Schlüsselfilter.
- Kommandozeile: `bonys-agents vpn NAME status [--json] | up [TUNNEL] | down [TUNNEL] | import DATEI
  [--tunnel NAME] [--replace] | killswitch on|off | autostart on|off [--tunnel NAME] | ip`.

### Vorlagen

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

### Verträglichkeit mit dem Kill-Switch

Geprüft im echten Test (Kill-Switch an, Tunnel getrennt): Gast-Agent, QMP, SSH-Weiterleitung,
Herunterfahren (2,3 s), Fortschrittsanzeige (serielle Konsole), RDP (xrdp über die Weiterleitung),
dynamische Auflösung (spice-vdagent über virtio-serial). „Agent-PC aktualisieren“ geht über den
Tunnel. Ohne Tunnel meldet es: „Kill-Switch an und kein Tunnel verbunden – erst verbinden“ (vorher
hätte apt die Netzfehler als Erfolg gemeldet).

## Eigener Rechner (Host)

### Linux: das .deb von Bony's Agents

| Pfad | Inhalt |
|---|---|
| `/usr/lib/bonys-agents/vpn/bonys_vpn/` | Das Paket (ohne GTK-Oberfläche), läuft mit dem System-Python, nicht mit dem PyInstaller-Bündel |
| `/usr/sbin/bonys-vpn-helper` | Helfer, `#!/usr/bin/python3 -I` |
| `/usr/bin/bonys-vpn` | Kommandozeile |
| `/usr/share/polkit-1/actions/io.github.bonys-agents.vpn.policy` | polkit-Aktion, gilt nur für `/usr/sbin/bonys-vpn-helper` |
| `/usr/share/polkit-1/rules.d/50-bonys-vpn.rules` | `host.rules`: `AUTH_ADMIN_KEEP` für aktive lokale Sitzungen, sonst `AUTH_ADMIN`. Einzige Ausnahme ohne Passwort: genau `bonys-vpn-helper status` (siehe unten) |
| `/usr/lib/systemd/system/bonys-vpn-killswitch.service` | Kill-Switch nach dem Neustart (eingeschaltet nur über den Helfer) |
| `/usr/share/applications/bonys-vpn.desktop` | Desktop-Eintrag „Bony's VPN“ → `/opt/bonys-agents/BonysAgents --vpn` |

- Unter `/etc` liefert das Paket nichts aus (keine Conffiles). `/etc/bonys-vpn` und `/etc/wireguard`
  legt der Helfer bei Bedarf an. `dpkg --purge` löscht `/etc/bonys-vpn`, **nie** `/etc/wireguard`.
- `Depends: python3`, `Recommends: wireguard-tools, nftables` (neben `pkexec`). Fehlen die beiden,
  bietet der Bereich „VPN“ an, sie nach Rückfrage mit `pkexec apt-get install` nachzuinstallieren.
- `prerm remove` schaltet den Kill-Switch ab. Sonst bliebe der Rechner ohne Tunnel offline, ohne dass es
  noch ein Programm zum Abschalten gäbe. Bei einem Update bleibt er an.
- `install.py --layout system` geht nur mit `--root` (zum Paketbau). Auf einem Rechner mit dem .deb
  nicht zusätzlich `install.py --variant host` verwenden: Beide legen dieselbe polkit-Datei an.
- Die Kommandozeile sucht den Helfer zuerst unter `/usr/local/sbin` (install.py, Agent-PC), dann unter
  `/usr/sbin` (.deb), oder nimmt `BONYS_VPN_HELPER`.

### Status ohne Passwort

Die Oberfläche fragt bei sichtbarem Bereich alle 10 s den Helfer (`status`) nach dem Handshake. Mit
`auth_admin_keep` allein käme immer wieder die Passwortabfrage. Deshalb erlaubt `host.rules` der aktiven
lokalen Sitzung genau die Befehlszeile `/usr/sbin/bonys-vpn-helper status` (ohne weitere Argumente)
**ohne Passwort**. pkexec gibt sie den Regeln als `command_line` mit. Alles andere fragt weiter nach dem
Administrator-Passwort.

Zuerst war dafür eine zweite polkit-Aktion mit `org.freedesktop.policykit.exec.argv1 = status` gedacht.
Das greift nicht: pkexec nimmt die **erste** Aktion, deren `exec.path` passt, und eine Aktion ohne `argv1`
passt immer (im echten Test auf Mint 22 mit polkit 124 kam deshalb trotzdem die Abfrage).

`status` gibt nur nicht geheime Angaben aus: Tunnelnamen, Adressen, DNS, Endpunkte, Handshake, Datenmenge,
Kill-Switch-Zustand. Die sieht damit jeder Benutzer, der am Rechner angemeldet ist, Schlüssel nie. Fehlt die
Regel (ältere Installation), fragt die Oberfläche den Helfer nur auf Knopfdruck und liest Verbunden/Getrennt
und die Datenmenge aus `/sys`.

**Wie oft fragt polkit?** `auth_admin_keep` merkt sich die Anmeldung einige Minuten **für den aufrufenden
Prozess**. Im Fenster von Bony's Agents ist das immer derselbe Prozess, also eine Abfrage für mehrere
Aktionen. Jeder einzelne Aufruf von `bonys-vpn` auf der Kommandozeile ist ein neuer Prozess und fragt neu.

### WireGuard-Verbindungen des NetworkManager

Tunnel, die der NetworkManager verwaltet (z. B. über „Netzwerkverbindungen“ importiert), stehen oft
zusätzlich in `/etc/wireguard` und erscheinen dann als fremde Tunnel. Trennen kann sie nur der
NetworkManager (`wg-quick down` kennt sie nicht), und sie benutzen dieselbe Routing-Tabelle und Markierung
(51820) wie wg-quick. Die Oberfläche erkennt sie über `nmcli` (als Benutzer): Bei ihnen ist „Trennen“ aus,
mit dem Hinweis auf das Netzwerk-Symbol, und vor dem Verbinden eines anderen Tunnels kommt die Bitte,
den NetworkManager-Tunnel zuerst zu trennen.

### Oberfläche (Qt)

`gui/host_vpn.py`: Bereich „VPN“ im Hauptfenster (Knopf oben, nur Linux) und eigenes Fenster
(`BonysAgents --vpn`) mit Tray-Symbol (`QSystemTrayIcon`, schließt in den Infobereich). Dieselbe Logik wie
im Agent-PC (`vpn/model.py`: Status, Live-Werte, Abbruch-Erkennung, Editor-Prüfung, Namensvorschlag,
Export mit 600), dieselben Aufrufe des Helfers (`vpn/cli.call`, Konfigurationen über die Standardeingabe).

- Vor dem Verbinden oder Import: Hinweis „Das VPN gilt dann für deinen ganzen Rechner, nicht nur
  für die Agent-PCs.“ (abschaltbar mit „Nicht mehr anzeigen“).
- Kill-Switch nur nach einer zusätzlichen Warnung. Ausnahmen (z. B. das Heimnetz) über „Ausnahmen …“
  (`killswitch on --exception NETZ … | --no-exceptions`).
- Konfigurationen mit Hook-Zeilen nur nach der Warnung (wie im Agent-PC).

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
