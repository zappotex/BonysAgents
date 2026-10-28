# Änderungen

Alle wichtigen Änderungen an Bony's Agents. Ältere Versionen (bis 0.16.3): siehe die
[Releases auf GitHub](https://github.com/zappotex/BonysAgents/releases).

## 0.28.0 – Community-Katalog und Kursportal

### Neu
- **Community-Katalog für Kurspakete.** Unter **Kurse → Kurspakete → „Aus dem Internet …“** zeigt Bony's Agents
  jetzt zusätzlich Kurspakete, die andere Autoren eingereicht haben und die von der Moderation freigegeben wurden.
  Sie sind mit „– Community“ gekennzeichnet. Das ist keine Signatur von Bony's Agents: Vor dem ersten Start zeigt die
  App wie bei jedem fremden Kurspaket die Liste der Skripte. Die Quelle ist im Standard
  **aus**. Mit dem Schalter „Community-Kurspakete anzeigen“ im Katalogfenster schaltest du sie ein, nachdem du einmal
  gelesen und bestätigt hast, was dabei passiert: Die App fragt dann die Katalogliste von `kurse.bony23.de` ab; der
  Server und sein Hoster sehen deine IP-Adresse und Programmname und -version. Bony's Agents speichert nichts davon.
- **Kursportal-Moderation (Kursleiter-Version).** Neuer Eintrag **ⓘ → „Kursportal: Moderation …“**: eingereichte
  Kurspakete ansehen (Prüfbericht, Verlauf, Inhalt als Klartext), freigeben, ablehnen, veröffentlichen und
  zurückziehen – lokal oder online am Kursportal mit einem Moderator-Token. Jede Entscheidung braucht eine
  Begründung und steht unveränderbar (hashverkettet) im Verlauf. Es wird nie etwas aus einem Paket ausgeführt.
- **Annahme-Server für Kurspakete** (Quelltext unter `packaging/kursportal-server/`, läuft nicht in der App): nimmt
  `.bonyspaket`-Dateien nur mit Token an, prüft sie als Daten in einem abgeschotteten Container und veröffentlicht
  erst nach einer menschlichen Entscheidung. Eine Sicherheits-Prüfliste liegt unter
  `docs/dev/pruefliste-kursportal-server.md`.

### Geändert
- Pakete mit der ID eines mitgelieferten Kurspakets werden bei der Einreichung abgelehnt und nie veröffentlicht.
- Handbücher: Abschnitte zum Community-Katalog (Benutzer) und zum Prüfen und Freigeben (Kursleiter).

## 0.27.1 – Sprachmodus beim Starter „Hermes Agent (Sprache)“ repariert

### Behoben
- **„Hermes Agent (Sprache)“ startete ohne Sprachmodus.** Der Starter schickte „/voice on“ und Enter in einem Rutsch;
  Hermes hielt das für eingefügten Text, und das Enter wurde nur eine neue Zeile. Jetzt kommen Befehl und Enter
  getrennt an – Sprachmodus und Vorlesen sind wieder gleich an. Bis zum Update: im Hermes-Fenster einmal Enter drücken.

## 0.27.0 – Spracheingabe und Sprachausgabe

### Neu
- **Sprechen statt tippen – und Antworten zum Anhören.** Die App „Hermes Agent“ bringt jetzt Spracheingabe und
  Sprachausgabe mit, auf Deutsch eingestellt: Erkennung lokal mit Whisper (Modell „base“, schnell), Stimme lokal mit
  Piper (Thorsten), als Alternative Edge (Katja, über das Internet). Sprachmodell und Stimme werden schon beim
  Einrichten geladen. Neue Verknüpfung **„Hermes Agent (Sprache)“**: Sprachmodus und Vorlesen sind gleich an –
  Strg+B drücken, sprechen, Strg+B. Voraussetzung: ein Mikrofon am Rechner, der Agent-PC im eigenen Fenster.
- **Mission Control 0.3.0** für neue Agent-PCs (bisher 0.2.7): Knopf „Sprechen“ im Agenten-Chat und am
  Beschreibungsfeld, Vorlese-Knopf an jeder Antwort, Schalter „Antworten vorlesen“. Sind Hermes und Mission Control
  im Agent-PC, ist der Sprachdienst dafür gleich eingeschaltet.

### Geändert
- Mission Control: Das Feld „Beschreibung“ im Mission Board steht in einer eigenen Zeile und wächst mit dem Text.
- Bestehende Agent-PCs: Reiter „Mission Control“ → „Aktualisieren“; Sprache für Hermes im Terminal mit
  `hermes pm install --extra voice --extra piper --extra edge-tts` (danach `/voice on`).

## 0.26.1 – Mission Control 0.2.7

### Geändert
- **Mission Control 0.2.7** für neue Agent-PCs (bisher 0.2.5):
  - **Hermes-Agenten mit einem Befehl anbinden:** `sudo /opt/bonys-mission-control/scripts/hermes-team.sh add NAME`
    legt das Hermes-Profil an, schaltet dessen Schnittstelle mit eigenem Schlüssel ein und startet den Agenten
    als Dienst (auch nach einem Neustart). `list` zeigt den Stand, `remove` nimmt einen Agenten wieder heraus.
  - Neue Installationen starten mit dem neutralen Beispielteam Atlas, Nova und Scribe.
  - Behoben: Im Agent-PC wurden Missionen, Chat und Profile aus dem Browser abgelehnt („forbidden“), und
    Aufträge an Hermes scheiterten mit Anbietern wie OpenRouter am fest eingestellten Modell.
  - Bestehende Agent-PCs: Reiter „Mission Control“ → „Aktualisieren“.

## 0.26.0 – Mission Control 0.2.5 und Kurspaket „Bony's VPN“

### Neu
- **Kurspaket „Bony's VPN: sicher und privater ins Internet“** (90 Minuten, Anfänger, auch im
  Selbstlern-Modus): Was ein VPN ist und was nicht, WireGuard-Konfiguration bei Proton VPN (kostenlos) oder von
  der FRITZ!Box holen, in Bony's VPN importieren, verbinden, öffentliche Adresse prüfen, Kill-Switch und
  automatisch verbinden, Prüfseiten für DNS und Tracker, privates Fenster mit Tor, Wegwerf-PC – ehrlich:
  privater, nicht anonym. Prüfaufgaben lesen nie einen Schlüssel (nur Dateinamen und `bonys-vpn status`).

