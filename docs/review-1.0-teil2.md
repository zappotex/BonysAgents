# Durchsicht vor Version 1.0 – Teil 2

Stand: 28.10.2026, geprüft wurde Bony's Agents **0.28.0** (Commit `ba6f46c`) und die Zentrale „Bony-Netz“ im Repo
`bonys-netz` (Commit `98e8ecc`, Zentrale und Baustein 0.2.0; der Baustein in `src/bony_netz` ist dateigleich, per
`diff -r` geprüft). Es wurde **nur geprüft** – kein Code, kein Paket, kein Server, kein Release geändert.

Teil 1 (`docs/review-1.0.md`) hat 0.19.0 geprüft. Dieser Teil prüft, was danach dazukam: Bony-Netz (0.21.0),
Kurse über das Bony-Netz, Kursraum mit LiveKit/Qt WebEngine (0.21.0), Hilfe über das Bony-Netz mit x11vnc (0.22.0),
Kurspakete (0.23.0) und – zusätzlich – die App-Seite von Community-Katalog und Kursportal-Moderation (0.28.0). Der
Annahme-Server `kurse.bony23.de` hat eine eigene Prüfliste (`docs/dev/pruefliste-kursportal-server.md`) und
Datenschutz-Bestandsaufnahme (`docs/dev/datenschutz-kursportal.md`) und wird hier nur gestreift.

Vorgehen: fünf getrennte, unvoreingenommene Prüfungen (Bony-Netz/Isolation/Anwender-Edition, Kursraum, Hilfe,
Kurspakete/Katalog, Zentrale/Datenschutz/Missbrauch). Die wichtigsten Funde wurden danach selbst am Code
nachgeprüft (Spalte „Beleg“). Mehrfach gefundene Punkte sind zusammengeführt.

Ausgeführt:
- `QT_QPA_PLATFORM=offscreen PYTHONPATH=src build/venv/bin/python -m pytest -q` → **827 bestanden, 1 übersprungen**
  (7:40 Min.).
- `build/venv/bin/ruff check src tests` → sauber.
- `gitleaks git .` (149 Commits) und `gitleaks dir .` → 3 bzw. 5 Treffer, **alle Fehlalarme**: absichtlich
  gefälschte Schlüssel (`sk-or-…`) in `tests/test_kurspaket_portal.py:41,97` und `tests/test_kurspaket_editor.py:65`
  (Tests der Geheimnisprüfung) sowie deren `__pycache__`. Vorschlag: `.gitleaksignore` mit diesen Fingerabdrücken.
- Fokustests der Prüfer: Bony-Netz/Kurse/Hilfe/Baustein/Editionen 98 bestanden, 1 übersprungen; Kursraum + Hilfe
  54; Kurspakete + Moderation 231.
- Experimente nur im Scratchpad (präparierte ZIPs, Schein-Token gegen lokale Server, Qt-Label-Prüfung). Keine
  Verbindung zu echten Servern, `~/.config/bonys-netz/` nicht gelesen, nichts mit sudo.
- **Nicht gelaufen:** die Tests der Zentrale (`fastapi` fehlt in `build/venv`, nichts installiert).

**Umsetzung der „Muss“-Punkte (28.10.2026, nicht committet, nicht deployt):** I-01 (Zentrale: nur Port 5959; im
Agent-PC zusätzlich `x11vnc -allow` nur vom Kursleiter-Rechner – statt einer Firewall auf `tailscale0`, die die
gewollten Verbindungen zwischen den eigenen Agent-PCs gekappt hätte), K-01, I-02 (Bony's VPN `--shields-up`; unter
Windows/macOS Hinweis, in der offiziellen Tailscale-App eingehende Verbindungen abzuschalten), Z-01, K-02, I-03, H-01, KP-01, KP-02, B-01,
DR-01 bis DR-03 (Entwürfe und Hinweis im Bony-Netz-Dialog; die Rechtstexte selbst prüft die Fachperson, Bony stellt
sie bereit), Z-02, Z-03. Repos: `bonys-agents`, `bonys-netz` (Zentrale und Baustein 0.2.1), `bonys-vpn`.

---

## Zusammenfassung (10 Zeilen)

1. **Gesamteindruck:** Die neuen Teile sind sorgfältig gebaut – Geheimnisse nie im Log, Eingaben aus dem Netz nur als Text, strenger Entpack-Schutz, Signaturen für geprüfte Kurspakete, Bony-Netz standardmäßig aus und per Test belegt kontaktfrei.
2. **Größtes Risiko (hoch):** Während eines Kurses erreichen **alle Geräte des Kursleiters** – auch seine eigenen Agent-PCs mit KI-Agenten – **alle Ports** der Teilnehmer-Agent-PCs. Dort lauscht SSH mit Passwort, der Benutzer hat `sudo` ohne Passwort. Das hebelt „ohne deine Zustimmung sieht niemand deinen Agent-PC“ aus.
3. **Hoch:** Ein Teilnehmer kann sich im Kursraum **als Kursleiter ausgeben** (Rolle steht in selbst änderbaren LiveKit-Metadaten): Mikrofone aller abschalten, Hilfe-Anfragen mit falschem Namen an alle schicken – bei Zustimmung gehen IP und VNC-Passwort an ihn.
4. **Hoch:** Ist der eigene Rechner im Bony-Netz (beim Kursleiter nötig), erreichen ihn **alle eigenen Agent-PCs auf allen Ports** – Bony's VPN verbindet ohne `--shields-up`.
5. **Hoch (Datenschutz):** Die Zentrale schreibt die **echten IP-Adressen** jedes App-Aufrufs mit Zeit und Pfad ins Docker-Protokoll, ohne Begrenzung – die README sagt das Gegenteil.
6. **Mittel:** Eintrittskarten gelten 6 h und werden beim Entfernen/Pausieren nicht widerrufen; fällt Headscale beim Beenden aus, bleibt der Zugang offen; stürzt die App des Teilnehmers während einer Hilfe ab, bleibt die Fernsicht bis zu 30 min offen, ohne Hinweis.
7. **Mittel:** Die Zustimmung zu Kurspaket-Skripten lässt sich umgehen, wenn ein Kurs das Paket im Hintergrund ersetzt; der Dialog verschweigt, dass Skripte als root laufen.
8. **Recht:** Für Zentrale und Kursraum fehlen Datenschutzerklärung, Impressum und Löschfristen; neu ist die Frage nach einer **Meldepflicht bei der Bundesnetzagentur (TKG)** – fachkundig prüfen lassen.
9. **Reif für 1.0? Noch nicht.** Grund: die Isolation im Kurs (Punkte 2–4) und die fehlenden Rechtstexte der Zentrale. Fast alles ist klein und in ≈ 5 Sitzungen lösbar (siehe unten); die Zentrale braucht dafür ein Release 0.2.1 und einen Deploy durch Bony.
10. Aus Teil 1 sind alle „Muss“-Punkte erledigt; von den „Sollte“-Punkten ist bisher nur P-04 (Lock-Datei) umgesetzt (Tabelle unten).

---

## Tabelle aller Funde

Schwere: **kritisch / hoch / mittel / gering**. Aufwand: **klein / mittel / groß**.
Beleg: ✔ = selbst nachgeprüft bzw. per Experiment bestätigt, (C) = durch Code-Lesen des Prüfagenten belegt,
(V) = Vermutung/abgeleitet, nicht praktisch ausprobiert. Pfade ohne Präfix beziehen sich auf
`bonys-agents/src/bonys_agents/`, `bonys-netz/…` auf das Repo der Zentrale.

### Isolation im Bony-Netz (I)

