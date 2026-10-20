# Bony's Agents – Gesamtüberblick von der Idee bis heute

Stand: 18.10.2026 · Bony's Agents 0.22.1 · Bony's VPN 1.0.1 · Mission Control 0.1.0

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
| **Bony-Netz-Zentrale** | Server `zentrale.bony23.de` (Headscale/Tailscale, LiveKit) für Kurse über das Internet | nicht in diesen Repos |

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
- Umfang: ca. 29.000 Zeilen Code, 10.000 Zeilen Tests, CI auf Linux/macOS/Windows.

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
| **Kurspaket** (geplant) | INHALT eines Kurses (Ablaufplan, Handout, Lektionen, Prüfungen, Quiz) als `.bonyspaket` |
| **Instanz** | Anmeldung beim Bony-Netz-Server (ohne E-Mail) |

---

## 7. Hermes Agent – wichtige Fakten

- Installation: offizieller Installer (`curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash`) als Benutzer `agent`.
- Einrichten: `hermes setup` → **bei der Anbieter-Wahl oberster Punkt „Nous“ → dort ein Free-Modell** (von Bony
  getestet). Alternative: OpenRouter-Modelle mit `:free` (API-Schlüssel, Tageslimit). Die Unterlagen nennen bisher
  OpenRouter – **vereinheitlichen** (Nous Standard, OpenRouter Alternative).
- Starten: `hermes --tui` oder `hermes`; Prüfen: `hermes doctor`; Modell wechseln: `hermes model` bzw. `/model`;
  Werkzeuge: `/tools`; Hilfe: `/help`. Modell braucht mindestens 64K Kontext.
- Telegram: Token bei @BotFather, `hermes gateway setup` oder `~/.hermes/.env` (`TELEGRAM_BOT_TOKEN`,
  `TELEGRAM_ALLOWED_USERS` = nur eigene ID), dann `hermes gateway restart`.
- Doku: https://hermes-agent.nousresearch.com/docs – Befehle immer dort prüfen, nicht raten.

---

## 8. Aktuelle Einschätzung (18.10.2026)

**Stärken:** echte Nische (Klassenzimmer für KI-Agenten in sicheren Agent-PCs), sehr sorgfältig getestet,
gehärtet und dokumentiert, Lizenzen nachgezogen, professionelle Handbuch-Erzeugung.

**Risiken und offene Punkte:**

1. **Neue Teile ungeprüft:** Die Durchsicht lief über 0.19.0. Bony-Netz, Kursraum und Hilfe online (0.21/0.22)
   haben die meiste Angriffsfläche und sind unter Windows/macOS kaum getestet.
2. **Betrieb eines Dienstes:** `zentrale.bony23.de` verarbeitet Instanzen, Netzadressen, Video/Ton → Erreichbarkeit,
   Kosten, Missbrauch (Instanzen ohne E-Mail); rechtlich wahrscheinlich Impressum, Datenschutzerklärung, ggf.
   Absprachen mit Kursleitern (fachkundig prüfen lassen, keine Rechtsberatung).
3. **Umfang/Tempo:** drei Programme, ein Server, Video-Infrastruktur, eine Person. „Sollte vor 1.0“-Liste aus
   `docs/review-1.0.md` großteils offen.
4. **Begriff „Kurs“** ist für Live-Veranstaltungen vergeben → Inhalte heißen „Kurspaket“.
5. **Beispielkurs existiert** (`docs/handbuch/beispielkurs.md` + Handout); ein zweiter Entwurf
   (`kurse/01-ki-agenten-fuer-einsteiger/kurs.md`, falls abgelegt) dient nur als Ideenquelle.

---

## 9. Fahrplan

- [ ] **Auftrag A:** Zweite Durchsicht (Bony-Netz, Kursraum, Hilfe online, Server) → `docs/review-1.0-teil2.md`
- [ ] „Muss“-Punkte aus Teil 2 umsetzen
- [ ] Echter Probekurs über das Internet mit 2–3 Bekannten, mindestens ein Windows-Rechner
- [ ] Rechtliches zum Server klären
- [ ] Kostenloses Modell in allen Unterlagen vereinheitlichen
- [ ] **Version 1.0** veröffentlichen, Video drehen, Rückmeldungen über GitHub-Issues sammeln
- [ ] **Auftrag B:** Kurspakete (erst nach 1.0)
- [ ] Später: Kursleiter-Dashboard (Teilnehmer-Übersicht, alle zurücksetzen, Dateien verteilen)

