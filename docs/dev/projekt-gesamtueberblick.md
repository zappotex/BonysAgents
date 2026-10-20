# Bony's Agents – Gesamtüberblick von der Idee bis heute

Stand: 20.10.2026 · Bony's Agents 0.23.0 · Bony's VPN 1.0.1 · Mission Control 0.1.0 · Bony-Netz 0.2.0

Dieses Dokument fasst das ganze Projekt für Claude Code (und andere KI-Helfer) zusammen: Idee, Entscheidungen,
feste Regeln, aktueller Stand, offene Punkte und die nächsten Aufträge. **Vor jeder größeren Aufgabe lesen.**

Empfohlener Ablageort (intern, nicht im README verlinken): `docs/dev/projekt-gesamtueberblick.md`

---

## 1. Die Idee

> Du hast schon viel von KI-Agenten gehört. Bony's Agents bietet eine Möglichkeit, ohne VPS oder große
> Vorkenntnisse auf dem eigenen PC unter Linux, Windows und Mac einen virtuellen PC zu erstellen und darauf
> KI-Agenten zu installieren – so, dass das eigene System sicher bleibt.

- Ein **Agent-PC** ist eine QEMU-VM mit Debian 13, Desktop, Brave, Telegram und Hermes Agent – vollständig vom
  eigenen Rechner getrennt.
- Alles ohne Terminal-Kenntnisse: Installer (.deb, Setup.exe, .dmg), die App installiert QEMU selbst, legt den
  Benutzer `agent` an, richtet alles ein.
- Grundausstattung komplett **Open Source** (QEMU, Debian, Brave, Telegram, Hermes Agent). Nicht Open Source und
  nur optional: Claude Code, Obsidian.
- Hermes startet mit einem **kostenlosen Modell**; jederzeit umstellbar (ChatGPT, andere Anbieter, lokale Modelle).
- Ausgebaut zu einem **Klassenzimmer für KI-Agenten**: Vorlagen verteilen, vorführen, helfen, Kurse über das
  Internet mit Kursraum.
- YouTube-Kanal: https://www.youtube.com/@BonysAgents

---

## 2. Die Projekte

| Projekt | Zweck | Repo |
|---|---|---|
| **Bony's Agents** | Hauptprogramm (GUI + CLI), zwei Editionen: Anwender und Kursleiter | https://github.com/zappotex/BonysAgents |
| **Bony's VPN** | eigenes WireGuard-Tool für Linux (Vorbild: wireguird, aber selbst entwickelt), im Agent-PC und auf dem Linux-Rechner, mit Kill-Switch | https://github.com/zappotex/bonys-vpn |
| **Mission Control** | Steuerzentrale für Agenten im Browser, läuft mit Docker nur im Agent-PC (wird mit ChatGPT/Hermes weiterentwickelt, Schnittstelle siehe dort `AGENTS.md` / `docs/installation-agent-pc.md`) | https://github.com/zappotex/bonys-agents-mission-control |
| **Bony-Netz** | Zentrale `zentrale.bony23.de` (Headscale/Tailscale, LiveKit, Kurse, Kurspakete zum Kurs, Fortschritt) für Kurse über das Internet; dazu der Baustein `bony_netz`, der in Bony's Agents und Bony's VPN dateigleich steckt (Quelle: `baustein/` im Repo) | https://github.com/zappotex/bonys-netz |
| **Kurspakete** | öffentlicher Katalog für „Aus dem Internet …“ (`index.json` + `pakete/*.bonyspaket`, signiert), nach jedem Release mit geänderten Paketen von Hand befüllt (`docs/RELEASE.md`) | https://github.com/zappotex/bonys-agents-kurspakete |

Lokaler Projektordner: `/media/zappotex/bonysagent/BonysAgents/`

---

## 3. Feste Regeln (gelten für jede Aufgabe)

