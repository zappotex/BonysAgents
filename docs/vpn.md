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
| `bonys-vpn` (`cli.py`), später die Oberfläche | Benutzer | Bedienung. Liest .conf-Dateien mit den Rechten des Benutzers |
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
| `/usr/share/polkit-1/actions/io.github.bonys-agents.vpn.policy` | polkit-Aktion `io.github.bonys-agents.vpn`, gilt nur für genau den Helfer-Pfad |
| `/etc/polkit-1/rules.d/50-bonys-vpn.rules` | Regel für den Agent-PC oder den Host |
| `/etc/systemd/system/bonys-vpn-killswitch.service` | Kill-Switch nach dem Neustart |
| `/etc/bonys-vpn/killswitch.json` | an/aus, Ausnahmen, zuletzt aufgelöste Endpunkte (keine Schlüssel) |

```sh
sudo python3 -I install.py --variant agent --user agent   # Agent-PC
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
