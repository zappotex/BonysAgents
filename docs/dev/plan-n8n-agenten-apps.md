# Plan: n8n, Software-Center und „Agenten-Apps“ (Release 0.24.0)

Auftrag: `docs/dev/auftrag-n8n-agenten-apps.md` (22.10.2026, nicht im Repo – steht in `.gitignore`; Vorlage
`agenten-apps-vorlage.zip` in `BonysAgents/new for new release/`).
Neue Sitzung: **„Mach weiter laut docs/dev/plan-n8n-agenten-apps.md“** – zuerst [Stand](#stand) lesen.

## Entscheidungen (Bony, 22.10.2026)

- **Software-Center UND Agenten-Apps-Liste:** Das Video „Agent-PC persönlich einrichten“ (3:01) verspricht, dass
  das Software-Center in der nächsten Version dabei ist. Deshalb kommt GNOME Software (Flathub) fest in jeden neuen
  Agent-PC – mit sauberem Offline-Fix – und zusätzlich die Liste „Agenten-Apps“ für Programme mit MCP-Server.
- **Online-Liste auf GitHub Pages:** `https://zappotex.github.io/BonysAgents/agenten-apps/` (nicht bony23.de).
  Erzeugt aus derselben `agent-apps.yaml`; neue Einträge brauchen kein neues Release.
- **Craft-Programme mit in die Liste:** WordCraft, GridCraft, DeckCraft, CADCraft, SolidCraft zusätzlich zu den
  sechs Einträgen der Vorlage (GridCraft-MCP mit Hermes am 22.10. im Video getestet).

## Umsetzung (bestehende Muster)

Alles als `AppSpec` in `apps.py` – dann gilt automatisch: im Dialog „Neuer Agent-PC“ wählbar, über
„Programme hinzufügen …“ nachrüstbar, in Vorlagen/Manifest, Update-Befehl.

| App-ID | Standard | Inhalt |
|---|---|---|
| `software-center` | an | `gnome-software` + `gnome-software-plugin-flatpak`; Offline-Fix (siehe unten) |
| `agenten-apps` | an | `agent-apps.yaml` + `build_agent_apps.py` als Heredoc in den Gast, dort mit `python3-yaml` und `--home "$AGENT_HOME"` → `/usr/share/bonys-agents/agenten-apps/index.html`; Starter in `/usr/share/applications/` + Schreibtisch; `~/Agent-Dateien` |
| `n8n` | an | `requires=("brave", "docker")`; eigenes Modul `n8n.py` wie `mission_control.py` |

### n8n
- Offizielles Image `docker.n8n.io/n8nio/n8n`, Container `n8n`, `-p 127.0.0.1:5678:5678`, Volume
  `n8n_data:/home/node/.n8n`, `GENERIC_TIMEZONE`/`TZ` = Zeitzone des Agent-PCs (sonst Europe/Berlin),
  `N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=true`, `--restart unless-stopped` (Docker-Dienst ist enabled).
- Start-/Neuanlage-Skript `/usr/local/bin/bonys-n8n` (install + update: `docker pull` → Container neu anlegen;
  Volume bleibt).
- Starter „n8n“ öffnet `http://localhost:5678` in Brave (wie Mission Control, `--password-store=basic` nur mit
  Markierung).
- Dialog: Lizenzhinweis „Sustainable Use License – Quellcode offen, aber keine OSI-Open-Source-Lizenz“; RAM-Warnung
  (≈ 1 GB zusätzlich) wie bei Mission Control → Abschnitt verallgemeinern (Docker-Apps mit Erklärung).
- Vorlagen: n8n-Daten im Volume = persönliche Daten → beim „frischen“ Export Volume leeren (wie Mission Control).
- Lizenz: Sustainable Use License erlaubt die Nutzung, Weitergabe des Images in Vorlagen? → prüfen; im Zweifel
  `redistributable=False` (Image wird beim Empfänger neu geladen).

### Software-Center – Offline-Fix
Ursache (Test 22.10.): NetworkManager läuft (kommt mit Cinnamon), `enp0s3` wird aber von systemd-networkd
(netplan/cloud-init) verwaltet → NM meldet „keine Verbindung“ → GIO/GNOME Software glaubt „offline“ und zeigt nichts.
Lösung: `GIO_USE_NETWORK_MONITOR=netlink` (offizielle GIO-Umgebungsvariable) in `/etc/environment.d/` bzw.
`/etc/environment`. Prüfen: wirkt nach Neuanmeldung; Flathub-Quelle ohne Passwort (polkit, Gruppe sudo).

### Agenten-Apps
- Quelle: `agent-apps/` im Repo (`agent-apps.yaml`, `build_agent_apps.py`, `agenten-apps.desktop`), ins Paket über
  `force-include` (wheel) und `datas` (PyInstaller-Spec) wie `kurspakete/`.
- `hermes_snippet()`: Format der Hermes-Doku (`mcp_servers:` → `command`/`args`), zusätzlich der Befehl
  `hermes mcp add <id> --command … --args …` (im Video so genutzt) – Pfade absolut über `--home`.
- Online: Job im Pages-Workflow baut `agenten-apps/index.html` ohne `--home`; eigener Auslöser bei Änderung der YAML
  auf `main`.
- Einträge: jeder in frischem Debian-13-Agent-PC testen; erst dann `geprueft_am`; Nicht-Funktionierendes
  auskommentieren.

### Handbuch / Release
- `docs/handbuch/benutzer.md`: Abschnitte „Software-Center“, „n8n“ (inkl. Zusammenarbeit mit Hermes: Webhooks,
  Instance-level MCP `http://localhost:5678/mcp-server/http` mit Bearer-Token → Hermes `mcp_servers` mit `url` +
  `headers`), „Agenten-Apps“ – je mit Screenshot.
- CHANGELOG: alle drei Funktionen, n8n mit Lizenzhinweis.
- Hosts: Linux selbst; Windows und Mac testet Bony.

## Stand

- [x] Plan (22.10.)
- [x] `agent-apps/` (Liste + Craft-Apps, versionsfreie Downloads über `releases/latest/download` + SHA256SUMS,
      `uname -m`), Build-Skript (Pflichtfelder inkl. meta/vorinstalliert, `hermes mcp add …` + config.yaml,
      `--installiert`), Tests `tests/test_agenten_apps.py`
- [x] AppSpecs `software-center`, `n8n` (`n8n.py`), `agenten-apps` (`agenten_apps.py`) – Paket/Spec-Einbindung,
      Vorlagen-Bereinigung (frisch: Volume weg; Export: n8n entfernt, `redistributable=False`)
- [x] Dialoge: n8n-Abschnitt mit Lizenz + RAM-Warnung (zählt Mission Control mit), Häkchen-Zeile als FlowLayout;
      „Programme hinzufügen“ mit Lizenzhinweis + Warnung
- [x] Pages-Workflow (`apt-repo.yml`): baut `site/agenten-apps/`, Auslöser `push` auf `agent-apps/**`
- [x] Handbuch-Text (Software-Center, n8n inkl. Hermes, Agenten-Apps) + CHANGELOG
- [x] Echter Test: neuer Agent-PC `aa-test` (Linux-Host, 22.10.) – n8n-Dienst läuft, Liste mit 11 Apps gebaut;
      Platte hat den Stromausfall am 22.10. ohne Fehler überstanden
- [x] Alle Listeneinträge im Agent-PC getestet, Hermes-MCP geprüft, `geprueft_am: 2026-10-22`; `mcp-fetch`
      auskommentiert (bricht mit installiertem Node.js ab)
- [x] Screenshots fürs Handbuch: `bilder/software-center.png`, `bilder/n8n.png`, `bilder/agenten-apps.png`
- [x] Version 0.24.0, pytest (beide Editionen) und ruff grün (22.10.)
- [x] Release v0.24.0 (22.10.); Paketquelle und Online-Liste veröffentlicht; Kurspaket Hermes 1.0.1 im Katalog
- [ ] Windows/Mac-Test durch Bony