1. **Frag mich, bevor du etwas mit sudo ausführst** oder Programme installierst.
2. **Niemals** Passwörter, Tokens, API-Keys, VPN-Schlüssel, Eintrittskarten im Klartext ausgeben, ins Repo,
   in Logs, Tests, Vorlagen oder Pakete schreiben. Vor Commits gitleaks.
3. **Keine Zugangsdaten in Agent-PCs vorkonfigurieren.** Jeder Nutzer meldet sich mit seinem eigenen Konto an.
4. **Programme immer von der offiziellen Quelle** (Debian-Quellen, offizielle GitHub-Releases, winget, Flathub,
   Herstellerseite) – mit Prüfsumme/Signatur, nichts Fremdes ins Repo kopieren.
5. **Nicht weitergebbare Programme** (Claude Code, Obsidian) nie mitliefern; beim Empfänger frisch installieren.
   NoMachine (`Software/`) nie weitergeben.
6. Arbeitsweise: vor jeder Aufgabe `/clear`; für große Aufgaben Opus; große Aufträge in Sitzungen mit
   Plan-Datei und Abschnitt „Stand“; nach jedem Teil committen; **Release erst nach Bonys Test und OK**.
7. Interne Pläne nicht öffentlich verlinken (siehe Durchsicht D-04).
8. Begriffe nicht verwechseln (siehe Abschnitt 6).

---

## 4. Technik in Kürze

- Python 3.10+, PySide6 (Qt), argparse-CLI; PyInstaller; Lizenz **GPL-3.0-or-later** mit CLA.
- QEMU mit KVM/HVF/WHPX (TCG-Rückfall); Steuerkanäle seit 0.20.0 über Unix-Sockets (Linux/macOS) bzw. TLS (Windows).
- Debian 13 Cloud-Image (SHA512), cloud-init NoCloud, Einrichtung als systemd-Dienst mit wiederaufnehmbaren
  Schritten, „fertig mit Fehlern“ statt still „fertig“.
- Desktops: Cinnamon (Standard), Xfce, KDE Plasma, GNOME, MATE, LXQt.
- Apps: Brave, Telegram, Hermes (Standard); OpenClaw, Claude Code, Obsidian, Bony's VPN, Mission Control (+Docker) optional,
  auch nachträglich („Programme hinzufügen …“).
- Pakete: .deb (amd64/arm64), Setup.exe, .dmg (Apple-Chip/Intel), APT-Quelle auf GitHub Pages, minisign-signierte
  Updates, Auto-Update in der eigenen Edition.
- Kurspakete: `.bonyspaket` (ZIP, textbasiert), Format in `docs/kurspaket-format.md`; mitgelieferte Pakete in
  `kurspakete/`, beim Release mit dem Release-Schlüssel signiert und als Assets angehängt.
- Umfang (20.10.2026): ca. 35.000 Zeilen Python in `src/` (ca. 29.700 ohne Leer- und Kommentarzeilen, davon ca.
  6.200 Kursleiter-Teil `trainer/`), ca. 12.400 Zeilen Tests, CI auf Linux/macOS/Windows.

---

## 5. Was bisher gebaut wurde (Chronik)

