# Änderungen

Alle wichtigen Änderungen an Bony's Agents. Ältere Versionen (bis 0.16.3): siehe die
[Releases auf GitHub](https://github.com/zappotex/BonysAgents/releases).

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
