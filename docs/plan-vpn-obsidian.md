# Plan: Obsidian und Bony's VPN

Zwei neue Funktionen für Bony's Agents, gebaut in fünf Sitzungen:

1. **Obsidian** als optionale App im Agent-PC.
2. **Bony's VPN**: WireGuard-VPN mit einem selbst entwickelten Werkzeug, im Agent-PC und auf dem Linux-Host.

Jede Sitzung liest zuerst diese Datei (und ab Sitzung 2 `docs/vpn.md`) und aktualisiert am Ende den Abschnitt [Stand](#stand).

## Regeln (gelten für alle Sitzungen)

- Programme immer von der offiziellen Quelle laden (Debian-Paketquellen, offizielle GitHub-Releases, winget, App Store/Herstellerseite). Nichts Fremdes in unser Repo oder Paket kopieren außer eigenem Code.
- wireguird (https://github.com/UnnoTed/wireguird) ist nur Vorbild für Bedienung/Funktionen, kein Code wird übernommen.
- VPN-Konfigurationen/Schlüssel landen nie in vm.json, Logs, Vorlagen-Metadaten, Tests oder im Repo und werden nie ausgegeben.
- Keine Zugangsdaten im Agent-PC vorkonfigurieren.
- Vor jedem Befehl mit sudo nachfragen.

Zum Testen gibt der Nutzer nur den **Pfad** einer Test-.conf an (z. B. `~/vpn-test/test.conf`, Rechte 600). Ihr Inhalt wird nie gelesen, ausgegeben oder irgendwo abgelegt. Der Helfer verarbeitet die Datei, sonst nichts.

## Obsidian (Sitzung 1)

- App-Option „Obsidian (Notizen)“, standardmäßig aus. Beschreibung: „kostenlos, aber kein Open Source“.
- Quelle: offizielles GitHub-Release `obsidianmd/obsidian-releases`. Die neueste Version wird beim Installieren über die GitHub-API ermittelt, nicht fest eingetragen.
  - amd64: `obsidian_<version>_amd64.deb` über `apt-get install` (zieht die Abhängigkeiten aus Debian).
  - arm64: Es gibt keine .deb. Gewählt: `obsidian-<version>-arm64.tar.gz` nach `/opt/Obsidian`, dieselben Abhängigkeiten wie in der .deb aus Debian, eigener Desktop-Eintrag, `/usr/bin/obsidian` als Verweis. Das AppImage bräuchte FUSE. Das Flatpak `md.obsidian.Obsidian` auf Flathub stammt nicht von Obsidian selbst.
  - Prüfsumme: Die GitHub-API liefert für jede Datei ein SHA-256 (`digest`). Es wird mit `sha256sum -c` geprüft. Stimmt es nicht, bricht die Installation ab. Fehlt es, gibt es eine Warnung.
- Desktop-Eintrag heißt wie in der offiziellen .deb `md.obsidian.Obsidian.desktop`. Unsere Fassung in `/usr/local/share/applications` (hat Vorrang, übersteht Updates der .deb) startet mit dem Electron-Schalter `--password-store=basic`. Sonst fragt Obsidian beim ersten Start nach einem Schlüsselbund-Passwort, weil die automatische Anmeldung keinen entsperrten Schlüsselbund hat.
- Verknüpfung auf dem Schreibtisch, leerer Tresor `~/Agent-Notizen`, in `~/.config/obsidian/obsidian.json` als geöffneter Tresor eingetragen. Keine Anmeldung, kein Sync.
- Vorlagen: Anmeldung/Einstellungen in `~/.config/obsidian` (außer der Tresorliste) und der Inhalt von `~/Agent-Notizen` gehören zu den persönlichen Daten, die gelöscht werden.
- Claude Code: Hinweis „kein Open Source, Nutzung braucht ein kostenpflichtiges Claude-Abo oder API-Guthaben“. „Kostenlos“ wäre bei Claude Code falsch.
- Läuft auch über „Programme nachinstallieren“ (`bonys-agents install NAME obsidian`).

### Geteilter Ordner Host ↔ Agent-PC: später

Geprüft, aber nicht umgesetzt:

- **virtiofs**: QEMU braucht dafür den externen Dienst `virtiofsd` und einen geteilten Arbeitsspeicher (`memory-backend-memfd`, `share=on`). Das ändert den Start aller Agent-PCs und geht nur unter Linux.
- **9p (`-virtfs`)**: unter Linux und macOS möglich, unter Windows hat QEMU es nicht. Langsam, mit Problemen bei Dateirechten und mehreren Sicherheitslücken in der Vergangenheit (Ausbruch über Symlinks).
- Grundsätzlich: Der Agent-PC ist absichtlich vom Host getrennt. Ein geteilter Ordner gibt jedem Programm im Agent-PC, auch dem KI-Agenten, Lese- und Schreibzugriff auf diesen Host-Ordner.

Vorschlag für später: nur Linux/macOS, nur ein eigens angelegter, leerer Ordner, standardmäßig aus, mit deutlicher Warnung. Alternativ ein Sync über SSH/`rsync` auf Knopfdruck, der ohne neue QEMU-Geräte auskommt.

## Bony's VPN

### Ziel und Aufbau

- **Oberfläche** (läuft als normaler Benutzer) und **Root-Helfer `bonys-vpn-helper`**, aufgerufen über `pkexec`, polkit-Aktion `io.github.bonys-agents.vpn`.
- Der Helfer erlaubt nur:
  - auflisten, `up`, `down`, `status`
  - importieren, umbenennen, löschen in `/etc/wireguard` (Dateirechte 600)
  - Autostart (`wg-quick@NAME`) an/aus
  - Kill-Switch (nftables) an/aus
- Tunnelnamen nur `[a-zA-Z0-9_=+.-]{1,15}`.
- `PreUp`/`PostUp`/`PreDown`/`PostDown` (Hook-Zeilen) nur nach ausdrücklicher Warnung.
- polkit: im Agent-PC ohne Passwort für den Benutzer `agent`, auf dem Host `auth_admin_keep`.
- Code in `src/bonys_agents/vpn/`, ohne Abhängigkeit vom Rest von Bony's Agents (wird einzeln in den Agent-PC kopiert), nur Debian-Pakete (python3, wireguard-tools, nftables).

### Funktionen der Oberfläche

- Tunnelliste mit Status
- Ein-Klick verbinden/trennen (nur ein Tunnel gleichzeitig)
- Details: Adresse, DNS, Endpunkt, letzter Handshake, Datenmenge live, öffentliche IP optional
- Import per Dateiauswahl, Drag&Drop, mehrere Dateien, ZIP
- Umbenennen, Löschen, Export
- Editor mit Prüfung und maskiertem Private Key
- Autoconnect
- Kill-Switch (die Steuerung des Agent-PCs über das QEMU-Netz bleibt erlaubt)
- Tray-Symbol, Benachrichtigung bei Abbruch
- Deutsch/Englisch
- CLI `bonys-vpn list|up|down|status|import|delete`

### Anbindung an Bony's Agents

- .conf beim Erstellen wählen. Sie wird nur in den Agent-PC übertragen.
- Detailansicht: Status und Knöpfe.
- CLI: `bonys-agents create --vpn-config/--vpn-autoconnect/--killswitch` und `bonys-agents vpn NAME status|up|down|import`.
- Vorlagen: „frisch“ = Schlüssel/Tunnel löschen, Autoconnect aus. Klon = alles behalten, mit Warnhinweis (gleicher Schlüssel auf zwei PCs).

### Eigener Rechner (Host)

- **Linux**: Bony's VPN im Bony's-Agents-Fenster plus eigener Desktop-Eintrag. `wireguard-tools` als Recommends.
- **Windows**: offizielle WireGuard-App per winget (`WireGuard.WireGuard`).
- **macOS**: offizielle App aus dem App Store. Prüfen, ob es einen automatischen Weg gibt, sonst die App-Store-Seite öffnen und erklären.

## Sitzungen

| Sitzung | Inhalt | Modell |
|---|---|---|
| 1 | Plan-Datei + Obsidian | Sonnet reicht |
| 2 | Root-Helfer + bonys-vpn-Kommandozeile + Sicherheitskonzept `docs/vpn.md` | Opus |
| 3 | Oberfläche von Bony's VPN im Agent-PC | Opus |
| 4 | Einbindung in Bony's Agents (Erstellen, Detailansicht, Vorlagen, Kill-Switch-Test) + echte Tests | Opus |
| 5 | Eigener Rechner (Linux, Windows, Mac), README, Release | Sonnet oder Opus |

Vor jeder Sitzung `/clear`. Wird es zwischendurch knapp: „mach einen Zwischenstand in die Plan-Datei und committe“. Die nächste Sitzung macht dann dort weiter. Ein Release gibt es erst in Sitzung 5.

## Stand

### Sitzung 1 – Plan + Obsidian

- [x] Plan-Datei angelegt
- [x] App-Option „Obsidian (Notizen)“ (amd64 .deb, arm64 tar.gz, neueste Version, SHA-256)
- [x] Hinweis „kein Open Source“ bei Obsidian und Claude Code
- [x] Schreibtisch-Verknüpfung, Tresor „Agent-Notizen“, keine Schlüsselbund-Abfrage
- [x] Nachinstallieren bei bestehenden Agent-PCs (`bonys-agents install NAME obsidian`, „Programme hinzufügen“)
- [x] Vorlagen: Obsidian-Daten bei den persönlichen Daten
- [x] Tests für die App-Registry (Auswahl der Datei für amd64/arm64, fremde URL, fehlende Prüfsumme, Vorlagen)
- [x] Echter Test (2026-10-09, amd64, Cinnamon): Agent-PC „obsidian-test“ neu erstellt. Prüfsumme „OK“, Nachinstallieren im laufenden Agent-PC, Start über den Desktop-Eintrag, Tresor „Agent-Notizen“ offen, keine Abfrage. Screenshots per QMP screendump.
- [ ] arm64-Weg (tar.gz) nur per Unit-Test geprüft, nicht auf echter arm64-Hardware
- [x] Geteilter Ordner geprüft → später (siehe oben)
- [x] pytest (218 grün), ruff, Commit

### Sitzung 2 – Root-Helfer, CLI, Sicherheitskonzept

- [x] `src/bonys_agents/vpn/`: `conf.py` (Prüfung, Namen, Schlüssel verbergen), `killswitch.py` (nft-Regelwerk), `helper.py` (`bonys-vpn-helper`), `cli.py` (`bonys-vpn`), `install.py` (eigenständig), `data/` (polkit-Aktion, Regeln agent/host, systemd-Unit). Nur Standardbibliothek, nur relative Importe.
- [x] Helfer bekommt keine Pfade: .conf kommt über stdin (die CLI liest sie als Benutzer). Fehlermeldungen ohne Werte, Ausgaben fremder Programme werden von schlüsselähnlichem Text bereinigt, Status nie über `wg show … dump`.
- [x] Eigene Tunnel tragen die Kopfzeile `# Verwaltet von Bony's VPN`. Nur sie lassen sich löschen, umbenennen und exportieren.
- [x] Kill-Switch `inet bonys_vpn` (nur output): lo, Tunnel-Geräte, `ct direction reply`, DHCP, IPv6-ND, Endpunkte, DNS nur root/systemd-resolve, Ausnahmen; Rest `reject`. Unit `bonys-vpn-killswitch.service` vor `network-pre.target`, ohne ExecStop.
- [x] polkit: eine Aktion `io.github.bonys-agents.vpn`, `agent.rules` (Benutzer ohne Passwort), `host.rules` (`auth_admin_keep`)
- [x] Installation an feste Orte: `/usr/local/lib/bonys-vpn/bonys_vpn/`, `/usr/local/sbin/bonys-vpn-helper` (`python3 -I`), `/usr/local/bin/bonys-vpn`, `/etc/bonys-vpn/`
- [x] `docs/vpn.md` (Sicherheitskonzept)
- [x] 75 Tests in `tests/test_vpn.py` (Attrappen für wg/wg-quick/nft/systemctl/pkexec, nur unter Linux). Regelwerk zusätzlich mit echtem `nft` 1.0.9 im eigenen Namensraum geladen. pytest 293 grün, ruff sauber.
- [x] Praxistest (2026-10-10, Agent-PC „obsidian-test“, Debian 13): Pakete `wireguard-tools nftables` per apt, Dateien per Gast-Agent übertragen, `install.py --variant agent`. Eigene Server-.conf (Pfad vom Nutzer, Inhalt nie gelesen) über den Gast-Agent in einen 700-Ordner gelegt, als `agent` importiert, Kopie gelöscht. Ergebnisse:
  - Kill-Switch ohne Tunnel: Internet sofort gesperrt, SSH vom Host und Gast-Agent gehen
  - `up`: öffentliche IP = VPN-Server, Status/JSON mit Handshake und Daten, SSH bei aktivem Tunnel geht
  - `down`: wieder gesperrt; Autostart an → Neustart: Kill-Switch lädt vor NetworkManager, Tunnel verbindet sich selbst
  - `bonys-agents stop` bei aktivem Tunnel + Kill-Switch: sauber in 2,4 s
- Erkenntnis: Der Agent-PC nutzt systemd-resolved, `resolvconf` kommt von dort. **openresolv nicht installieren.** Sitzung 4: `wireguard-tools nftables` in die Paketliste der Agent-PCs, Helfer beim Erstellen installieren.
- Hinweis: Der Benutzer `agent` hat sudo ohne Passwort. Im Agent-PC ist der Helfer also Bequemlichkeit, keine Sicherheitsgrenze (steht in `docs/vpn.md`).
- Offen für Sitzung 5 (Host): Pfade für das .deb (statt `/usr/local`), `bonys-vpn` als Skript im Paket.
- Achtung: In „obsidian-test“ liegt der Tunnel „bonysagents“ (echter Schlüssel), Autostart und Kill-Switch sind an. Für Sitzung 3/4 nutzbar, sonst mit `bonys-vpn delete bonysagents --ja` und `bonys-vpn killswitch aus` aufräumen.

### Sitzung 3 – Oberfläche im Agent-PC

- [ ] offen

### Sitzung 4 – Einbindung in Bony's Agents

- [ ] offen

### Sitzung 5 – Eigener Rechner, Doku, Release

- [ ] offen

### Später

- Geteilter Ordner Host ↔ Agent-PC (siehe oben)
- Obsidian auf einem echten arm64-Agent-PC testen
