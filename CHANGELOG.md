# Änderungen

Alle wichtigen Änderungen an Bony's Agents. Ältere Versionen (bis 0.16.3): siehe die
[Releases auf GitHub](https://github.com/zappotex/BonysAgents/releases).

## Unveröffentlicht

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

### Verbessert
- **Formatversion für Agent-PCs und Vorlagen.** `vm.json` trägt jetzt eine Formatversion. Einstellungen, die
  eine neuere Version von Bony's Agents ergänzt hat, bleiben beim Speichern erhalten (bisher gingen sie still
  verloren, z. B. mit einer SSD an einem Schulungs-PC mit älterer Version). Stammt ein Agent-PC oder eine
  Vorlage aus einer neueren Formatversion, zeigt Bony's Agents sie nur an und bittet um ein Update, statt sie
  zu verändern. `vm.json` wird außerdem atomar geschrieben – ein Absturz beim Speichern hinterlässt keine halbe
  Datei mehr.

## 0.19.0 – Zwei Editionen (Bony's Agents und Bony's Agents Kursleiter), neues Hintergrundbild (noch nicht veröffentlicht)

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