| Nr. | Bereich | Schwere | Beschreibung | Fundstelle | Vorschlag | Aufwand | Beleg |
|---|---|---|---|---|---|---|---|
| I-01 | Kursleiter-Regel | **hoch** | Läuft ein Kurs, erlaubt die Netzregel **allen Geräten der Kursleiter-Instanz** (`<user>@`) **alle Ports** der Teilnehmer-Agent-PCs (`IP:*`). Dazu gehören seine eigenen Agent-PCs mit KI-Agenten (Prompt-Injection). Im Agent-PC des Teilnehmers lauscht sshd auf allen Schnittstellen mit Passwortanmeldung, das Passwort braucht nur 4 Zeichen, der Benutzer hat `sudo` ohne Passwort; mit Fernzugriff zusätzlich xrdp 3389. → Passwort durchprobieren = root im fremden Agent-PC, ganz ohne Hilfe-Zustimmung. | `bonys-netz/server/zentrale/app/regeln.py:32-46`; `cloudinit.py:415,422,782`; `vm.py:1897,1993`; Zusage in `README.md:30-32`, `docs/handbuch/benutzer.md:903-904` | Ziel nur `IP:5959` (Hilfe-Port); Quelle nur der Kursleiter-Rechner (Tag oder feste 100.x), nicht dessen Agent-PCs. Zweite Schicht im Gast: auf `tailscale0` nur 5959 annehmen (nftables) bzw. sshd nicht auf tailscale0. Regressionstest auf die erzeugte Regel. | klein–mittel | ✔ Code |
| I-02 | Eigener Rechner | **hoch** | Ist der Host im Bony-Netz (beim Kursleiter für die Hilfe nötig, beim Teilnehmer per „Diesen Rechner verbinden“ möglich), gilt die Grundregel `autogroup:member → autogroup:self:*`: **alle eigenen Agent-PCs erreichen den Host auf allen Ports**. Bony's VPN verbindet mit `tailscale up --reset` ohne `--shields-up`. Ein Agent-PC mit eingeschleusten Anweisungen erreicht SSH, Drucker- und Entwicklungsdienste des echten Rechners; ein Betreiber der Zentrale kann per Regel jedes Gerät auf den Host lassen. | `bonys-netz/server/zentrale/app/regeln.py:19-20`; `bonys-vpn/src/bonys_vpn/helper.py:485-487`; `hilfe.py:347-354` | Host mit `--shields-up` verbinden (die ausgehende VNC-Verbindung des Kursleiters geht weiter). Für die offizielle Tailscale-App unter Windows/macOS den Hinweis „Eingehende Verbindungen blockieren“. Auf dem Server Host-Geräte taggen und aus `autogroup:self` nehmen. | klein (App) / mittel (Server) | (C) |
| I-03 | Regeln bei Fehlern | mittel | Die Zentrale ändert erst die Datenbank, dann die Headscale-Regel. Scheitert `PUT /policy`, kommt 502, die Datenbank sagt aber schon „pausiert/beendet/entfernt“ – **der alte Zugang bleibt offen**, „Beenden“ lässt sich nicht wiederholen (409). Beim Start wird ein Fehler nur protokolliert. | `bonys-netz/server/zentrale/app/main.py:80-84,94-101,401-420,572-578` | Regel vor dem Speichern setzen bzw. bei Fehler zurückrollen; Abgleich alle ~60 s; Zustand in `/health`. | klein | (C) |
| I-04 | Server-Wechsel / Austreten | mittel | Agent-PCs bleiben bei Server-Wechsel und beim Ausschalten des Bony-Netzes im **alten Netz** (kein `tailscale logout`, Marke `bony-netz.done` meldet „schon verbunden“, geprüft wird nur „Running“, nicht der Server). Der alte Betreiber behält Netzzugang, DNS und Online-Status. | `netz.py:366-368,405-407`; `bony_netz/agentenpc.py:44-45` | „Vom Bony-Netz trennen“ (logout, tailscaled aus, Marke löschen), beim Server-Wechsel und Löschen der Instanz anbieten; beim Beitritt die ControlURL vergleichen. | mittel | (C) |
| I-05 | Kursauswahl | gering | Der eigene Rechner wird nur aus „Agent-PC wählen“ ausgenommen, wenn Bony's VPN ihn vermerkt hat; mit der offiziellen Tailscale-App lässt er sich für den Kursleiter öffnen. | `kurse.py:313-334` | Positivliste: nur Geräte, deren Name zu einem Agent-PC dieses Rechners passt. | klein | (C) |
| I-06 | DNS | gering | `--accept-dns=true`: Der Betreiber der Zentrale kann alle DNS-Anfragen des Agent-PCs umleiten und mitlesen. Die App braucht MagicDNS nicht. | `bony_netz/agentenpc.py:47`; `bonys-netz/server/vorlagen/headscale-config.yaml.vorlage:44-51` | `--accept-dns=false`. | klein | (C) |
| I-07 | Altlast IP | gering | Die Regel zielt auf die beim Beitritt gemerkte `geraet_ip`. Wird ein Gerät außerhalb der API gelöscht und die Adresse neu vergeben (`allocation: sequential`), könnte der Kursleiter ein fremdes Gerät erreichen. | `regeln.py:33-37`; `headscale-config.yaml.vorlage:12` | Beim Bauen der Regel jede IP gegen die aktuellen Knoten des Teilnehmers prüfen. | klein | (V) |

### Kursraum (K)