---

## 10. Auftrag A – Zweite Durchsicht (jetzt)

Vorher `/clear`, mit Opus, im BonysAgents-Ordner.

```text
Zweite Durchsicht vor Version 1.0 – NUR prüfen und berichten, NICHTS am Code, an Paketen, Releases, Servern oder der Git-Historie ändern. Einzige Ausnahme: du schreibst den Bericht nach docs/review-1.0-teil2.md und committest nur diese Datei (nach meinem OK).

Hintergrund: docs/review-1.0.md hat 0.19.0 geprüft; alle „Muss“-Punkte sind seit 0.20.0 umgesetzt. Danach kamen dazu: Bony-Netz (0.21.0, Headscale/Tailscale, Zentrale zentrale.bony23.de), Kurse über das Bony-Netz, Kursraum mit LiveKit/Qt WebEngine (0.21.0) und die Hilfe-Funktion über das Bony-Netz mit x11vnc (0.22.0). Genau diese Teile sind noch nicht geprüft. Lies zuerst docs/dev/projekt-gesamtueberblick.md, docs/review-1.0.md, docs/bony-netz.md, docs/editionen.md, CHANGELOG.md und die Handbücher in docs/handbuch/.

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
9) Server: Der Code der Zentrale liegt nicht in diesem Repo. Frag mich, ob und wo ich ihn lokal habe (z. B. bony-netz-paket oder ein eigenes Repo). Falls ja: dieselbe Prüfung in Kurzform (Authentisierung, Headscale-ACLs, LiveKit-Tokens, Rate-Limits, Logs mit personenbezogenen Daten). Falls nein: aufschreiben, was ich auf dem Server selbst prüfen muss.
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

## 11. Auftrag B – Kurspakete (erst nach 1.0)

Vorher `/clear`, mit Opus, im BonysAgents-Ordner.

```text
Neue Funktion nach Version 1.0: KURSPAKETE – fertige, speicher- und ladbare Kursinhalte, die ein Kursleiter erstellt und wiederverwendet (Anfänger bis Experte). Lies zuerst docs/dev/projekt-gesamtueberblick.md.

WICHTIG – Begriffe: In Bony's Agents ist ein „Kurs“ bereits eine LIVE-VERANSTALTUNG (Bony-Netz-Kurs mit Kurscode, Teilnehmern, Kursraum, starten/pausieren/beenden; Logik in kurse.py, gui/kurse_dialog.py, trainer/gui/kurse_leiten.py) bzw. eine „Schulung im eigenen Netz“ (Freigabe, Vorführen, Hilfe-Schalter). Das Neue heißt durchgängig „Kurspaket“ (Datei .bonyspaket) – im Code, in der Oberfläche, in den Handbüchern. Ein Kurspaket ist der INHALT, ein Kurs die DURCHFÜHRUNG: Beim Anlegen eines Kurses (Bony-Netz) oder einer Schulung im eigenen Netz kann der Kursleiter ein Kurspaket auswählen; ohne Kurspaket funktioniert alles wie bisher. Prüfe alle bestehenden Texte, damit die beiden Begriffe nie verwechselt werden, und ergänze das Glossar im Benutzerhandbuch.