### Geändert
- **Mission Control 0.2.5** für neue Agent-PCs (bisher 0.1.0, das nur anzeigen konnte): Missionen anlegen, Agenten
  zuweisen und von „geplant“ bis „fertig“ verfolgen, aus einer Mission einen echten Hermes-Auftrag starten,
  beobachten und stoppen, Einzel- und Teamchat mit den Hermes-Agenten, Erreichbarkeit der Agenten live, Bereich
  „Updates“. Bestehende Agent-PCs: Reiter „Mission Control“ → „Aktualisieren“.

### Behoben
- **Kali Linux:** Das Zeichen „㉿“ in der Eingabezeile des Terminals (`agent㉿name`) erschien als Kästchen – dem
  Kali-Cloud-Abbild fehlt die Schrift dafür. Neue Kali-PCs bekommen jetzt `fonts-noto-cjk`; bestehende:
  `sudo apt install fonts-noto-cjk`.

## 0.25.0 – Kali Linux und Tor Browser

### Neu
- **Kali Linux als Grundsystem:** Beim Erstellen unter „Grundlage“ gibt es jetzt „Neu installieren (Kali Linux)“
  (Kommandozeile: `bonys-agents create NAME --distro kali`). Bony's Agents lädt das aktuelle offizielle
  Cloud-Abbild von kali.download, prüft die SHA256-Prüfsumme (Kali signiert die Cloud-Abbilder nicht), entpackt und
  wandelt es in qcow2 um und richtet es wie gewohnt ein. Eigene Schritte für Kali: Die automatische root-Anmeldung
  des Abbilds (Bildschirm und serielle Konsole) wird abgeschaltet, und am Ende kommt der normale Kernel mit
  Grafiktreibern statt des Cloud-Kernels (alle Kernelteile von Kali, sonst startete GRUB einen Kernel ohne Module).
  Neue App **Kali-Werkzeuge** (nur unter Kali, dort vorausgewählt): `kali-tools-top10` mit Kali-Menü, Wireshark
  ohne root. Nur x86_64 und Xfce – so geprüft; „Desktop hinzufügen“ gibt es für Kali-PCs deshalb nicht. Apps
  können jetzt auch auf Grundsysteme beschränkt werden. Vorlagen, `.bonys`-Dateien und Kurspaket-Rezepte
  (`"distro": "kali"`) merken sich das Grundsystem. Unter Kali geprüft: alle Apps (Docker nimmt dort den
  Debian-Zweig „trixie“ der Docker-Paketquelle, wie in der Kali-Anleitung).
- **Tor Browser:** Das Symbol auf dem Schreibtisch fehlte mit neueren Fassungen von `torbrowser-launcher` (z. B.
  unter Kali), weil deren Startdatei `org.torproject.torbrowser-launcher.desktop` heißt – beide Namen gehen jetzt.
- **Tor Browser** als App (standardmäßig aus, auch über „Programme hinzufügen …“): Debian-Paket
  `torbrowser-launcher` (dafür wird die Komponente „contrib“ eingeschaltet); es lädt beim ersten Start den
  offiziellen Tor Browser von torproject.org und prüft die Signatur. Nur x86_64 – das Tor Project baut für Linux
  kein ARM64; Apps können dafür jetzt auf Architekturen beschränkt werden (im Dialog dann nicht angeboten,
  Kommandozeile mit klarer Meldung).

### Behoben
- **Selbsttest** (`bonys-agents selftest`): Ließ sich das Test-QEMU nicht binnen 10 Sekunden beenden (langsame
  Rechner, z. B. Mac ohne Hardware-Virtualisierung), brach der Selbsttest mit einem Python-Fehler ab, statt sein
  Ergebnis zu melden. Er wartet jetzt bis zu 30 Sekunden und macht danach trotzdem weiter. Das hat den Release-Lauf
  von 0.24.2 einmal aufgehalten.

## 0.24.2 – Leistung ändern: mehr Arbeitsspeicher per Klick

### Neu
- **Leistung ändern …** (beim Arbeitsspeicher eines Agent-PCs): CPU-Kerne und Arbeitsspeicher lassen sich jetzt auch
  nach dem Anlegen ändern. Läuft der Agent-PC, fährt Bony's Agents ihn dafür herunter und startet ihn mit den neuen
  Werten neu. Der Dialog empfiehlt eine Größe (Desktop + n8n/Mission Control + 2 GB Puffer für Browser und Agent);
  liegt ein Agent-PC darunter, steht beim Arbeitsspeicher „⚠ empfohlen: …“. Anlass: Mit genau dem bisherigen
  Minimum (Cinnamon + n8n = 4 GB) blieb Brave beim Start hängen – das Fenster von „Agenten-Apps“ erschien nie.
  Auf der Kommandozeile: `bonys-agents resources NAME [--cpus N] [--ram GB] [--restart]`.

## 0.24.1 – Kurspakete MCP-Server und n8n, Gast-Agent blockiert nicht mehr

### Neu
- **Zwei neue Kurspakete** aus der Reihe „Agenten, MCP-Apps und n8n“ (je 90 Minuten, ab 0.24.0, als Kurs oder im
  Selbstlern-Modus):
  - **„Was ist ein MCP-Server? Hermes bekommt Werkzeuge“** – PdfCraft aus der Liste „Agenten-Apps“ installieren
    (offizielle Quelle, Prüfsumme), mit `hermes mcp add` anmelden und Hermes Beispiel-PDFs zusammenfassen, drehen und
    zusammenfügen lassen. Prüfaufgaben: PdfCraft angemeldet, zusammengefügte PDF mit beiden Rechnungen.
  - **„n8n-Grundlagen: der erste Workflow“** – n8n öffnen, eigenen Telegram-Bot anlegen, Workflow „RSS Feed Trigger
    → Telegram“ bauen, veröffentlichen und mit „Export JSON“ sichern. Die Prüfungen lesen aus der Datenbank von n8n
    nur, ob ein Konto bzw. ein veröffentlichter Workflow mit diesen Knoten existiert – nie Zugangsdaten.