| Nr. | Bereich | Schwere | Beschreibung | Fundstelle | Vorschlag | Aufwand | Beleg |
|---|---|---|---|---|---|---|---|
| K-01 | Rollen | **hoch** | **Ein Teilnehmer kann sich als Kursleiter ausgeben.** Jede Eintrittskarte erlaubt `canUpdateOwnMetadata: True`; Seite und Python erkennen den Kursleiter nur am Feld `rolle` in diesen Metadaten. Mit einem eigenen LiveKit-Client setzt er `{"rolle":"kursleiter"}` und einen beliebigen Namen und kann dann: (a) per `freigabe` bei allen das Mikrofon abschalten, (b) `hilfe-anfrage` an jeden schicken – Zustimmungsdialog mit falschem Namen, bei Zustimmung gehen IP, Port und VNC-Passwort an ihn (verbinden verhindert vermutlich nur die Netzregel), (c) die Bühne übernehmen, (d) im Chat als „(Kursleiter)“ erscheinen; (e) beim echten Kursleiter fehlen für ihn „Stumm“/„Entfernen“. Die App nutzt `setMetadata`/`setName` nirgends. | `bonys-netz/server/zentrale/app/livekit.py:45`; `resources/kursraum/kursraum.js:56-66,313-317,622-633,726`; `gui/hilfe_ui.py:269-278`; `docs/bony-netz.md:177-178` | `canUpdateOwnMetadata` streichen. Die Zentrale liefert in `/eintritt` die Identität des Kursleiters mit; Seite und `TeilnehmerHilfe.anfrage` vergleichen `p.identity` (im Token, nicht änderbar). Test: Karte ohne `canUpdateOwnMetadata`. | klein | ✔ Code |
| K-02 | Karten / Widerruf | mittel | Karten gelten **6 h** und werden nie zurückgenommen: „Pausieren“ lässt den Raum offen, „Entfernen“ ändert nur Datenbank und Netzregel, nicht LiveKit; nach „Beenden“ legt LiveKit den Raum beim nächsten Beitritt neu an (`auto_create` nicht abgeschaltet). Ein entfernter Teilnehmer kann bis zu 6 h wieder eintreten. | `bonys-netz/server/zentrale/app/main.py:202-205,401-420,601-607`; `config.py:52`; `server/vorlagen/livekit.yaml.vorlage:10-12` | `room.auto_create: false`, Raum bei „läuft“ anlegen und bei Pause/Ende löschen; beim Entfernen `RemoveParticipant`; Kartenlaufzeit 10–15 min (das SDK erneuert sie). | klein–mittel | (C); Wiedereintritt (V) |
| K-03 | Sandbox | mittel | Unter Ubuntu ab 24.04 ohne AppArmor-Profil (Quelltext-Start, anderer Pfad) schaltet die App die Chromium-Sandbox **prozessweit beim Programmstart** ab, ohne Hinweis. Der Renderer dekodiert Bild und Ton fremder Teilnehmer; eine Decoder-Lücke führte direkt ins Benutzerkonto. | `kursraum.py:232-251`; `gui/kursraum_fenster.py:67-68`; `gui/app.py:39-41` | Ohne Sandbox den Kursraum nur nach deutlicher Rückfrage öffnen (oder gar nicht, mit Hinweis auf .deb/Profil); im Selbsttest melden. | klein | (C) |
| K-04 | Sprechfreigabe | gering | „Sprechen nur nach Freigabe“ wirkt nur in der Seite; die Karte erlaubt jedem `microphone`, ein manipulierter Client ignoriert die Freigabe. | `kursraum.js:415-435`; `kursraum.py:176-181`; `livekit.py:35` | Bei Pflicht-Freigabe per `UpdateParticipant` die Quellen ohne `microphone` setzen. | mittel | (C) |
| K-05 | CSP / Transport | gering | CSP erlaubt `connect-src wss: https: ws: http:`; `server_adresse` nimmt auch `ws://`/`http://` → bei falscher Server-Einstellung Karte im Klartext. | `resources/kursraum/index.html:8-10`; `kursraum.py:131,147` | `connect-src` genau auf den Kursraum-Host; `ws`/`http` nur für localhost. | klein | (C) |
| K-06 | Kursleiter-Karte | gering | Die Karte mit `roomAdmin` liegt auch in der Seite, die nur `roomJoin` braucht. | `kursraum.py:91-94,144-146`; `livekit.py:47-48` | Zwei Karten: Beitritt für die Seite, kurze Admin-Karte nur für Python. | mittel | (C) |
| K-07 | Geräterechte | gering | Kamera, Mikrofon und Bildschirm gelten für jede Seite unter `kursraum://app`, auch für die Hilfe-Seite; das Mikrofon des Kursleiters geht beim Eintreten automatisch an. | `kursraum.py:214-216`; `gui/kursraum_fenster.py:198-209`; `kursraum.js:171` | Rechte auf die Kursraum-Seite beschränken; Hilfe-Seite lehnt alles ab. | klein | (C) |
| K-08 | Qt < 6.7 | gering | Ohne `desktopMediaRequested` teilt Chromium beim Kursleiter ohne Auswahl den ganzen Bildschirm (`pyproject` erlaubt PySide6 ≥ 6.6; Pakete nutzen 6.12). | `gui/kursraum_fenster.py:195-196`; `pyproject.toml:30` | Unter Qt < 6.7 vorher fragen oder Teilen abschalten. | klein | (V) |
| K-09 | Lieferkette | gering | `fetch-livekit.py` prüft bei vorhandener Datei nur `VERSION`, nicht den Hash der `umd.js` (nur lokale Builds); LiveKit-Server `latest`. | `packaging/fetch-livekit.py:57-60`; `bonys-netz/server/install.sh:19` | Hash bei jedem Lauf und im Selbsttest prüfen; Server per Version/Digest pinnen. | klein | (C) |
| K-10 | Kennungen | gering | LiveKit-Identität = dauerhafte Instanz-ID, für alle im Raum sichtbar und über Kurse verknüpfbar; „Max (Kursleiter)“ als Anzeigename sieht aus wie die echte Markierung. | `bonys-netz/server/zentrale/app/main.py:601-604`; `kursraum.js:457` | Je Kurs abgeleitete Kennung (HMAC); Markierung als eigenes Element, „Kursleiter“ im Namen ablehnen. | klein | (C) |

### Hilfe über das Bony-Netz (H)

| Nr. | Bereich | Schwere | Beschreibung | Fundstelle | Vorschlag | Aufwand | Beleg |
|---|---|---|---|---|---|---|---|
| H-01 | Beenden | mittel | Stürzt die App des Teilnehmers ab (oder Netz weg), bleibt x11vnc im Agent-PC bis zu **30 min** aktiv; der Betrachter des Kursleiters bleibt verbunden, weil `ParticipantDisconnected` die Hilfe nicht beendet. Der Teilnehmer sieht keinen Hinweis mehr. Beim normalen App-Ende läuft der Stopp in einem `QThread`, auf den niemand wartet (V). | `resources/kursraum/kursraum.js:230-237`; `hilfe.py:141`; `gui/hilfe_ui.py:51-62,379`; `gui/app.py:61` | Beim Kursleiter Betrachter schließen, wenn der Teilnehmer geht; Totmannschalter im Gast (App erneuert alle ~10 s, sonst Stopp); beim App-Ende begrenzt warten; beim Start Reste stoppen. | mittel | ✔ Code (Disconnect) / (V) |
| H-02 | Fremde Texte als HTML | gering | Name des Kursleiters (mit K-01 frei wählbar) landet als AutoText-HTML im Zustimmungsdialog → Text optisch verfälschbar. Gleiches Muster weiter offen im alten LAN-Hilfe-Modus (S-10 aus Teil 1). | `gui/hilfe_ui.py:83,171,198,263,298`; `gui/course_ui.py:400-410` | `Qt.PlainText` für alle Labels/Meldungen mit fremden Texten. | klein | ✔ Experiment |
| H-03 | Fehler beim Beenden | gering | `hilfe.beenden` schluckt Fehler (Gast-Agent hängt) und meldet trotzdem „beendet“. | `hilfe.py:216-225`; `gui/hilfe_ui.py:376-385` | Danach `aktiv()` prüfen; bei unklarem Zustand sichtbar warnen und wiederholen. | klein | ✔ Code |
| H-04 | Anfragen-Flut | gering | Ohne laufende Hilfe erzeugt jede `hilfe-anfrage` sofort wieder einen Dialog im Vordergrund; keine Sperrzeit nach „Ablehnen“. | `gui/hilfe_ui.py:269-276,301-306` | 60 s Sperre je Absender nach Ablehnen/Zeitablauf; Obergrenze je Kurs und Stunde. | klein | ✔ Code |
| H-05 | x11vnc als root | gering | x11vnc läuft per `systemd-run` als root ohne Härtung (`NoNewPrivileges`, `ProtectSystem` …); ob CVE-2020-29074 (Shared Memory) in Debian/Kali behoben ist, ist offen. | `hilfe.py:115-121,141-142` | Härtende `--property=`; besser als Desktop-Benutzer (`--uid`); ggf. `-noshm`. | klein | ✔ Code / (V) |
| H-06 | Zusage-Prüfung | gering | Fehlt `geraet_ip` in der Antwort der Zentrale, akzeptiert `zusage_pruefen` jede Adresse in 100.64/10. | `hilfe.py:260`; `trainer/gui/hilfe_fenster.py:230` | Ohne erwartete Adresse ablehnen. | klein | ✔ Code |
| H-07 | Passwortweg | gering | Das Einmal-Passwort geht als Klartext über LiveKit-Datennachrichten; der Server der Zentrale sieht es. Die Vertrauensannahme „Zentrale ist vertrauenswürdig“ steht nirgends. | `hilfe.py:92-94`; `gui/hilfe_ui.py:346`; `vncauth.py:10-12` | In Doku und Zustimmungsdialog nennen; optional Ende-zu-Ende (LiveKit-E2EE). | klein | ✔ Code |
| H-08 | Klarheit | gering | „Ansehen und bedienen“ sagt nur „kann auch Maus und Tastatur benutzen“ – nicht, dass das alles Angemeldete einschließt (Telegram, Browser, Hermes-Schlüssel, Terminal). | `gui/hilfe_ui.py:87-91` | Ein klarer Satz dazu. | klein | ✔ Code |

### Kurspakete, Community-Katalog, Moderation (KP)