Vorhandenes nutzen, nicht doppelt bauen:
- Der erste Beispielkurs existiert bereits: docs/handbuch/beispielkurs.md (Ablaufplan Kursleitung, „Einführung in Hermes Agent“, 2 Stunden, 8 Blöcke, Übungen mit Lösungen) und docs/handbuch/beispielkurs-handout.md (Handout). Er wird das ERSTE Kurspaket. Die PDF-Erzeugung (docs/handbuch/erstellen.sh, Pandoc/Typst, Kästen, Felder) für Ablaufplan und Handout weiterverwenden – Kurspakete sollen ihr Handout und ihren Ablaufplan genauso als PDF erzeugen können.
- Falls kurse/01-ki-agenten-fuer-einsteiger/kurs.md existiert: ein zusätzlicher Entwurf von mir. Nicht als zweiten Kurs anlegen, sondern prüfen, welche Ideen daraus (z. B. Quizfragen, Prüfaufgaben je Lektion, Lektion „Zurücksetzen und Vorlage“) den vorhandenen Beispielkurs sinnvoll ergänzen; mir die Vorschläge zeigen, nach meinem OK einarbeiten, danach die Datei entfernen.
- Kostenloses Modell: In den Unterlagen steht bisher OpenRouter (:free, API-Schlüssel). Mein getesteter Weg ist: `hermes setup` → bei der Anbieter-Wahl oberster Punkt „Nous“ → dort ein Free-Modell. Prüfe in der aktuellen Hermes-Doku (https://hermes-agent.nousresearch.com/docs), schreib Nous als Standardweg und OpenRouter als Alternative – einheitlich in Benutzerhandbuch, Beispielkurs, Handout und Kurspaketen.
- Bestehende Bausteine wiederverwenden: Vorlagen und .bonys (statt neuer Festplatten-Abbilder), Geheimnis-/Frisch-Prüfung, Editionstrennung (trainer/), Kursraum, Hilfe, signierte Downloads.

Arbeite in Sitzungen. Lege zuerst docs/dev/plan-kurspakete.md an (Begriffe, Format, Sitzungsplan, Sicherheitsregeln, „Stand“ mit Checkliste) – intern, nicht im README verlinkt. Committe nach jedem Teil. Reicht eine Sitzung nicht: Stand festhalten, ich starte neu mit „Mach weiter laut docs/dev/plan-kurspakete.md“. Release erst nach meinem Test und OK.

SITZUNG 1 – Format, Bibliothek, Anzeige
1) Format .bonyspaket (Ordner bzw. ZIP, textbasiert, mit Git versionierbar): paket.json (Name, Beschreibung, Stufe Anfänger/Fortgeschritten/Experte, Sprache, Autor, Lizenz – Standard CC BY-SA 4.0 –, Version, Mindestversion Bony's Agents, Dauer, Teilnehmerzahl), rezept bzw. Verweis auf eine Vorlage/.bonys, ablaufplan.md (Kursleitung, Blöcke mit Zeiten, Notizen), handout.md (Teilnehmer), optional lektionen/ mit anleitung.md, pruefung/ (Prüfskripte), quiz.json, bilder/. Schema in docs/kurspaket-format.md, Validierung mit deutschen Fehlermeldungen, Entpack-Schutz (kein Pfad-Ausbruch, Größenlimit).
2) Bibliothek „Kurspakete“ (beide Editionen): lokal importieren/löschen/aktualisieren; optional Download aus einem öffentlichen GitHub-Repo (frag mich nach dem Repo), signiert bzw. mit Prüfsumme.
3) Teilnehmer-Ansicht: Anleitung der aktuellen Lektion neben dem Agent-PC (Fenster in Bony's Agents oder im Kursraum – entscheide und begründe kurz), Zurück/Weiter, Fortschritt. Selbstlern-Modus: ein Kurspaket auch ohne Kurs allein durcharbeiten (beide Editionen).

SITZUNG 2 – Startzustände, Prüfaufgaben, Quiz
1) Startzustand je Lektion (qcow2-Schnappschuss oder Startskript), „Lektion zurücksetzen“, „Zu Lektion X springen“, Warnung vor Verlust eigener Dateien.
2) Prüfaufgaben laufen NUR im Agent-PC (Gast-Agent), Ergebnis nur „geschafft/noch nicht“ mit Hinweistext, Zeitlimit. Fremde Pakete: Hinweis mit Liste der Skripte vor dem ersten Start.
3) Quiz am Lektionsende, Ergebnis nur lokal.