### Behoben
- Ein Agent-PC war manchmal nicht mehr erreichbar („Der Gast-Agent antwortet nicht“), bis Bony's Agents geschlossen
  wurde: Lief der Verbindungsaufbau zum Gast-Agent (oder zum QEMU-Monitor) in einen Timeout – etwa weil gleichzeitig
  ein anderer Befehl lief –, blieb die halb aufgebaute Verbindung offen. QEMU nahm sie später an und blockierte damit
  alle weiteren. Sie wird jetzt sofort geschlossen.

## 0.24.0 – n8n, Software-Center und Agenten-Apps

### Neu
- **n8n im Agent-PC** (Standard: an, auch über „Programme hinzufügen …“): Workflows per Klick, aus dem offiziellen
  Docker-Image `docker.n8n.io/n8nio/n8n` auf dem Docker-Unterbau von Mission Control. Nur unter
  `http://localhost:5678` im Agent-PC erreichbar (nicht im Heimnetz, nicht im Bony-Netz), Daten im Volume
  `n8n_data` (überstehen Updates), Zeitzone des Agent-PCs, startet mit dem Agent-PC; Verknüpfung „n8n“ öffnet es in
  Brave. **Lizenz:** n8n steht unter der *Sustainable Use License* – Quellcode offen, aber keine
  OSI-Open-Source-Lizenz; deshalb steckt n8n nicht in weitergegebenen Vorlagen, frische Vorlagen löschen seine
  Daten. Der Dialog zeigt den Lizenzhinweis und warnt, wenn der Arbeitsspeicher (ca. 1 GB zusätzlich) knapp ist.
- **Software-Center** (Standard: an): GNOME Software mit Flathub – Programme wie GIMP per Klick, ohne Passwort.
  Behebt dabei, dass GNOME Software im Agent-PC „offline“ meldete (NetworkManager verwaltet die Netzwerkkarte
  nicht; jetzt fragt GIO den Kernel). Updates macht weiter „Agent-PC aktualisieren“.