| Nr. | Bereich | Schwere | Beschreibung | Fundstelle | Vorschlag | Aufwand | Beleg |
|---|---|---|---|---|---|---|---|
| KP-01 | Skript-Zustimmung | mittel | Der Dialog „Kurse“ holt Kurspakete automatisch und ersetzt **ohne Rückfrage** jedes gleichnamige Paket der Bibliothek (außer „eigen“). Ein offenes Anleitungsfenster liest die Skripte zur Laufzeit neu von der Platte, prüft die Zustimmung aber nicht erneut; `_takt` startet Startskripte (Standard root) automatisch. Damit stimmt „wird bei geänderten Skripten erneut eingeholt“ nicht. | `kurse.py:405-415`; `gui/kurse_dialog.py:270-277`; `gui/kurspaket_anleitung.py:185-193,558-590,679-695`; `kurslauf.py:164,223`; `docs/kurspaket-format.md:204` | Direkt vor jeder Ausführung Paket frisch laden und `zustimmung_noetig` prüfen bzw. Skript-Kennung vergleichen; offenes Fenster bei Ersatz schließen/neu laden; anderen Inhalt nur nach Rückfrage übernehmen. | klein | ✔ Experiment (altes Objekt liest neues Skript, keine Rückfrage); Fenster-Pfad (C) |
| KP-02 | Zustimmungsdialog | mittel | Der Dialog nennt nur Pfade und „können Dateien anlegen oder ändern“ – nicht, dass Skripte **als root** laufen, ins Internet dürfen und gespeicherte Zugangsdaten lesen können. „Vorhandenen verwenden …“ erlaubt dafür den Haupt-Agent-PC mit persönlichen Konten. Skriptinhalt nicht ansehbar. | `gui/kurspaket_bibliothek.py:115-121,151,167-172`; `kurspaket.py:254`; `kurslauf.py:4-10` | Je Skript „als root“ anzeigen, klarer Satz zu Netz/Zugangsdaten, Knopf „Skripte ansehen“; bei ungeprüften Paketen neuen Agent-PC empfehlen. | klein | (C) |
| KP-03 | Fremde Texte als HTML | gering | Paketnamen/-titel landen als AutoText in `QMessageBox`/`QLabel` → gefälschte Dialoge und **klickbare Links** (`openExternalLinks`, auch `file://`). | `kurspaket.py:129`; `gui/kurspaket_bibliothek.py:92,139,326,506`; `gui/kurspaket_anleitung.py:224,446,616`; `gui/main_window.py:1642` | `Qt.PlainText` bzw. `html.escape`. | klein | ✔ Experiment |
| KP-04 | Vertrauensanzeige | gering | `_md` maskiert keine Setext-Überschriften/Listen/Autolinks; eine Beschreibung kann „✓ Geprüftes Kurspaket“ groß über der echten Vertrauenszeile anzeigen. | `gui/kurspaket_bibliothek.py:71-75,377-381,446` | Paketangaben als PlainText; Vertrauensstatus in eigenem Widget. | klein | ✔ Experiment |
| KP-05 | Kurs-Import | gering | Ein Kurs-Paket mit der ID eines mitgelieferten Pakets verdeckt dieses dauerhaft, auch nach Kursende. | `kurse.py:405-415`; `kurspaket.py:1063-1072` | Eigener Namensraum oder Rückfrage mit Herkunftsvergleich. | klein | ✔ Experiment |
| KP-06 | Katalog-Downloads | gering | `urlopen` folgt Weiterleitungen ungeprüft (auch https→http, fremde Hosts); Community-Einträge dürfen `datei` auf beliebige https-Hosts zeigen → IP und Download gehen an Dritte, entgegen dem Zustimmungstext. Integrität schützt SHA-256. Keine Gesamt-Zeitgrenze. | `kurspaket.py:1211-1213,1224-1228,1244-1247,1280-1291` | Redirect-Handler: nur https und derselbe Host; Community-Dateien nur vom Katalog-Host; Gesamt-Deadline. | klein | (C) |
| KP-07 | Windows-Namen | gering | `bilder/evil.exe.` hat leere Endung und besteht die Prüfung; Windows entfernt den Punkt → `evil.exe` im Bibliotheksordner (nichts wird ausgeführt). | `kurspaket.py:67,929,961-965` | Namen mit `.`/Leerzeichen am Ende, `:`, reservierte Windows-Namen ablehnen. | klein | ✔ unter Linux / (V) Windows |
| KP-08 | Robustheit | gering | Datei-/Ordner-Kollision (`bilder/a` + `bilder/a/b.md`) gibt rohen `OSError` mit vollem Pfad; im Moderationsdialog nicht abgefangen. Ebenso unerwartete Typen in Server-Antworten (`"nr": "x"`). | `kurspaket.py:961-975`; `kurspaket_moderation_client.py:191,197,282-285`; `gui/moderation_dialog.py:222-226,271-278` | Vorab prüfen; `OSError`/`ValueError` in die eigenen Fehlerklassen wandeln. | klein | ✔ Experiment |
| KP-09 | Fortschritt | gering | `melden` wird beim erneuten Öffnen ohne Kurs nicht zurückgesetzt; ein offenes Fenster meldet nach „Kurs verlassen“ weiter Lektion/geschafft. | `gui/kurspaket_anleitung.py:191-193,493-503`; `gui/kurse_dialog.py:356-372` | In `oeffnen` immer setzen (auch `None`); beim Verlassen abschalten. | klein | (C) |

### Zentrale – Betrieb, Missbrauch, Härtung (Z)

