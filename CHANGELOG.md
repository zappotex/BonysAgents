# Änderungen

Alle wichtigen Änderungen an Bony's Agents. Ältere Versionen (bis 0.16.3): siehe die
[Releases auf GitHub](https://github.com/zappotex/BonysAgents/releases).

## Unveröffentlicht

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