| Bereich | Inhalt |
|---|---|
| Grundlage | Agent-PC erstellen/starten/stoppen/löschen/verschieben, freier Speicherort (externe SSD), Bibliotheken auf allen Laufwerken, Festplatte 32 GB–1 TB, QEMU-Fenster 800×600 mit dynamischer Auflösung, skaliertes Hintergrundbild, Fernzugriff (xrdp + SPICE + Remmina) nur bei Bedarf |
| Behobene Probleme | Zombie-QEMU, libmount/LD_LIBRARY_PATH (`clean_env`), Einrichtung fortsetzbar, PXE-Verzögerung (bootindex/romfile), skalierbares Programmfenster, macOS-Start (Gatekeeper/Architektur/Homebrew), unlesbare Tooltips (0.22.1) |
| Vorlagen | frischer Agent-PC ohne private Daten oder vollständiger Klon |
| Desktop-Auswahl | sechs Desktops, X11-Sitzungen für xrdp/xrandr |
| VPN | Bony's VPN als eigenes Repo (Root-Helfer über polkit, Kill-Switch, Tray), im Agent-PC und auf Linux-Hosts; Windows/macOS: offizielle WireGuard-App |
| Obsidian, Mission Control | optionale Apps; Mission Control mit Docker aus offizieller Quelle, fester Release-Tag |
| Schulung im eigenen Netz | `.bonys`-Export/Import mit Frisch-Prüfung, Freigabe im Netzwerk (Code, QR, Fingerabdruck), Vorführen im Browser (Nur-Ansehen serverseitig erzwungen), Hilfe-Modus mit zwei Zustimmungen |
| Editionen (0.19) | „Bony's Agents“ und „Bony's Agents Kursleiter“ aus einem Quellcode; Kursleiter-Teile fehlen in der Anwender-Version ganz |
| Durchsicht vor 1.0 | `docs/review-1.0.md` über 0.19.0; alle „Muss“-Punkte in 0.20.0 umgesetzt (u. a. kritischer VM-Ausbruch über QMP, präparierte qcow2, APT-Signaturkette, Lizenzen, deutsche Qt-Texte, Fehlerprotokoll) |
| Bony-Netz (0.21) | Agent-PCs über Headscale/Tailscale ins Netz der Zentrale, standardmäßig aus |
| Kurse + Kursraum (0.21) | Kurse mit Kurscode über das Bony-Netz; Kursraum mit Bildschirm, Ton, Kamera, Chat (LiveKit, Qt WebEngine, ca. +290 MB) |
| Hilfe online (0.22) | Hilfe über das Bony-Netz mit x11vnc, Einmal-Passwort, nur nach Zustimmung |
| Handbücher (0.22.1) | Benutzer-, Kursleiter-Handbuch, Beispielkurs „Einführung in Hermes Agent“ + Handout als PDF; Bildschirmfotos automatisch im Vorführmodus mit OCR-Datenschutzprüfung |
| Kurspakete (0.23, vorgezogen vor 1.0) | Bibliothek in beiden Editionen (Import, Drag & Drop, „Aus dem Internet …“), Anleitung neben dem Agent-PC, Selbstlern-Modus, Startzustände je Lektion (qcow2-Schnappschuss/Startskript), Prüfaufgaben nur im Agent-PC („geschafft / noch nicht“), Quiz nur lokal, signierte „Geprüfte Kurspakete“; Editor + „Kurspaket prüfen“ + PDF nur Kursleiter; Kurspaket zum Bony-Netz-Kurs (Upload zur Zentrale) und zur Schulung im eigenen Netz, Kursansicht mit Lektion + Prüfung je Teilnehmer nur solange der Kurs läuft; „Einführung in Hermes Agent“ 1.0.0 fertig + 5 Entwürfe; Nous als Standard-Modell in allen Unterlagen. Plan und Entscheidungen: `docs/dev/plan-kurspakete.md` |

---

## 6. Begriffe (nicht verwechseln!)

| Begriff | Bedeutung |
|---|---|
| **Agent-PC** | die virtuelle Maschine des Nutzers |
| **Vorlage** | gespeicherter Agent-PC als Grundlage für neue (frisch oder Klon) |
| **.bonys** | Vorlage als eine Datei zum Weitergeben |
| **Schulung im eigenen Netz** | Freigabe/Vorführen/Hilfe-Schalter ohne Server, mit Freigabe-Code (z. B. `4711-BONY`) |
| **Kurs** | LIVE-Veranstaltung im Bony-Netz mit Kurscode (z. B. `K7QX-M3PA`), Teilnehmern, Kursraum |
| **Kursraum** | Video-/Ton-/Chat-Fenster während eines Kurses |
| **Kurspaket** | INHALT eines Kurses (Ablaufplan, Handout, Lektionen, Prüfungen, Quiz) als `.bonyspaket`; ein Kurs ist die DURCHFÜHRUNG |
| **Prüfaufgabe** | kleines Skript im Agent-PC, Ergebnis nur „geschafft“ oder „noch nicht“ |
| **Geprüftes Kurspaket** | mit dem Release-Schlüssel signiert (mitgeliefert bzw. aus dem Katalog) |
| **Instanz** | Anmeldung beim Bony-Netz-Server (ohne E-Mail) |