| Nr. | Bereich | Schwere | Beschreibung | Fundstelle | Vorschlag | Aufwand | Beleg |
|---|---|---|---|---|---|---|---|
| Z-01 | Zugriffsprotokoll | **hoch** | Uvicorn läuft mit Zugriffsprotokoll (Standard) und `--proxy-headers --forwarded-allow-ips *` → **echte Client-IPs** jedes App-Aufrufs mit Zeit und Pfad (`kurs_id`, `geraet_id`) im Docker-Log; die Apps fragen alle 15–60 s → Bewegungsprofil. Docker-Logs ohne Rotation. README: „speichert keine … IP-Adressen“. | `bonys-netz/server/zentrale/Dockerfile:17`; `server/vorlagen/docker-compose.yml.vorlage` (kein `logging:`); `bonys-netz/README.md:140-146` | `--no-access-log` (oder Format ohne IP); `logging` 5 MB × 3 für alle Dienste (wie Kursportal-Bundle v8); README korrigieren; vorhandene Logs bereinigen. | klein | ✔ Code |
| Z-02 | IP-Hash | mittel | `sha256(salz + IP)` wird **dauerhaft** bei der Instanz gespeichert, obwohl die Grenze nur 24 h braucht; mit dem Salz lässt sich IPv4 durch Probieren zurückrechnen. README: „nicht umkehrbar“. | `main.py:236-257`; `db.py:22`; `README.md:143-144` | Eigene Tabelle mit Zeit, nach 24 h löschen (oder Tagessalz); Text korrigieren. | klein | (C) |
| Z-03 | Löschfristen | mittel | Teilnahmen (Anzeigename, Gerätename, 100.x, Zeit) und Kurse bleiben nach „Beenden“ unbegrenzt; Kurse enden nie von selbst, Instanzen laufen nie ab; kein Aufräumbefehl. | `main.py:202-205,393-399`; `db.py:34-55`; `admin.py` | Teilnahmen beim Beenden löschen/anonymisieren; Kurse nach Code-Ablauf beenden; Befehl `aufraeumen` (beendete Kurse, inaktive Instanzen samt Headscale-Benutzer). | mittel | (C) |
| Z-04 | Rate-Limits / Kurscodes | mittel | Nur das Anlegen von Instanzen ist gebremst (3/IP/Tag, nur IPv4). `POST /kurse/beitreten` ungebremst; Kurscode 8 Zeichen aus 31 (≈ 39,6 Bit), bis 60 Tage gültig – grob 1–2 % Trefferchance bei 25 Codes und 100 Versuchen/s über 60 Tage (V); Treffer = Bild, Ton, Chat. | `kennungen.py:7-13`; `main.py:519-530`; `config.py:43` | Fehlversuche je Instanz und IP-Hash begrenzen (z. B. 10/h → 429); allgemeines Limit je Token; Code optional länger. | klein | (C) / Rechnung (V) |
| Z-05 | Gerätegrenze | mittel | Gezählt werden nur registrierte Knoten; Anmeldeschlüssel sind unbegrenzt → 100 Schlüssel holen, 100 Geräte registrieren; Headscale-Datenbank flutbar. | `main.py:329-349`; `headscale.py:44-56` | Offene Schlüssel mitzählen; N Schlüssel/Stunde/Instanz. | klein | (C) |
| Z-06 | Kursleiter-Entzug | mittel | `kursleiter-entziehen` lässt laufende Kurse laufen; der Ex-Kursleiter kann sie nicht mehr beenden, der Admin hat keinen Befehl dafür. | `admin.py:67-73`; `main.py:119-122,401-402` | Beim Entzug Kurse beenden; Admin-Befehl `kurs-beenden <id>`. | klein | (C) |
| Z-07 | Sicherung | mittel | Kein Konzept für Sicherung/Wiederherstellung von `zentrale.db`, Headscale-Datenbank und Noise-Schlüssel. Geht `zentrale.db` verloren, antwortet die Zentrale 401 – die App **verwirft dann die Anmeldung**, alle müssen neu anlegen. | `netz.py:138-146`; `bonys-netz/README.md:99-117` | Nächtlich `sqlite3 .backup` von `zentrale-daten/` und `headscale/data/`, verschlüsselt auf einen anderen Rechner; Wiederherstellung üben. | mittel | (C) / Folge (V) |
| Z-08 | Last / Kosten | mittel | DERP-Relay ohne Mengengrenze für jede anonyme Instanz; LiveKit ohne `limit:`; alle 49 Teilnehmer dürfen Kamera senden (grob mehrere 100 Mbit/s im ungünstigsten Fall); ohne TURN scheitert der Kursraum hinter Proxys mit nur 443. | `headscale-config.yaml.vorlage:14-27`; `livekit.yaml.vorlage:1-12`; `livekit.py:35-46` | Verkehr überwachen; LiveKit-Limits; Kamera erst nach Freigabe; TURN/TLS nur bei Bedarf, Grenze dokumentieren. | mittel | (C) / Kosten (V) |
| Z-09 | Verfügbarkeit | gering–mittel | Globale Sperre wird während Headscale-Aufrufen (15 s) gehalten, auch im `async`-Upload-Handler → hängt Headscale, steht die ganze Zentrale. | `main.py:94-101,238-257,426-437`; `db.py:98` | Aufrufe außerhalb der Sperre; Upload synchron oder Threadpool. | klein | (C) |
| Z-10 | Angriffsfläche | gering | Headscale-REST über die VPN-Domain öffentlich erreichbar; API-Schlüssel 10 Jahre; FastAPI `/docs`, `/redoc`, `/openapi.json` öffentlich. | `Caddyfile.vorlage:1-3`; `install.sh:248`; `main.py:87` | `/api/*` auf der VPN-Domain 404; Schlüssel kürzer mit Wechselplan; Doku-URLs aus. | klein | (C) |
| Z-11 | Lieferkette | gering | `LIVEKIT_VERSION=latest`, `caddy:2`, `requirements.txt` mit `==x.*` – ein neues LiveKit kann `livekit-client` 2.22.3 brechen. | `install.sh:19`; `docker-compose.yml.vorlage:16`; `requirements.txt:1-4` | Feste Versionen bzw. Digests. | klein | (C) |
| Z-12 | Container / Dateien | gering | Kein `read_only`, `cap_drop`, `no-new-privileges`, keine Grenzen/Healthchecks (Zentrale selbst läuft gut als uid 10001); `livekit.yaml` mit Secret ohne `chmod 600`. | `docker-compose.yml.vorlage:2-53`; `install.sh:165-170` | Ergänzen, Zentrale zuerst; `chmod 600`. | klein | (C) |

### Netz-Baustein (B)

| Nr. | Bereich | Schwere | Beschreibung | Fundstelle | Vorschlag | Aufwand | Beleg |
|---|---|---|---|---|---|---|---|
| B-01 | Instanz-Token | mittel | urllib übernimmt den `Authorization`-Kopf bei einer Umleitung auch zu fremden Zielen und auf `http://` – mit Schein-Token nachgewiesen (302 von 127.0.0.1 nach 127.0.0.2, Kopf kam an). `server_normalisieren` nimmt `http://…` ohne Warnung an. Betrifft auch bonys-netz und Bony's VPN (dateigleicher Baustein). | `bony_netz/zentrale.py:61-63`; `bony_netz/konto.py:42` | Opener ohne Umleitungen (Umleitung = Fehler); `http://` nur für localhost (wie `kurspaket._url_ok`). | klein | ✔ Experiment |
| B-02 | Geräteschlüssel | gering | Schlüssel steht während `tailscale up` als `--authkey` in `/proc/*/cmdline`; nach hartem Abbruch des ersten Starts bleibt `/root/bony-netz-beitritt.sh` mit Schlüssel liegen, `generalize_script` löscht es nicht (Schlüssel gilt nur einmal und 60 min). | `bony_netz/agentenpc.py:47`; `cloudinit.py:696` | `--auth-key=file:` mit 0600-Datei; Skript in die Löschliste. | klein | (C) |

### Dokumentation, Recht und Editionen (DR)

*Hinweise, keine Rechtsberatung. Für 1.0 eine fachkundige Prüfung empfehlenswert.*

| Nr. | Bereich | Schwere | Beschreibung | Fundstelle | Vorschlag | Aufwand | Beleg |
|---|---|---|---|---|---|---|---|
| DR-01 | Rechtstexte Zentrale | mittel | Für `zentrale.bony23.de` und den Kursraum-Server gibt es keine Datenschutzerklärung und kein Impressum; im Bony-Netz-Dialog fehlt Hinweis und Link vor „Instanz anlegen“. Die Handbuch-Tabelle nennt nicht: öffentliche IP gegenüber Zentrale, Headscale, DERP, LiveKit; Zugriffsprotokoll (Z-01); bei Headscale Endpunkte, Systeminfo, „zuletzt gesehen“. | `docs/handbuch/benutzer.md:894-898`; `gui/netz_dialog.py`; `bonys-netz/README.md:140-146` | Wie beim Kursportal: Rechtstexte (Ordner `rechtstexte/`), Link im Netz-Dialog und beim ersten Betreten des Kursraums; Tabelle ergänzen. | klein–mittel | (C) |
| DR-02 | Doku-Richtigkeit | mittel | Bild, Ton, Chat und das VNC-Passwort laufen durch den LiveKit-Server (verschlüsselt nur bis zum Server); „Ende-zu-Ende“ gilt nur für WireGuard. „Aufgezeichnet wird nichts“ stimmt für den Server, Mitschnitte bei Teilnehmenden sind technisch nicht verhindert. | `bonys-netz/README.md:33-34`; `docs/handbuch/kursleiter.md:296-300`; `docs/handbuch/benutzer.md:895` | Klar formulieren („Server leitet weiter, zeichnet nicht auf; Mitschnitte sind nach Kursregel nicht erlaubt“). | klein | (C) |
| DR-03 | Telekommunikationsrecht | mittel | Das Bony-Netz vermittelt Verbindungen (DERP) und bietet Chat/Video/Ton für einen offenen Nutzerkreis. Offen ist, ob eine **Meldepflicht bei der Bundesnetzagentur (§ 5 TKG)** besteht und welche Pflichten aus dem **Fernmeldegeheimnis (§ 3 TDDDG)** folgen. Die Frage steht bisher nirgends. | – | In die Fragenliste für die Fachperson (`docs/dev/datenschutz-kursportal.md`, Abschnitt Fragen) aufnehmen. | klein | (V) |
| DR-04 | Editionen | gering | Moderationsdialog und -client liegen in `gui/` bzw. `bonys_agents/`, nicht in `trainer/`; in der Anwender-Version nur ausgeblendet – entgegen `docs/editionen.md:49-52`; `check-edition.py` prüft es nicht (ohne Token keine Anfrage). | `gui/main_window.py:343-345`; `gui/moderation_dialog.py`; `kurspaket_moderation_client.py:25` | Nach `trainer/` verschieben oder in der Doku als Ausnahme nennen. | klein | (C) |
| DR-05 | gitleaks | gering | Drei absichtliche Test-Geheimnisse lösen gitleaks aus; echte Funde gehen dazwischen leicht unter. | `tests/test_kurspaket_portal.py:41,97`; `tests/test_kurspaket_editor.py:65` | `.gitleaksignore` mit den Fingerabdrücken. | klein | ✔ |