- **„Agenten-Apps“** auf dem Schreibtisch jedes Agent-PCs: offline lesbare Liste von Programmen mit MCP-Server
  (PdfCraft, PhotoCraft, WordCraft, GridCraft, DeckCraft, CADCraft, SolidCraft, offizielle MCP-Server für Dateien
  und Git, Playwright für den Browser) mit Installationsbefehlen von den offiziellen Seiten (neueste Version,
  Prüfsumme) und dem Befehl `hermes mcp add …` mit den echten Pfaden. Nichts wird automatisch installiert. Quelle:
  `agent-apps/agent-apps.yaml`; die Online-Fassung (<https://zappotex.github.io/BonysAgents/agenten-apps/>) baut der
  Pages-Workflow bei jeder Änderung neu – ohne neues Release. Bestehende Agent-PCs: „Programme hinzufügen …“.

### Behoben
- Kurspaket „Einführung in Hermes Agent“ 1.0.1: Die Prüfung „Hermes eingerichtet“ (Lektion 3) meldete bei einem
  frisch installierten Hermes schon „geschafft“ – dessen Standard-Einstellung enthält `provider: "auto"`. „auto“
  gilt jetzt als „noch nicht eingerichtet“; ebenso in der Prüfskript-Vorlage des Kurspaket-Editors.

## 0.23.0 – Kurspakete

### Neu
- **Kurspakete** (`.bonyspaket`): fertige Lerninhalte – Lektionen mit Anleitung, Prüfaufgaben, Quiz, Ablaufplan
  und Handout. Fenster „Kurse“ → Reiter **„Kurspakete“**: Bibliothek mit Import (Datei, Drag & Drop), Export und
  „Aus dem Internet …“ (Repository [bonys-agents-kurspakete](https://github.com/zappotex/bonys-agents-kurspakete),
  nur HTTPS, Größe und SHA-256 geprüft). Format: `docs/kurspaket-format.md`.
- **Selbstlern-Modus** (beide Editionen): „Durcharbeiten“ richtet einen eigenen Agent-PC nach dem Rezept des Pakets
  ein und öffnet daneben das Fenster **„Anleitung“** – Weiter/Zurück, Springen, **„Prüfen“** (Skripte laufen nur im
  Agent-PC über den Gast-Agent, Ergebnis nur „geschafft / noch nicht“), Quiz und **„Zurücksetzen“** auf den
  Startzustand der Lektion (qcow2-Schnappschuss). Fremde Pakete zeigen vor dem ersten Start ihre Skripte;
  mitgelieferte und signierte gelten als geprüft.
- **Kurspaket im Kurs:** beim Anlegen eines Bony-Netz-Kurses oder in der Kursansicht wählen – die Teilnehmer bekommen
  es automatisch und öffnen es mit „Anleitung“; die Kursansicht zeigt je Teilnehmer Lektion und „geschafft / noch
  nicht“ (braucht einen Bony-Netz-Server ab 0.2.0). Ebenso bei der Schulung im eigenen Netz („Im Netzwerk
  freigeben“ → „Kurspaket“).
- **Kurspaket-Editor** (Kursleiter-Version): anlegen, bearbeiten, duplizieren; Markdown mit Vorschau, Bildschirmfoto
  des Agent-PCs, Prüfskript-Vorlagen („Datei existiert“, „Dienst läuft“, „Hermes eingerichtet“), Startskript aus
  einem Ordner im Agent-PC, Quiz; Speichern und Export nur ohne Zugangsdaten (Schlüssel, Tokens, Passwörter,
  E-Mail, Telefon, IBAN); PDF von Ablaufplan und Handout; **„Kurspaket prüfen“** – auch in einem Test-Agent-PC.
- **Mitgeliefert:** „Einführung in Hermes Agent“ (2 Stunden, 9 Lektionen mit Quiz und Prüfaufgaben, Standardweg
  `hermes setup` → Nous → kostenloses Modell) und fünf Entwürfe bis zur Stufe Experte. Die Release-Aktion signiert
  sie und hängt sie als `.bonyspaket` an.
- Handbücher: Kapitel „Kurspakete“ (beide), Glossar, neue Bildschirmfotos. Der Beispielkurs hat nur noch eine
  Quelle – das Kurspaket.

### Geändert
- Baustein `bony_netz` 0.2.0 (Kurspaket hoch-/herunterladen, Fortschritt melden).

## 0.22.1 – Handbücher, lesbare Tooltips

### Neu
- **Handbücher als PDF** (`docs/handbuch/`): Benutzerhandbuch, Kursleiter-Handbuch und Beispielkurs „Einführung in
  Hermes Agent“ (Ablaufplan für die Kursleitung und Handout für Teilnehmer), mit Bildschirmfotos. Die Release-Aktion
  hängt sie an jedes Release. Die Bildschirmfotos entstehen mit einem Befehl neu (`docs/handbuch/erstellen.sh`) –
  in einem Vorführmodus mit erfundenen Beispieldaten, ohne Server, Netz oder echte Agent-PCs; eine Prüfung per
  Texterkennung stellt sicher, dass keine Daten des Rechners in den Bildern stehen.
- Menü ⓘ → „Hilfe (Anleitung)“ öffnet das Benutzerhandbuch dieser Version (Kursleiter-Version zusätzlich
  „Kursleiter-Handbuch“).

### Behoben
- **Hilfetexte (Tooltips) unlesbar:** Auf Systemen mit hellem Theme (z. B. Linux Mint) war die Schrift schwarz auf
  dunklem Grund. Tooltips, Kontextmenüs, Meldungsfenster, Dateiauswahl, Tabellen/Listen und deaktivierte Elemente
  haben jetzt feste, kontrastreiche Farben, unabhängig vom System-Theme.
- **Hilfe-Funktion:** Die Rückfrage „Hilfe-Anfrage des Kursleiters“ schnitt den Erklärtext unten ab („Nur ansehen“ /
  „Ansehen und bedienen“, „… endet nach spätestens 30 Minuten“). Fenster und Hinweis „Hilfe läuft“ sind jetzt so hoch
  wie der umgebrochene Text.

## 0.22.0 – Hilfe-Funktion über das Bony-Netz

### Neu
- **Hilfe im Kurs über das Bony-Netz.** Der Kursleiter kann sich während eines laufenden Kurses den Agent-PC eines
  Teilnehmers ansehen und bedienen – **nur nach ausdrücklicher Zustimmung, jedes Mal neu**. Im Kursraum steht bei
  jedem Teilnehmer „Helfen“ (auch in der Kursansicht), Teilnehmer können mit „🆘 Hilfe anfordern“ darum bitten.
  Beim Teilnehmer erscheint eine deutliche Rückfrage: „Nur ansehen“, „Ansehen und bedienen“ oder „Ablehnen“ (ohne
  Antwort nach 60 Sekunden abgelehnt). Solange der Kursleiter zusehen kann, steht über allen Fenstern ein Hinweis
  mit **„Beenden“**, der sofort trennt; die Hilfe endet auch, wenn der Kurs pausiert oder beendet wird, der
  Kursraum verlassen wird oder nach spätestens 30 Minuten.
- Im Agent-PC läuft dafür x11vnc (aus Debian, bei neuen Agent-PCs gleich dabei, bei älteren beim ersten Mal
  nachinstalliert) – nur auf der Adresse im Bony-Netz, mit Einmal-Passwort, für genau eine Verbindung, bei „Nur
  ansehen“ ohne Eingaben. Die App des Kursleiters verbindet sich nur mit der Adresse, die die Zentrale für genau
  diesen Agent-PC nennt. Angezeigt wird in einem eigenen Fenster (noVNC); wo der eingebaute Browser fehlt (Linux auf
  ARM), mit TigerVNC.
- Beim Kursstart prüft die Kursleiter-Version, ob dieser Rechner im Bony-Netz ist, und bietet sonst Bony's VPN an
  (Windows/macOS: Hinweis auf die Tailscale-App).

## 0.21.0 – Bony-Netz: Agent-PCs im Netz, Kurse und Kursraum

### Neu
- **Bony-Netz (erster Schritt).** Menü → „Bony-Netz …“: Schalter „Bony-Netz verwenden“ (standardmäßig aus – dann
  nimmt die App keinen Kontakt zum Server auf und verhält sich wie bisher), Server wählen und prüfen
  (Vorschlag `https://zentrale.bony23.de`), Instanz anlegen oder löschen, Zustand der Verbindung. Die Anmeldung
  teilt sich Bony's Agents mit Bony's VPN (`~/.config/bonys-netz/konto.json`, nur für dich lesbar). Agent-PCs
  und Kurse kommen in den nächsten Schritten.
- **Agent-PCs im Bony-Netz.** Ist das Bony-Netz an und eine Instanz angemeldet, gibt es beim Erstellen das
  Häkchen „Mit dem Bony-Netz verbinden“ (standardmäßig an). Der Agent-PC installiert dann beim ersten Start
  Tailscale aus der offiziellen Paketquelle und tritt dem Netz der Instanz bei (Protokoll im Agent-PC:
  `/var/log/bony-netz-beitritt.log`). Der einmal nutzbare Geräteschlüssel wird erst direkt vor dem Start geholt und
  geht nur über die Einrichtungsdaten in den Agent-PC. Ohne Internet oder bei erreichter Gerätegrenze wird der
  Agent-PC ganz normal ohne Netz erstellt, mit Hinweis. In der Liste zeigt ein kleines Netz-Symbol „im Netz /
  offline / nicht verbunden“ (abgefragt höchstens alle 30 Sekunden, nur bei sichtbarem Fenster). Beim Löschen wird
  der Agent-PC auch aus dem Netz entfernt; ist der Server nicht erreichbar, wird trotzdem gelöscht, mit Hinweis.
  Nachträglich: Rechtsklick in der Liste → „Mit dem Bony-Netz verbinden“ (über den Gast-Agent, sonst SSH).
  Kommandozeile: `create … --bony-netz`. Vorlagen enthalten nie die Tailscale-Anmeldung – jeder Klon tritt selbst bei.
- **Kurse über das Bony-Netz.** Der Knopf „Kurs beitreten“ heißt jetzt **„Kurse“** und öffnet ein Fenster mit
  „Teilnahme“ (beide Versionen: Kurscode, Agent-PC wählen, Anzeigename, „Meine Kurse“, „Kurs verlassen …“) und in
  der Kursleiter-Version zusätzlich „Kursleitung“ (Kursleiter-Code einlösen, „Neuer Kurs …“ mit Code-Gültigkeit 1–60
  Tage, Kursliste mit „Beendete anzeigen“, Kursansicht mit großem Code und „Kopieren“, Starten/Pausieren/Beenden,
  Teilnehmertabelle mit Netzadresse, „Entfernen …“; Abfrage alle 15 Sekunden, solange sichtbar). Nur solange ein Kurs
  läuft, erreicht der Kursleiter die gewählten Agent-PCs der Teilnehmer. Der eigene Rechner (über Bony's VPN im Netz)
  steht nie zur Auswahl. Beginnt ein Kurs, an dem du teilnimmst, meldet das die Statuszeile (höchstens jede Minute
  gefragt). Die Schulung im eigenen Netz bleibt unverändert: „Kurse“ → „Schulung im Netzwerk beitreten …“.
- **Kursraum mit Bildschirm, Ton, Kamera und Chat.** Solange ein Kurs läuft: Kursansicht → „Kursraum öffnen“
  (Kursleiter) bzw. „Kurse“ → „Kursraum betreten“ (Teilnehmer). Ein eigenes Fenster zeigt groß den Bildschirm des
  Kursleiters (ohne Freigabe seine Kamera), darunter die eingeschalteten Kameras (wer spricht, ist grün umrandet),
  rechts die Teilnehmerliste mit Mikrofon und ✋ sowie den Chat. Unten: Mikrofon, Kamera, Hand heben/senken,
  „Kursraum verlassen“ – beim Kursleiter zusätzlich „Bildschirm teilen“ (Bildschirm oder einzelnes Fenster wählen)
  und „Sprechen nur nach Freigabe“. Teilnehmer kommen mit Mikrofon und Kamera aus, der Kursleiter mit Mikrofon an.
  Der Kursleiter kann Teilnehmer stumm schalten, ihnen das Sprechen erlauben und sie aus dem Raum nehmen.
  Der Chat wird nirgends gespeichert. Bricht die Verbindung ab, zeigt der Kursraum „Verbindung wird
  wiederhergestellt …“; ist der Kurs beendet oder pausiert oder die Eintrittskarte (6 Stunden) abgelaufen, steht da
  warum, mit „Erneut eintreten“. Technik: LiveKit (`livekit-client` 2.22.3, Apache-2.0) in einem eingebetteten
  Browser (Qt WebEngine); die Seite gehört zur App, Kamera, Mikrofon und Bildschirmaufnahme bekommt nur sie.
  Bildschirm teilen geht unter Linux nur in einer X11-Sitzung (unter Wayland zeigt der Knopf einen Hinweis).
  Im Paket für Linux auf ARM (arm64, z. B. Raspberry Pi) gibt es den Kursraum noch nicht – dort fehlt ein
  passender eingebetteter Browser für Debian 12/Ubuntu 22.04; „Kursraum betreten“ sagt das.
  Das Programm wird dadurch etwa 290 MB größer (Qt WebEngine). Unter macOS fragt das System beim ersten Mal nach
  Kamera, Mikrofon und Bildschirmaufnahme; unter Ubuntu ab 24.04 bringt das .deb ein AppArmor-Profil mit, das der
  Sandbox von Qt WebEngine eigene Namensräume erlaubt.

### Behoben
- **Bony-Netz: Beitritt scheiterte bei Agent-PCs ohne Tailscale** („bei der Einrichtung ist etwas schiefgegangen“,
  im Protokoll `"Debian GNU/Linux" contains invalid character ' '`). Baustein `bony_netz` 0.1.1. Betroffene
  Agent-PCs: Rechtsklick → „Mit dem Bony-Netz verbinden“.

## 0.20.0 – Durchsicht vor 1.0: Sicherheit, Zuverlässigkeit, Lizenzen

### Sicherheit
- **Agent-PCs kommen nicht mehr an die Steuerung von QEMU.** Bisher lauschten QEMU-Steuerung (QMP), Gast-Agent
  und SPICE (ohne Passwort) an 127.0.0.1 – und das ist aus jedem Agent-PC über 10.0.2.2 erreichbar. Ein Programm
  im Agent-PC (z. B. ein umgelenkter KI-Agent) hätte darüber Befehle auf deinem Rechner ausführen können. Unter
  Linux und macOS laufen diese Kanäle jetzt über Unix-Sockets in einem Ordner, den nur dein Benutzer öffnen darf.
  Unter Windows sind sie über TLS verschlüsselt und nur mit einem Zertifikat erreichbar, das Bony's Agents bei
  jedem Start neu erzeugt (Ordner `.steuerung` im Agent-PC-Ordner). SPICE an einem Port (Heimnetz, Windows) gibt
  es nur noch mit Passwort. Laufende Agent-PCs einmal neu starten.
- **Festplatten aus fremden Quellen können keine Dateien deines Rechners mehr lesen.** Eine präparierte
  qcow2-Festplatte (in einer `.bonys`-Datei, einer alten Vorlagen-Datei oder auf einem fremden Laufwerk) konnte
  auf eine beliebige Datei deines Rechners zeigen, z. B. einen SSH-Schlüssel – der Agent-PC hätte sie als
  Festplatte gesehen. Bony's Agents prüft den Kopf jeder solchen Festplatte jetzt selbst, bevor QEMU oder
  qemu-img sie öffnen: keine externe Datendatei, beim Import keine Backing-Datei, beim Start nur Vorlagen im
  qcow2-Format ohne Protokoll-Angaben wie `json:` oder `nbd:`.
- **Präparierte Einstellungsdateien werden abgelehnt.** `vm.json` und `template.json` (auch von Laufwerken, die
  Bony's Agents automatisch erkennt, und aus alten `.bonys-template`-Dateien) werden beim Laden genau geprüft:
  Typ und erlaubte Werte jedes Felds, z. B. Name, Benutzername, Tastatur, Ports und Desktop. Ein Agent-PC
  oder eine Vorlage mit unzulässigen Angaben erscheint nicht in der Liste. Remmina-Profile, `.rdp`- und
  SPICE-Verbindungsdateien nehmen keine Zeilenumbrüche mehr an – darüber hätte sich z. B. ein Befehl vor dem
  Verbinden einschleusen lassen.
- **Kurs aus der Suche nur nach Vergleich des Fingerabdrucks.** Wer „Schulung beitreten“ oder „Hilfe anfordern“
  über die Suche im Netz nutzt, muss den Fingerabdruck jetzt immer mit dem Bildschirm des Kursleiters
  vergleichen. Bisher galt der Fingerabdruck aus der Suche als geprüft – im WLAN kann ihn aber jeder fälschen
  und sich als Kursleiter ausgeben. Ohne Rückfrage gilt nur der Link bzw. QR-Code des Kursleiters.
- **Updates über die Aktualisierungsverwaltung (APT) sind lückenlos geprüft.** Die Paketquelle übernimmt ein
  Paket nur noch, wenn die minisign-Signatur des Release stimmt (derselbe Schlüssel, den die App prüft), das
  Paket in der signierten Prüfsummenliste steht und Name und Version zum Projekt passen. Ein Release wird nur
  noch veröffentlicht, wenn alle Tests grün sind und die Signatur gelingt.

### Lizenzen
- **Feste Versionen für alle Pakete.** Die fertigen Programme werden nur noch mit festgelegten Versionen und
  Prüfsummen gebaut (`packaging/requirements-build.txt`): nachvollziehbar, und eine manipulierte neue Version auf
  PyPI landet nicht unbemerkt im Release. `THIRD-PARTY-LICENSES` nennt jetzt genau diese Versionen mit Links auf
  ihre Quelltexte (Qt, PySide6).
- **pycdlib (LGPL-2.1) ist austauschbar mitgeliefert.** Die Bibliothek liegt jetzt als lose Quelltext-Dateien im
  Programmordner (`_internal/pycdlib/`) statt im Archiv der Programmdatei – wie es die LGPL verlangt. Der Paketbau
  prüft das.
- **Alle Lizenztexte liegen bei.** Jedes Paket enthält jetzt den Ordner `licenses` mit den Lizenztexten aller
  tatsächlich mitgelieferten Teile – beim Bauen aus dem Inhalt gesammelt: Python (mit den Drittteilen seines
  Builds), OpenSSL (Windows/macOS), Qt und alle seine Drittkomponenten (harfbuzz, PCRE2, libpng …), ICU, jedes
  Python-Paket und unter Linux jede gebündelte Systembibliothek (z. B. OpenSSL, Kerberos, libjpeg). Bisher fehlten
  viele davon, und die Liste nannte teils Bibliotheken, die gar nicht dabei waren.

### Verbessert
- **Update-Suche nur nach Zustimmung.** Beim ersten Start fragt Bony's Agents, ob es einmal am Tag bei GitHub nach
  einer neuen Version suchen darf. Neuer README-Abschnitt „Datenschutz“: was wann wohin geht (keine Telemetrie).
- **README:** versionsneutrale Dateinamen (mit Kursleiter-Version) und eine Anleitung für die Windows-Warnung
  „Der Computer wurde durch Windows geschützt“ (→ „Weitere Informationen“ → „Trotzdem ausführen“).
- **Alles auf Deutsch.** Auch die Knöpfe und Menüs, die Qt selbst mitbringt („Ja/Nein“, „Abbrechen“, „Kopieren/
  Einfügen“ im Kontextmenü), sind jetzt deutsch.
- **Löschen nur mit Absicht.** Beim Löschen eines Agent-PCs oder einer Vorlage ist „Behalten“ voreingestellt –
  ein versehentliches Enter löscht nichts mehr.
- **Fehlerprotokoll.** Unerwartete Fehler der Desktop-App landen in `fehler.log` im Datenordner und werden kurz
  gemeldet, statt still zu verschwinden (z. B. ein Knopf, der nichts tut). Startet die App gar nicht, steht der
  Grund ebenfalls dort.
- **Einrichtung „fertig mit Fehlern“ statt still „fertig“.** Scheitert bei der Ersteinrichtung ein Schritt (z. B.
  die Installation einer App oder die Übernahme der WireGuard-Konfiguration), zeigt Bony's Agents das jetzt im
  Hauptfenster und bei `bonys-agents status` an. Die App gilt dann nicht als installiert, „Programme hinzufügen …“
  bietet sie wieder an. Jede App wird nach der Installation geprüft, Downloads von Fremd-Installern haben ein
  Zeitlimit mit Wiederholung, und ein hängender Schritt wird nach 4 Stunden abgebrochen statt ewig zu warten.
- **Nach einem Absturz kein falscher Agent-PC mehr „laufend“.** Ob ein Agent-PC läuft, prüft Bony's Agents jetzt
  auch über die Festplatte in der Befehlszeile von QEMU und die Startzeit. Bisher konnte nach Absturz oder
  Stromausfall die alte Prozessnummer zum QEMU eines *anderen* Agent-PCs gehören – „Ausschalten“ hätte dann den
  anderen hart beendet.
- **Verschieben auf ein anderes Laufwerk ist sicher gegen Stromausfall und zu frühes Abziehen.** Die Kopie wird
  vollständig auf das Ziel geschrieben (`fsync`) und ihre Festplatte geprüft (`qemu-img check`), bevor das
  Original gelöscht wird. Bisher konnte der Agent-PC verloren gehen, wenn das Laufwerk direkt danach abgezogen
  wurde.
- **Formatversion für Agent-PCs und Vorlagen.** `vm.json` trägt jetzt eine Formatversion. Einstellungen, die
  eine neuere Version von Bony's Agents ergänzt hat, bleiben beim Speichern erhalten (bisher gingen sie still
  verloren, z. B. mit einer SSD an einem Schulungs-PC mit älterer Version). Stammt ein Agent-PC oder eine
  Vorlage aus einer neueren Formatversion, zeigt Bony's Agents sie nur an und bittet um ein Update, statt sie
  zu verändern. `vm.json` wird außerdem atomar geschrieben – ein Absturz beim Speichern hinterlässt keine halbe
  Datei mehr.
- **Einstellungsdateien gehen nicht mehr verloren.** `vm.json`, `runtime.json` und die Programmeinstellungen
  (`settings.json`) werden atomar geschrieben; von `vm.json` und `settings.json` bleibt die vorige Fassung als
  `.bak`, die bei einer kaputten Datei automatisch genutzt wird. Eine unlesbare `settings.json` wird nicht mehr
  still durch leere Einstellungen ersetzt, sondern aufgehoben. Ein Agent-PC mit unlesbarer `vm.json` heißt jetzt
  „beschädigt“ statt „nicht verfügbar“ (es fehlt kein Laufwerk).

## 0.19.0 – Zwei Editionen (Bony's Agents und Bony's Agents Kursleiter), neues Hintergrundbild

### Neu
- **Zwei Editionen aus einem Quellcode** (siehe [docs/editionen.md](docs/editionen.md)):
  **Bony's Agents** für alle, die Agent-PCs nutzen, und für Teilnehmer von Schulungen (Kurs beitreten, Vorführung
  im Browser öffnen, Hilfe anfordern), **Bony's Agents Kursleiter** zusätzlich mit Vorlage im Netzwerk freigeben,
  Vorführen und Hilfe-Anfragen annehmen. Teilnehmer brauchen nur die normale Version.
- In der normalen Version fehlen die Kursleiter-Funktionen ganz – kein Server-Code und kein noVNC im Paket. Unter
  ⓘ und im „Über“-Fenster steht dezent „Du möchtest selbst Schulungen geben? → Bony's Agents Kursleiter“.
- Wechsel zwischen den Editionen in beide Richtungen: einfach die andere Version installieren (.deb per Doppelklick
  oder apt, Setup.exe, .dmg). Agent-PCs, Vorlagen, Bibliotheken und Einstellungen bleiben. Updates bleiben in der
  eigenen Edition.
- „Über“, `bonys-agents --version` und `bonys-agents doctor` zeigen die Edition.
- **Kurs-Protokoll mit Version:** Passen Kursleiter und Teilnehmer nicht zusammen, sagt Bony's Agents verständlich,
  wer aktualisieren sollte (Teilnehmer mit 0.17/0.18 bleiben kompatibel).

- **Neues Hintergrundbild für Agent-PCs** (beide Editionen, alle Desktops und der Anmeldebildschirm; das Bild im
  Programmfenster bleibt): skaliert und unverzerrt, die Randfarbe stammt aus dem Bild. Bestehende Agent-PCs:
  Detailansicht → „Hintergrundbild aktualisieren“ bzw. `bonys-agents wallpaper NAME [--force]` – umgestellt wird
  nur, wenn noch das alte Standardbild aktiv ist; ein selbst gewähltes Bild bleibt (sonst Rückfrage). Agent-PCs aus
  alten Vorlagen bzw. `.bonys`-Dateien bekommen es beim ersten Start automatisch, sofern sie das alte hatten.

### Geändert
- `bonys-agents share` und `bonys-agents present` gibt es nur noch in der Kursleiter-Version; die normale Version
  erklärt das (Rückgabe 2).
- Pakete: `bonys-agents` und `bonys-agents-kursleiter` (.deb, beide in der APT-Paketquelle),
  `BonysAgents-Setup-….exe` und `BonysAgents-Kursleiter-Setup-….exe`, je zwei .dmg pro Mac-Chip.

## 0.18.0 – Schulungen: Live-Vorführung und Hilfe-Modus

### Neu
- **Vorführen:** Den Bildschirm eines laufenden Agent-PCs live im Browser der Teilnehmer zeigen (Laptop, Tablet,
  Handy – dort muss nichts installiert sein). Detailansicht → „Vorführen …“ bzw. `bonys-agents present NAME`.
  Code, Adressen, QR-Code (Code schon eingetragen), Fingerabdruck, Liste der Zuschauer, „Pause“ (alle sehen nur
  „Gleich geht's weiter“ – kein Bild, bis „Weiter“), „Zuschauer entfernen“, „Vorführung beenden“. Qualität und
  Bildrate wählbar (Standard: fürs WLAN), höchstens 30 Zuschauer (einstellbar), endet nach 90 Minuten
  (einstellbar) und wenn der Agent-PC ausgeschaltet wird. Vor dem Start der Hinweis, vor Passwörtern und Tokens
  zu pausieren.
- **Nur ansehen – im Server erzwungen:** Bony's Agents prüft jede Nachricht vom Browser zum Agent-PC und lässt
  nur durch, was für das Bild nötig ist. Tastatur, Maus, Zwischenablage und Steuerbefehle der Zuschauer kommen nie
  an (die Browser-Ansicht – noVNC – läuft zusätzlich im Nur-ansehen-Modus).
- **Teilnehmer im Browser:** Name und Code eingeben, Bild passt sich dem Fenster an, Vollbild, Statusanzeige
  (verbunden/Pause/beendet), verbindet sich nach kurzen WLAN-Aussetzern selbst wieder. „Kurs beitreten“ in
  Bony's Agents zeigt laufende Vorführungen ebenfalls an und öffnet sie im Browser.
- Bildrate sinkt automatisch bei vielen Zuschauern oder hoher Rechenlast.
- **Hilfe-Modus:** Teilnehmer wählen beim Agent-PC „Hilfe anfordern …“, der Kursleiter sieht die Anfragen unter
  „Kursleitung: Hilfe-Anfragen …“ (mit Hinweiston). Ansehen erst nach Zustimmung des Teilnehmers, Steuern nur nach
  einer zweiten Zustimmung; „Nur ansehen“ und „Beenden“ wirken sofort, gut sichtbarer Hinweis beim Teilnehmer
  (und als Benachrichtigung im Agent-PC). Die Verbindung geht vom Teilnehmer aus (klappt hinter Firewall/NAT und
  über VPN), nur der Agent-PC ist sichtbar, die Zwischenablage nie. Protokoll beim Teilnehmer ohne Bildinhalte.
- Vorführung und Hilfe-Schalter nutzen einen gemeinsamen Kurs-Server mit einem Code; das Vorführen-Fenster ist
  nicht mehr modal.

### Geändert
- Agent-PCs stellen ihren Bildschirm zusätzlich **nur lokal** per VNC bereit (Unix-Socket, den nur dein Benutzer
  öffnen darf; unter Windows 127.0.0.1) – Voraussetzung fürs Vorführen. Agent-PCs, die noch mit einer älteren
  Version laufen, einmal neu starten („Jetzt neu starten“ im Vorführen-Fenster).
- Adressen bei Freigabe und Vorführung: Docker- und VM-Netze dieses Rechners werden nicht mehr angezeigt,
  VPN-Adressen (z. B. WireGuard über den NetworkManager) als „VPN“ gekennzeichnet.
- Der Freigabe-Code steht wieder groß im Freigabe-Fenster.
- Mitgeliefert: noVNC 1.7.0 (MPL-2.0), beim Bauen aus dem offiziellen Release mit Prüfsumme geholt.

## 0.17.1

### Behoben
- Windows bei 150 % Anzeigegröße: Das Hauptfenster ließ sich nicht mehr auf 800 Pixel Breite verkleinern. Der
  Knopf heißt jetzt kürzer **„Kurs beitreten“** (das Fenster weiterhin „Schulung beitreten“).
- „Vorlage importieren“: Ein langer Dateipfad machte das Fenster breiter als kleine Bildschirme – er wird jetzt
  in der Mitte gekürzt, und „Rezept nutzen …“ steht jetzt beim Architektur-Hinweis statt in der Knopfzeile.

## 0.17.0 – Schulungen: Agent-PCs weitergeben

### Neu
- **Vorlagen als eine Datei weitergeben** (`.bonys`): „Vorlagen“ → „Weitergeben (.bonys) …“ bzw.
  `bonys-agents template export`. Die Datei enthält die komprimierte Festplatte und eine Beschreibung
  (Ersteller, Version, Programme mit Versionen, Desktop, Debian, Architektur, empfohlene Ausstattung, Prüfsumme),
  optional ein Vorschaubild.
- **Frisch-Prüfung vor jedem Export:** Eine Kopie der Vorlage startet ohne Netz und wird nach Resten durchsucht
  (API-Schlüssel und Tokens, WireGuard-Konfiguration, SSH-Schlüssel, Browser-Profile, Telegram-Sitzung,
  Geheimnisse von Mission Control, Befehlsverläufe). Funde werden nur mit Art und Ort angezeigt und blockieren den
  Export, bis sie in der Kopie bereinigt sind. Danach wird noch einmal streng geprüft.
- **Lizenzen beachtet:** Claude Code und Obsidian werden nicht mitgegeben, sondern beim Empfänger aus der
  offiziellen Quelle installiert („Programme hinzufügen“ schlägt sie vor).
- **Importieren** per Knopf oder Drag & Drop: Inhalt ansehen, Prüfsumme wird geprüft, auf Wunsch gleich einen
  Agent-PC daraus erstellen. Jeder Agent-PC bekommt beim ersten Start eine eigene Identität (Maschinen-ID,
  SSH-Hostschlüssel, Passwort, Geheimnisse von Mission Control).
- **Andere Architektur** (z. B. amd64-Vorlage auf einem Mac mit Apple-Chip): deutliche Warnung und das „Rezept“ –
  derselbe Desktop mit denselben Programmen wird mit dem passenden Debian-Image neu eingerichtet.
- **Im Netzwerk freigeben:** „Vorlagen“ → „Im Netzwerk freigeben …“ bzw. `bonys-agents share`. Verschlüsselt mit
  eigenem Zertifikat je Freigabe, Zugriff nur mit Code (z. B. `4711-BONY`), QR-Code, nur lesend, endet von selbst,
  Teilnehmerliste mit Fortschritt, Warteschlange bei vielen gleichzeitigen Downloads.
- **Schulung beitreten:** Knopf im Hauptfenster bzw. `bonys-agents join`. Findet Freigaben im selben Netz
  automatisch (mDNS), im VPN per Adresse und Code oder Link aus dem QR-Code. Abgebrochene Downloads werden
  fortgesetzt, die Prüfsumme wird geprüft.

### Geändert
- Beim Erstellen einer Vorlage werden jetzt auch die SSH-Schlüssel von root (`/root/.ssh`) entfernt.
- Das alte Format `.bonys-template` lässt sich weiter importieren, exportiert wird nur noch `.bonys`.
- Neue Abhängigkeit: `qrcode` (BSD-Lizenz) für den QR-Code der Freigabe.