---

## 7. Hermes Agent – wichtige Fakten

- Installation: offizieller Installer (`curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash`) als Benutzer `agent`.
- Einrichten: `hermes setup` → **bei der Anbieter-Wahl oberster Punkt „Nous“ → dort ein Free-Modell** (von Bony
  getestet). Alternative: OpenRouter-Modelle mit `:free` (API-Schlüssel, Tageslimit). Seit 0.23.0 einheitlich in
  Benutzerhandbuch, Beispielkurs, Handout und Kurspaketen (Nous Standard, OpenRouter Alternative).
- Starten: `hermes --tui` oder `hermes`; Prüfen: `hermes doctor`; Modell wechseln: `hermes model` bzw. `/model`;
  Werkzeuge: `/tools`; Hilfe: `/help`. Modell braucht mindestens 64K Kontext.
- Telegram: Token bei @BotFather, `hermes gateway setup` oder `~/.hermes/.env` (`TELEGRAM_BOT_TOKEN`,
  `TELEGRAM_ALLOWED_USERS` = nur eigene ID), dann `hermes gateway restart`.
- Doku: https://hermes-agent.nousresearch.com/docs – Befehle immer dort prüfen, nicht raten.

---

## 8. Aktuelle Einschätzung (20.10.2026)

**Stärken:** echte Nische (Klassenzimmer für KI-Agenten in sicheren Agent-PCs), sehr sorgfältig getestet,
gehärtet und dokumentiert, Lizenzen nachgezogen, professionelle Handbuch-Erzeugung, jetzt mit fertigen
Kursinhalten (Kurspakete).

**Risiken und offene Punkte:**

1. **Neue Teile ungeprüft:** Die Durchsicht lief über 0.19.0. Bony-Netz, Kursraum und Hilfe online (0.21/0.22)
   und Kurspakete (0.23: Skripte im Agent-PC, Upload zur Zentrale, Fortschritt) haben die meiste Angriffsfläche
   und sind unter Windows/macOS kaum getestet. Echter Test von 0.23.0 durch Bony läuft (Release auf Wunsch vor
   dem Test); 3-Rechner-Test des Bony-Netzes steht aus.
2. **Betrieb eines Dienstes:** `zentrale.bony23.de` verarbeitet Instanzen, Netzadressen, Video/Ton → Erreichbarkeit,
   Kosten, Missbrauch (Instanzen ohne E-Mail); rechtlich wahrscheinlich Impressum, Datenschutzerklärung, ggf.
   Absprachen mit Kursleitern (fachkundig prüfen lassen, keine Rechtsberatung).
3. **Umfang/Tempo:** drei Programme, ein Server, Video-Infrastruktur, eine Person. „Sollte vor 1.0“-Liste aus
   `docs/review-1.0.md` großteils offen.
4. **Begriff „Kurs“** ist für Live-Veranstaltungen vergeben → Inhalte heißen „Kurspaket“ (umgesetzt, Glossar).
5. **Beispielkurs ist jetzt ein Kurspaket:** `kurspakete/einfuehrung-hermes-agent/` (Ablaufplan + Handout dort,
   die Handbuch-PDFs werden daraus gebaut); `docs/handbuch/beispielkurs*.md` und `kurse/` gibt es nicht mehr.
   Die fünf weiteren Pakete sind Entwürfe (Gliederung + Lernziele) und müssen noch ausgearbeitet werden.