---

## Wahrscheinliche Betreiberpflichten (Zentrale und Kursraum)

*Keine Rechtsberatung – von einer Fachperson prüfen lassen.* Verantwortlicher ist laut
`docs/dev/datenschutz-kursportal.md` Bony privat.

1. **Impressum** (§ 5 DDG) für `zentrale.bony23.de` und den Kursraum-Server, sofern geschäftsmäßig – bei einem öffentlich angebotenen Dienst wahrscheinlich.
2. **Datenschutzerklärung** (Art. 13 DSGVO): IP-Adressen, Anzeigenamen, Kursnamen, Kursleiter-Name, Gerätenamen, Netzadressen, Endpunkte, Fortschritt, Kamera/Mikrofon (Weiterleitung, keine Aufzeichnung), Logs mit Frist, Hoster, Rechtsgrundlage, Betroffenenrechte („Instanz löschen“ gibt es schon).
3. **Rollen Kursleiter ↔ Betreiber** (Art. 26 gemeinsame Verantwortung, Art. 28 Auftragsverarbeitung oder eigene Verantwortung) – davon hängen Nutzungsbedingungen für Kursleiter ab.
4. **Auftragsverarbeitungsvertrag mit dem Hoster** (Art. 28), Standort EU; Drittlandbezug prüfen (z. B. an Geräte verteilte DNS-Server).
5. **Löschkonzept und Fristen** (Art. 5 Abs. 1 e, Art. 17) – siehe Z-01 bis Z-03.
6. **Verzeichnis der Verarbeitungstätigkeiten** (Art. 30) und **technisch-organisatorische Maßnahmen** (Art. 32) – ob nötig, klären.
7. **Datenpannen** (Art. 33/34): Ablauf festlegen.
8. **Telekommunikationsrecht** (DR-03): Meldepflicht § 5 TKG, Fernmeldegeheimnis § 3 TDDDG.
9. **Inhalte** (DDG/DSA): hochgeladene Kurspakete im geschlossenen Kreis – ob Hosting-Pflichten (Meldeweg) greifen.
10. **Kursraum:** Information/Einwilligung für Kamerabilder, Regel „keine Mitschnitte“; bei Minderjährigen Art. 8 DSGVO.
11. **Selbstbetreiber:** Wer nach README einen eigenen Server aufsetzt, ist selbst verantwortlich – ein Satz dazu.

---

## Muss vor 1.0