SITZUNG 3 – Editor (nur Kursleiter-Edition)
1) Kurspaket anlegen/bearbeiten: Blöcke/Lektionen, Markdown mit Vorschau, Bilder (Screenshot des Agent-PCs per Knopf), Notizen, Zeiten, Quiz, Prüfskripte mit Vorlagen (Datei existiert, Dienst läuft, Hermes eingerichtet – ohne Schlüssel auszulesen).
2) Startzustand aus aktuellem Agent-PC übernehmen, Speichern/Laden/Duplizieren/Version erhöhen.
3) Vor dem Export Geheimnis-Prüfung (wie beim .bonys-Export), Export blockieren bis bereinigt.
4) Ablaufplan und Handout als PDF (vorhandene Handbuch-Vorlage).
5) „Kurspaket prüfen“: spielt Lektionen in einem Test-Agent-PC durch und meldet Veraltetes.

SITZUNG 4 – Anbindung an Kurse, Beispielpakete, Abschluss
1) Beim Anlegen eines Bony-Netz-Kurses und bei der Schulung im eigenen Netz ein Kurspaket wählen; Teilnehmer bekommen es automatisch. Kursansicht zeigt pro Teilnehmer aktuelle Lektion und „geschafft/noch nicht“ (keine Inhalte, nur solange der Kurs läuft; Datenschutz-Abschnitt ergänzen).
2) Beispielpakete:
   - Anfänger: „Einführung in Hermes Agent“ – VOLLSTÄNDIG aus docs/handbuch/beispielkurs.md + beispielkurs-handout.md (Inhalte nicht kürzen, ergänzt um die freigegebenen Ideen aus meinem Entwurf).
   - Als Entwurf (Gliederung + Lernziele, gleicher Aufbau): „Hermes über Telegram steuern“ (Anfänger), „Aufgaben automatisieren“ und „Sicherheit: Was darf ein Agent? Prompt-Injection erkennen“ (Fortgeschritten), „Eigene Werkzeuge und Skills, Mission Control“ und „Lokale Modelle, VPN, mehrere Agenten“ (Experte). Hermes-Befehle in der aktuellen Doku prüfen, nicht raten. Keine API-Keys in Paketen.
3) Editionstrennung: Editor und Kurs-Zuordnung nur Kursleiter; Bibliothek, Anzeige, Selbstlern-Modus, Prüfungen, Quiz in beiden. docs/editionen.md aktualisieren.
4) Handbücher: Benutzerhandbuch (Kurspakete durcharbeiten, Selbstlernen), Kursleiter-Handbuch (Kurspakete erstellen und einem Kurs zuordnen), Glossar; Bildschirmfotos über den Vorführmodus (erstellen.sh) inkl. Texterkennungs-Prüfung.
5) Tests: Format-Validierung, Entpack-Schutz, Geheimnis-Prüfung, Prüfskripte nur im Agent-PC, Startzustände, Editionstrennung, Zuordnung zu Kursen.
6) Echter Test: Beispielpaket im Selbstlern-Modus (Anwender-Edition) durchspielen; Kurs mit Kurspaket über das Bony-Netz mit einem zweiten Rechner; Lektion zurücksetzen; Prüfungen grün/rot; Screenshots.
7) pytest und ruff für beide Editionen, Version erhöhen (Minor), .deb bauen, installieren (vorher fragen), committen; Zusammenfassung, was ich selbst testen soll. Release nach meinem OK.

Regeln: Frag mich, bevor du etwas mit sudo ausführst. Gib niemals Passwörter, Tokens oder Schlüssel im Klartext aus. Programme nur aus offiziellen Quellen. Keine Zugangsdaten in Kurspaketen.
```

---

## 12. Kurzbefehle für Claude Code

- Weitermachen nach Abbruch: `Mach weiter laut docs/dev/plan-kurspakete.md (Abschnitt „Stand“) mit dem nächsten offenen Teil.`
- Release nach eigenem Test: `Ich habe getestet, alles funktioniert. Bitte veröffentlichen: Tests und ruff, gitleaks, CHANGELOG/README prüfen, Version erhöhen, .deb bauen und installieren (vorher fragen), committen, Tag, Release, CI-Ergebnisse zeigen.`
- Neue Mission-Control-Version übernehmen: `Mission Control hat ein neues Release vX.Y.Z. Schnittstelle prüfen (CHANGELOG, docs/installation-agent-pc.md, BREAKING), feste Version in Bony's Agents anheben, neuer und bestehender Agent-PC testen, committen, Release nach meinem OK.`