---

## 9. Fahrplan

- [ ] **Auftrag A:** Zweite Durchsicht (Bony-Netz, Kursraum, Hilfe online, Server) → `docs/review-1.0-teil2.md`
- [ ] „Muss“-Punkte aus Teil 2 umsetzen
- [ ] Echter Probekurs über das Internet mit 2–3 Bekannten, mindestens ein Windows-Rechner
- [ ] Rechtliches zum Server klären
- [x] Kostenloses Modell in allen Unterlagen vereinheitlichen (0.23.0)
- [x] **Auftrag B:** Kurspakete – vorgezogen und mit v0.23.0 veröffentlicht (19.10.2026), Pakete im Katalog-Repo
- [ ] Echter Test von 0.23.0 (Selbstlernen, Editor, Kurs mit Kurspaket über Bony-Netz und im eigenen Netz)
- [ ] Die fünf Entwurfs-Kurspakete ausarbeiten
- [ ] **Version 1.0** veröffentlichen, Video drehen, Rückmeldungen über GitHub-Issues sammeln
- [ ] Später: Kursleiter-Dashboard (Teilnehmer-Übersicht, alle zurücksetzen, Dateien verteilen)

---

## 10. Auftrag A – Zweite Durchsicht (jetzt)

Vorher `/clear`, mit Opus, im BonysAgents-Ordner.