1. **I-01** Kursleiter-Regel eng: nur Port 5959, nur vom Kursleiter-Rechner; zweite Schicht im Gast (tailscale0 nur 5959).
2. **K-01** Rollenfälschung: `canUpdateOwnMetadata` aus, Kursleiter über die Identität im Token erkennen (Seite und Python).
3. **I-02** Eigener Rechner im Bony-Netz mit `--shields-up` (Bony's VPN) bzw. Hinweis für die offizielle Tailscale-App.
4. **Z-01** Zugriffsprotokoll der Zentrale ohne IPs, Logrotation für alle Dienste, README korrigieren.
5. **K-02 + I-03** Zugänge zuverlässig schließen: Karten kurz und widerrufbar, `auto_create` aus, Netzregel vor der Datenbank bzw. Abgleich.
6. **H-01** Hilfe endet zuverlässig, wenn der Teilnehmer geht oder die App abstürzt (Totmannschalter).
7. **KP-01 + KP-02** Skript-Zustimmung direkt vor der Ausführung prüfen; Dialog nennt root, Netz, Zugangsdaten.
8. **B-01** Instanz-Token nie bei Umleitungen oder über `http://` senden.
9. **DR-01 + DR-02 + DR-03 + Z-02 + Z-03** Rechtstexte für Zentrale und Kursraum, richtige Datenschutz-Angaben, Löschfristen, TKG-Frage an die Fachperson.

## Sollte vor 1.0

- **Aus Teil 2:** K-03 (Sandbox-Hinweis), I-04 (Bony-Netz verlassen), H-02/KP-03/KP-04 und S-10 aus Teil 1 (überall PlainText für fremde Texte), H-03, H-04, H-08, KP-05, KP-06, Z-04 (Rate-Limits, Kurscodes), Z-05, Z-06, Z-07 (Sicherung der Zentrale), Z-08 (Last/Kosten beobachten), Z-09.
- **Offen aus Teil 1:** S-05, S-06, S-08, S-09, S-10 · R-04, R-07, R-10, R-11, R-12, R-13, R-14 · U-01, U-02, U-06, U-07, U-08, U-10 · D-02 · L-03, L-04, L-05, L-06 · P-07, P-10, P-13 · N-01, N-02, N-05 · Q-01 (Stand siehe Tabelle unten).

## Kann später

Teil 2: I-05, I-06, I-07, K-04 bis K-10, H-05, H-06, H-07, KP-07, KP-08, KP-09, Z-10, Z-11, Z-12, B-02, DR-04, DR-05.
Teil 1 unverändert: S-07, S-11–S-15 · P-08, P-09, P-11, P-12, P-14 · R-08, R-09, R-15, R-16 · U-09, U-11–U-15 ·
D-05–D-07 · L-07 · Q-02–Q-07 · N-03, N-04, N-06, N-07.

---

## Stand der „Sollte vor 1.0“-Punkte aus Teil 1

Geprüft per Code-Stichprobe (grep/Lesen der genannten Fundstellen), nicht durch Ausprobieren. „offen“ heißt: die in
Teil 1 genannte Stelle ist unverändert bzw. die vorgeschlagene Lösung ist nicht zu finden.

| Punkt | Stand | Beobachtung |
|---|---|---|
| S-05 RFB-CPU | offen | `rfb.py:92,106` hängt weiter `bytes` an und schneidet per Slicing |
| S-06 Verbindungslimits | offen | keine Obergrenze in `trainer/share_server.py`/`present.py` gefunden |
| S-08 Abschießen per Fehlversuchen | offen | `trainer/share_server.py:203-206` beendet die Freigabe nach `MAX_FAILS_TOTAL` |
| S-09 WebSocket-Fragmente | nicht abschließend geprüft | keine eigene Fragmentgrenze gefunden |
| S-10 PlainText Hilfe-Modus | offen | `gui/course_ui.py:400-410` QMessageBox ohne PlainText; gleiches Muster neu in H-02, KP-03 |
| R-04 Sperre/Einzelinstanz | offen | kein `QLocalServer`, keine Datei-Sperre je Agent-PC |
| R-07 Platzprüfung | offen | `storage.py:368` `MIN_FREE_GB = 4` |
| R-10 Vorlagen-Sperre nach Neustart | nicht abschließend geprüft | – |
| R-11 RAM-Warnung | offen | keine Prüfung des freien Speichers vor dem Start gefunden |
| R-12 Download fortsetzbar | offen | kein `Range` in `images.py` |
| R-13 Obsidian API-Limit | offen | `apps.py:191` weiter `api.github.com` |
| R-14 halbe Ordner beim Anlegen | offen | kein Bauen in Zwischenordner gefunden |
| U-01/U-02 Fehlertexte | offen | keine zentrale Übersetzung (`friendly_error`) gefunden |
| U-06 Beschleuniger prüfen | offen | keine QMP-Abfrage des Beschleunigers |
| U-07 QEMU-Fenster-X | offen | kein `window-close=off` |
| U-08 Einrichtungsdialog | offen | kein „Nicht mehr anzeigen“ |
| U-10 „Gast-Agent“ | offen | weiter in `gui/install_dialog.py:4,101,106` |
| D-02 Laien-Doku | teilweise | Handbücher mit Bildern und PDFs vorhanden (`docs/handbuch/`); `SECURITY.md` und FAQ fehlen |
| L-03–L-06 | nicht abschließend geprüft | kein Gewährleistungshinweis im „Über“-Fenster gefunden (L-06), kein Abschnitt „Bilder und Logo“ (L-05) |
| P-04 gepinnte Builds | **erledigt** | `packaging/requirements-build.txt` mit `--require-hashes` (`release.yml:156,248`) |
| P-07 Update-/Purge-Tests | nicht abschließend geprüft | – |
| P-10 `Valid-Until`/Passphrase | offen | `build-apt-repo.sh:36` weiter `--passphrase` |
| P-13 APT-Zeitplan | offen | `apt-repo.yml:21-22` nur `schedule` |
| N-01 Kill-Switch `forward` | offen | kein `forward` in `bonys-vpn/src/bonys_vpn/killswitch.py` |
| N-02 DNS-Ausnahme | offen | `bonys-vpn/src/bonys_vpn/install.py:54` weiter `10.0.2.0/24` |
| N-05 Mission Control signieren | offen | `install.sh:134-139` prüft nur unsignierte `SHA256SUMS` |
| Q-01 Tests Update/Download/Löschen | nicht abschließend geprüft | – |

---

## Plattformen: was wirklich getestet ist

| Teil | Linux | Windows | macOS |
|---|---|---|---|
| Unit-Tests, beide Editionen (CI) | ✔ Ubuntu 26.04, Py 3.10/3.13 | ✔ Py 3.10/3.13 | ✔ Py 3.10/3.13 |
| Selbsttest „Kursraum (Qt WebEngine, livekit-client)“ im Paket | ✔ CI | ✔ CI | ✔ CI |
| Kursraum mit echtem Server | ✔ Bony (Linux Mint) | ✗ nicht ausprobiert | ✗ nicht ausprobiert (Freigabe Bildschirmaufnahme!) |
| Bildschirm teilen | ✔ Linux (X11) | ✗ | ✗ |
| Hilfe (noVNC eingebettet, TigerVNC-Rückfall) | ✔ Linux | ✗ (Tailscale-App, `%TEMP%`-Passwortdatei) | ✗ (Tailscale-App, `$TMPDIR`) |
| Ubuntu 24.04+ mit AppArmor-Profil | ✗ nur nach Doku | – | – |
| Bony-Netz mit drei Rechnern | ✗ offen (Probekurs) | ✗ | ✗ |

Quelle: `docs/bony-netz.md` („Windows und macOS … sowie Ubuntu 24.04 bisher nur nach Quelltext/Doku, nicht ausprobiert“), CI-Matrix `.github/workflows/ci.yml`.

### Testanleitung für Bony (Windows und macOS)

1. **Vorbereitung:** Kursleiter-Edition auf dem eigenen Linux-Rechner, Anwender-Edition auf einem Windows-11-Rechner und (wenn möglich) einem Mac; alle mit eigener Bony-Netz-Instanz.
2. **Kursraum:** Kurs anlegen und starten, beide Teilnehmer treten bei. Prüfen: Bild und Ton in beide Richtungen, Chat, Hand heben, Sprechfreigabe, Stumm/Entfernen durch den Kursleiter. Auf dem Mac: Fragt macOS nach Kamera und Mikrofon? Beim Teilen (nur Kursleiter) nach „Bildschirmaufnahme“?
3. **Hilfe:** Teilnehmer (Windows) bittet um Hilfe, Kursleiter öffnet die Ansicht. Danach Teilnehmer-App hart beenden (Task-Manager) → bleibt die Ansicht beim Kursleiter offen? (H-01). Unter Windows nach 20 s prüfen, ob in `%TEMP%` keine VNC-Passwortdatei mehr liegt (nur beim TigerVNC-Rückfall).
4. **Tailscale-App unter Windows/macOS:** Ist der eigene Rechner im Netz, darf er in „Agent-PC wählen“ nicht auftauchen (I-05); in der Tailscale-App „Eingehende Verbindungen blockieren“ prüfen (I-02).
5. **Kurspakete unter Windows:** Paket mit Datei `bilder/test.txt.` importieren und im Ordner `%LOCALAPPDATA%\bonys-agents\kurspakete\…\bilder` nachsehen, ob daraus `test.txt` wurde (KP-07).
6. **Ergebnis:** je Punkt „geht / geht nicht / Meldung“ an Claude.

---

## Vorschlag: Aufteilung der „Muss“-Punkte in Claude-Code-Sitzungen

| Sitzung | Inhalt | Punkte | Hinweise |
|---|---|---|---|
| 1 – Zentrale 0.2.1 (Repo `bonys-netz`) | Kursleiter-Regel nur 5959 und nur vom Kursleiter-Rechner (Tag), Regel vor der Datenbank + Abgleich; Karten ohne `canUpdateOwnMetadata`, Kursleiter-Identität in `/eintritt`, `auto_create: false`, Raum anlegen/löschen, `RemoveParticipant`, kurze Kartenlaufzeit; `--no-access-log`, Logrotation, README; gleich mit: Z-06, Z-10. | I-01 (Server), K-01 (Server), K-02, I-03, Z-01 | Tests der Zentrale brauchen `fastapi` (eigenes venv im bonys-netz-Repo). Deploy durch Bony. Erst danach Sitzung 2 live testen. |
| 2 – Kursraum und Hilfe (App) | Kursleiter über die Identität erkennen (Seite + `TeilnehmerHilfe`), Hilfe endet bei Disconnect, Totmannschalter im Gast, nftables auf `tailscale0` nur 5959; gleich mit: H-02/S-10/KP-03 PlainText, H-03, H-04, H-08, K-03. | K-01 (App), H-01, I-01 (Gast) | Muss mit Zentrale 0.2.1 zusammenpassen (Feld in `/eintritt`, alte Zentrale: Rückfall ablehnen). |
| 3 – Baustein 0.2.1 und Bony's VPN | Opener ohne Umleitungen, kein `http://`; `--auth-key=file:`, `--accept-dns=false`; `--shields-up` in Bony's VPN; „Vom Bony-Netz trennen“. | B-01, I-02, (B-02, I-06, I-04) | Baustein in allen drei Repos dateigleich halten; Bony's VPN braucht ein eigenes Release. |
| 4 – Kurspakete | Zustimmung direkt vor der Ausführung, Ersatz nur nach Rückfrage, Dialog mit root/Netz/Zugangsdaten und „Skripte ansehen“; gleich mit: KP-04, KP-05, KP-06. | KP-01, KP-02 | Test: Paket im Hintergrund ersetzen → Rückfrage muss kommen. |
| 5 – Datenschutz Zentrale (mit Bony) | Entwürfe Datenschutzerklärung/Impressum für Zentrale und Kursraum (wie `docs/recht/kursportal/`), Link im Netz-Dialog und Kursraum, Handbuch-Tabelle, Löschfristen und IP-Hash (Code), TKG-Frage in die Fragenliste. | DR-01, DR-02, DR-03, Z-02, Z-03 | Texte sind Entwürfe; Name/Anschrift trägt Bony selbst ein; Fachperson. |

---

## Was ausdrücklich GUT gelöst ist (bei Änderungen nicht kaputt machen)

- **Bony-Netz standardmäßig aus, belegt:** `netz._zentrale()` bricht ohne Schalter vor jeder Anfrage ab; Tests `test_standard_ist_aus`, `test_ohne_bony_netz_kein_kontakt` (zählt Anfragen = 0), `test_fenster_ausgeschaltet_fragt_nicht`. Community-Katalog nur mit Schalter **und** Zustimmung (`kurspaket.py:1186-1190`, Test vorhanden).
- **Geräteschlüssel:** einmal nutzbar, 60 min gültig, erst beim Anlegen geholt, nie in `vm.json` oder Meldungen (`repr=False`); Seed-ISO 0600, nach „READY“ gelöscht; Vorlagen und `.bonys` ohne Tailscale-Identität (Test).
- **konto.json** atomar, 0600 im 0700-Ordner; Token in keinem Text.
- **Zentrale:** Tokens und Kursleiter-Codes nur als SHA-256; Kursleiter-Codes ≈ 59 Bit, einmalig; Instanzen per `autogroup:self` getrennt, Teilnehmer erreichen sich nicht; Regeln beim Start aus der Datenbank; Kurse nur mit Kursleiter-Code (keine Spam-Kurse); Eigentumsprüfung beim Beitritt; Karten raumgebunden, `screen_share`/`roomAdmin` nur für den Kursleiter; Upload beim Streamen begrenzt und atomar; Ports intern, DERP `verify_clients`; Caddy ohne Zugriffsprotokoll; Zentrale als uid 10001; keine Aufzeichnung.
- **Ausfall der Zentrale:** App bleibt bedienbar – alle Aufrufe mit 15 s Zeitlimit im Hintergrund-Thread, Agent-PC entsteht auch ohne Netz.
- **Kursraum:** Fremde Texte nur per `textContent`, kein `innerHTML`/`eval`, CSP `script-src 'self'`; QWebChannel-Slots einzeln geprüft (Stumm/Entfernen nur mit Kursleiter-Rolle laut Zentrale und `roomAdmin`); Navigation nur `kursraum://app`, keine Popups, kein LocalStorage; Schema-Handler mit Pfadschutz; Bildschirm teilen doppelt gesperrt; Karte nie in Adresse oder Log; `livekit-client` 2.22.3 mit fester SHA-256 und byte-gleich nachgeprüft; AppArmor-Profil eng (nur `userns`).
- **Hilfe:** x11vnc mit `-listen <100.x> -once -timeout 120 -nevershared -nosel -noremote -nocmds`, Lauschadresse streng auf 100.64/10 geprüft; Einmal-Passwort per `secrets` (62⁸) über stdin in `/run` 0700; Zustimmung jedes Mal, 60 s ohne Antwort = Ablehnen, Enter/Esc lehnen ab; Zusage nur auf die eigene Anfrage und gegen die IP der Zentrale geprüft; Brücke nur 127.0.0.1 mit geheimem Pfad (`compare_digest`) und genau einer Verbindung; TigerVNC-Passwortdatei 0600 und gelöscht.
- **Kurspakete:** ZIP-Vorprüfung (Pfade, Links, Sonderdateien, Verschlüsselung, Anzahl, Tiefe, Größe, Endungen, Groß-/Kleinschreibung) und Zählung der echten Bytes (Zip-Bombe abgewiesen); Skripte laufen nie auf dem Host, nur per Gast-Agent mit `env -i`, `timeout`, `runuser`; Signatur per minisign mit festem Schlüssel, `pruefsummen.txt` exakt; Community-Pakete nie „geprüft“, „mitgeliefert“ nicht vortäuschbar; Anleitung mit `MarkdownNoHTML`, Bilder nur aus dem Paketordner, Links nur https.
- **Moderationsclient:** keine Weiterleitungen, Token in eigener 0600-Datei, bei 401/403 gelöscht, Original begrenzt und per SHA-256 geprüft, Inhalte nur als bereinigter Klartext.
- **Aus Teil 1 weiter gut:** QMP/QGA über Unix-Sockets (S-01 behoben) – genau das macht Paketskripte im Gast harmlos für den Host.

---

## Was NICHT geprüft werden konnte – und wie du es selbst prüfst

| Thema | So prüfst du es |
|---|---|
| **Probekurs über das Internet** (2–3 Rechner, einer Windows) | Aufbau: A = Kursleiter (Linux) mit eigenem Agent-PC KA, B = Teilnehmer (Windows) mit B1 und B2, C = Teilnehmer per Handy-Hotspot mit C1. Ablauf wie in der Plattform-Anleitung oben; zusätzlich Kurs beenden → alle fliegen raus, erneuter Eintritt wird abgelehnt. |
| **I-01 Isolation** | Während der Kurs läuft, aus A und aus KA: `nc -zv <B1-100.x> 22 3389 5959`. Heute vermutlich alle offen; nach der Behebung nur 5959 und nur von A. Nicht erreichbar sein dürfen: B2 von A, C1 von B1, A von B1. Nach „Pausieren“ muss alles scheitern. |
| **I-02 eigener Rechner** | Rechner über Bony's VPN verbinden, `tailscale debug prefs \| grep -i shields`; aus einem eigenen Agent-PC `nc -zv <Host-100.x> 22`. |
| **K-01 Rollenfälschung** | Nur nach der Behebung sinnvoll: mit `livekit-server --dev` und einer Testseite `setMetadata('{"rolle":"kursleiter"}')` – muss mit „permission denied“ scheitern. |
| **K-02 / I-03 Widerruf** | Testkurs: Teilnehmer entfernen bzw. pausieren → hat der Teilnehmer noch Bild/Ton? `docker compose stop headscale`, „Pausieren“ (502), `docker compose start headscale`, dann `headscale policy get` – steht die Kursleiter-Regel noch drin? |
| **H-01 Absturz bei Hilfe** | Hilfe (bedienen) starten, Teilnehmer-App mit `kill -9` beenden; bleibt der Betrachter verbunden? Im Gast `systemctl is-active bonys-hilfe`. |
| **Z-01 Protokolle am Server** | Im Server-Ordner der Zentrale: `docker logs --tail 5 zentrale` (stehen IPs drin?), `docker inspect -f '{{.Name}} {{.HostConfig.LogConfig}}' $(docker ps -q)`. Ausgaben enthalten personenbezogene Daten – nicht weitergeben, nicht ins Repo oder nach Obsidian. |
| **Weitere Server-Checks** | `headscale policy get` (gültige Regel? ohne gültige Regel lässt Headscale vermutlich alles zu), `headscale preauthkeys list` (Z-05), offene Ports von außen (`nmap -Pn -p- <IP>`), `curl -s -o /dev/null -w '%{http_code}' https://zentrale.bony23.de/docs` (Z-10), `ls -l livekit/` (Z-12), Sicherung vorhanden? (Z-07), Datenbestand beendeter Kurse (Z-03). |
| **Kein Kontakt im Auslieferungszustand** | `ncat -lk 127.0.0.1 8899`; App mit leerem Profil starten: `HOME=$(mktemp -d) https_proxy=http://127.0.0.1:8899 bonys-agents`, alle Fenster einmal öffnen – keine `CONNECT`-Zeile zu `zentrale.bony23.de` oder `kurse.bony23.de`. |
| **K-03 Sandbox** | Ubuntu 24.04: einmal mit .deb, einmal aus dem Quelltext starten, Kursraum öffnen, `grep -i seccomp /proc/$(pgrep -f QtWebEngineProcess \| head -1)/status`. |
| **Tests der Zentrale** | Im Repo `bonys-netz` mit eigenem venv (`fastapi` u. a.) `pytest` – hier nicht ausgeführt. |
| **x11vnc-CVE** | Im Agent-PC `apt-cache policy x11vnc`, Debian/Kali-Changelog auf CVE-2020-29074 prüfen. |