```text
Zweite Durchsicht vor Version 1.0 – NUR prüfen und berichten, NICHTS am Code, an Paketen, Releases, Servern oder der Git-Historie ändern. Einzige Ausnahme: du schreibst den Bericht nach docs/review-1.0-teil2.md und committest nur diese Datei (nach meinem OK).

Hintergrund: docs/review-1.0.md hat 0.19.0 geprüft; alle „Muss“-Punkte sind seit 0.20.0 umgesetzt. Danach kamen dazu: Bony-Netz (0.21.0, Headscale/Tailscale, Zentrale zentrale.bony23.de), Kurse über das Bony-Netz, Kursraum mit LiveKit/Qt WebEngine (0.21.0) die Hilfe-Funktion über das Bony-Netz mit x11vnc (0.22.0) und die Kurspakete (0.23.0: Prüfskripte im Agent-PC, Startzustände, Signaturen, Upload zur Zentrale, Fortschritt der Teilnehmer). Genau diese Teile sind noch nicht geprüft. Lies zuerst docs/dev/projekt-gesamtueberblick.md, docs/review-1.0.md, docs/bony-netz.md, docs/editionen.md, docs/kurspaket-format.md, docs/dev/plan-kurspakete.md, CHANGELOG.md und die Handbücher in docs/handbuch/.

Arbeitsweise
- Teile die Prüfung in unabhängige Bereiche und lass sie, wenn möglich, von getrennten Unteragenten unvoreingenommen prüfen; danach jeden wichtigen Fund selbst am Code nachprüfen (Datei/Zeile oder konkreter Ablauf, Vermutungen als solche kennzeichnen) – Format und Schwere-Stufen wie in docs/review-1.0.md.
- Tests, ruff, gitleaks ausführen, wo das ohne sudo geht. Für alles mit sudo, Installationen oder Netzverbindungen zu echten Servern: vorher fragen. Die echte Bony-Netz-Anmeldung (~/.config/bonys-netz/) niemals lesen oder verändern.
- Gib niemals Passwörter, Tokens, Schlüssel oder Eintrittskarten im Klartext aus.

Zu prüfen
1) Bony-Netz (src/bony_netz/, src/bonys_agents/netz.py, cloudinit-Beitritt): Umgang mit Geräteschlüsseln (Lebensdauer, wo gespeichert, ob sie in Vorlagen/.bonys/Logs landen können), Seed-ISO-Inhalt, Beitrittsskript als root, Rechte von konto.json, Verhalten bei bösartiger oder kompromittierter Zentrale (was kann ein Server-Betreiber oder Angreifer mit Server-Zugriff auf den Rechnern der Nutzer und in ihren Agent-PCs anrichten?), Server-Wechsel, Löschen.
2) Isolation im Bony-Netz: Kann ein Teilnehmer andere Teilnehmer, den Kursleiter-Rechner oder fremde Agent-PCs erreichen? Was erzwingt die App, was nur die Zentrale (Headscale-Regeln)? Der eigene Rechner darf nie erreichbar sein – prüfen, wie zuverlässig das ist. Zusammenspiel mit Bony's VPN und dessen Kill-Switch.
3) Kursraum (kursraum.py, gui/kursraum_fenster.py, resources/kursraum/): eigenes Schema kursraum://, QWebChannel-Schnittstelle (was kann die Seite in Python auslösen?), Berechtigungen Kamera/Mikrofon/Bildschirm, Eintrittskarten (Gültigkeit, Weitergabe, Rollen „kursleiter“ – kann ein Teilnehmer sich als Kursleiter ausgeben?), Datennachrichten (Freigabe, Hand, Chat – Prüfung der Absender), Inhalte aus dem Netz als Text statt HTML, Sandbox-Abschaltung und AppArmor-Profil, livekit-client-Herkunft.
4) Hilfe über das Bony-Netz (hilfe.py, vncauth.py, gui/hilfe_ui.py, trainer/gui/hilfe_fenster.py, trainer/hilfe_betrachter.py): Zustimmungsablauf (auch bei manipulierten Nachrichten), x11vnc-Optionen, Einmal-Passwort (8 Zeichen, VNC-DES – reicht das hier?), Lauschadresse nur 100.x, Brücke auf 127.0.0.1 (geheimer Pfad, Origin, genau eine Verbindung), TigerVNC-Rückfall mit Passwortdatei, Beenden in allen Fällen.
5) Datenschutz und Recht für den Server-Betrieb (Hinweise, keine Rechtsberatung): Welche personenbezogenen Daten verarbeitet die Zentrale bzw. der LiveKit-Server (IP-Adressen, Anzeigenamen, Geräte-/Kursdaten, Video/Ton – Aufzeichnung?), was steht davon im Handbuch-Abschnitt „Datenschutz“, was fehlt? Liste, welche Pflichten als Betreiber in Deutschland wahrscheinlich anfallen (Impressum, Datenschutzerklärung, Auftragsverarbeitung, Löschfristen) – mit dem Hinweis, das fachkundig prüfen zu lassen.
6) Missbrauch und Betrieb: Instanzen ohne E-Mail (Massenanlage, Spam-Kurse), Kurscodes (Länge, Raten), Grenzen pro Instanz/Tag, was passiert bei Ausfall der Zentrale (App bleibt bedienbar?), Kosten-/Lastrisiken.
7) Wirkung auf die Anwender-Edition: Prüfe, dass das Bony-Netz standardmäßig aus ist und ohne Einschalten wirklich kein Kontakt zum Server entsteht (Code + Test); Kursleiter-Teile fehlen weiterhin in der Anwender-Version.
8) Plattformen: Was ist unter Windows und macOS (Kursraum, Bildschirm teilen, Hilfe, Tailscale) wirklich getestet? Konkrete Testanleitung für mich.
9) Server: Der Code der Zentrale liegt im Repo zappotex/bonys-netz (lokal ../bonys-netz, Ordner server/ und baustein/). Dieselbe Prüfung in Kurzform (Authentisierung, Headscale-ACLs, LiveKit-Tokens, Rate-Limits, Upload der Kurspakete und Fortschritt, Logs mit personenbezogenen Daten); aufschreiben, was ich auf dem laufenden Server selbst prüfen muss.
9a) Kurspakete (kurspaket.py, kurslauf.py, gui/kurspaket_*.py, trainer/kurspaket_editor.py, packaging/kurspakete.py): Entpack-Schutz, was ein fremdes oder präpariertes Paket im Agent-PC und auf dem Rechner anrichten kann, Signaturprüfung und „Geprüftes Kurspaket“, Upload/Download über Zentrale und Freigabe im eigenen Netz, Fortschrittsmeldungen (nur Lektion + geschafft, nur solange der Kurs läuft).
10) Stand der offenen „Sollte vor 1.0“-Punkte aus docs/review-1.0.md: kurz je Punkt erledigt/offen.

Bericht docs/review-1.0-teil2.md
- Zusammenfassung (10 Zeilen): Gesamteindruck der neuen Teile, größte Risiken, ist 0.22.x reif für 1.0 – wenn nein, warum.
- Tabelle aller Funde (Nr. | Bereich | Schwere | Beschreibung | Fundstelle | Vorschlag | Aufwand | Beleg).
- Listen „Muss vor 1.0“, „Sollte vor 1.0“, „Kann später“ – zusammengeführt mit den offenen Punkten aus Teil 1.
- Aufteilung der „Muss“-Punkte in Claude-Code-Sitzungen.
- Was ausdrücklich gut gelöst ist.
- Was du nicht prüfen konntest und wie ich es selbst prüfe (Probekurs über das Internet mit 2–3 Rechnern, davon einer Windows).

Zeig mir am Ende die Zusammenfassung und die „Muss vor 1.0“-Liste im Chat und frag, ob du den Bericht committen sollst.
```

---

## 11. Auftrag B – Kurspakete (erledigt)

Vorgezogen vor 1.0 und in vier Sitzungen umgesetzt, veröffentlicht mit **v0.23.0 am 19.10.2026**. Plan, Begriffe,
Entscheidungen und Checkliste: `docs/dev/plan-kurspakete.md` (Abschnitt „Stand“). Der ursprüngliche Auftragstext
steht in der Git-Historie dieser Datei (Commit 1b56a30).

Wichtige Entscheidungen in Kürze:
- Kurspaket = Inhalt, Kurs = Durchführung; ohne Kurspaket funktioniert alles wie bisher.
- Bony-Netz-Kurse: Kursleiter lädt das Paket zur Zentrale hoch (höchstens 25 MB), Teilnehmer holen es beim
  Beitritt; Schulung im eigenen Netz: Paket kommt direkt vom Kursleiter-Rechner.
- Kursleitung sieht je Teilnehmer nur Lektion und „geschafft / noch nicht“, nur solange der Kurs läuft.
- Mitgelieferte Pakete werden in der Release-Aktion signiert; der Katalog `zappotex/bonys-agents-kurspakete` wird
  danach von Hand befüllt (`docs/RELEASE.md`).

Offen: echter Test durch Bony, die fünf Entwürfe ausarbeiten.

---

## 12. Kurzbefehle für Claude Code

- Weitermachen nach Abbruch: `Mach weiter laut docs/dev/<plan-datei>.md (Abschnitt „Stand“) mit dem nächsten offenen Teil.`
- Release nach eigenem Test: `Ich habe getestet, alles funktioniert. Bitte veröffentlichen: Tests und ruff, gitleaks, CHANGELOG/README prüfen, Version erhöhen, .deb bauen und installieren (vorher fragen), committen, Tag, Release, CI-Ergebnisse zeigen; geänderte Kurspakete ins Repo bonys-agents-kurspakete.`
- Neue Mission-Control-Version übernehmen: `Mission Control hat ein neues Release vX.Y.Z. Schnittstelle prüfen (CHANGELOG, docs/installation-agent-pc.md, BREAKING), feste Version in Bony's Agents anheben, neuer und bestehender Agent-PC testen, committen, Release nach meinem OK.`
