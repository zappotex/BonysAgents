# Plan: Kursportal und sichere Kurspakete

Stand: 28.10.2026
Status: Schritt 1 (Intake, `kurspaket_portal.py`), Schritt 2 (Moderation mit hashverkettetem Verlauf, `kurspaket_moderation.py`) und Schritt 3 (lokaler Moderationsdialog `gui/moderation_dialog.py`, nicht ins Hauptfenster eingebunden) lokal fertig, 19 Tests grün, nicht committet; noch keine Portal-Funktion veröffentlicht. Die Rubrik-Prüfung entfällt, weil Pakete keine Rubrik haben.

## Ziel

Bony's Agents soll später ein Kursportal erhalten, in dem Nutzer eigene `.bonyspaket`-Dateien vorbereiten und nach einer mehrstufigen Prüfung zur Veröffentlichung einreichen können.

Das Portal darf niemals so tun, als sei eine automatische Prüfung unfehlbar. Die Entscheidungskette lautet:

1. technische Vorprüfung
2. Sicherheits- und Geheimnisprüfung
3. Inhalts- und Metadatenprüfung
4. automatische Freigabe nur bei eindeutig unkritischen Paketen
5. menschliche Moderation bei Grenzfällen
6. Veröffentlichung erst nach einem expliziten Freigabestatus

## Sicherheitsgrenzen

- Uploads werden nur als Daten behandelt; kein Skript, keine Startdatei und kein Paketbestandteil läuft auf dem Portalserver.
- Paketdateien werden vor dem Entpacken anhand von Pfaden, Dateitypen, Größen, Eintragszahl, Tiefe und Sonderdateien geprüft.
- Das bestehende `bonys_agents.kurspaket` bleibt die maßgebliche Format- und Entpackprüfung.
- Skripte werden im Portal nur erkannt, aufgelistet und statisch geprüft; eine echte Ausführung bleibt ausschließlich dem isolierten Agent-PC vorbehalten.
- Zugangsdaten, Tokens, private Schlüssel, persönliche Daten und Credentials führen mindestens zu `rejected` oder `needs_review`.
- Ablehnungsgründe werden nachvollziehbar gespeichert, aber keine Geheimniswerte in Meldungen oder Logs ausgegeben.
- Jede eingereichte Fassung erhält eine unveränderliche Prüfsumme und eine eigene Versions-/Submission-ID.
- Veröffentlichung und Rücknahme benötigen eine menschliche Moderationsentscheidung.

## Geplanter Statusautomat

```text
uploaded
  -> scanning
  -> needs_review
  -> approved
  -> published

scanning -> rejected
needs_review -> rejected | approved
published -> withdrawn
```

`published` ist kein Ersatz für eine fachliche oder rechtliche Garantie. `withdrawn` bleibt in der Historie erhalten.

## Submission-Metadaten

Eine Einreichung soll mindestens enthalten:

- opaque `submission_id`
- Paket-ID und Paketversion aus `paket.json`
- SHA-256 der Originaldatei
- Dateigröße
- Einreichungszeitpunkt
- technische Prüfergebnisse
- erkannte Skripte und externe HTTPS-Links
- Geheimnis-/Personendatenbefund ohne Fundwerte
- Moderationsstatus und Begründung
- Autorreferenz, intern; keine öffentliche E-Mail-Anzeige als Standard

Originaldateien und Prüfergebnisse werden getrennt vom öffentlichen Katalog gespeichert. Der öffentliche Katalog enthält nur freigegebene, bereinigte Metadaten und den Download-Fingerabdruck.

## Erste vertikale Scheibe

Nicht sofort Registrierung, E-Mail, Passwort-Reset und öffentliche Uploads bauen. Der erste Entwicklungsblock ist eine lokale, testbare Intake-Schicht:

1. `.bonyspaket` als Eingabe annehmen
2. Originaldatei in einem temporären Arbeitsbereich unter Größenlimit verwahren
3. `kurspaket.entpacken()` in ein neues Verzeichnis ausführen
4. `kurspaket.laden()` und `geheimnisse_pruefen()` ausführen
5. Skripte, Bilder, Links und Paketmetadaten erfassen
6. einen deterministischen Prüfbericht ohne Geheimniswerte erzeugen
7. den Status `approved`, `needs_review` oder `rejected` begründen

Die Scheibe bleibt zunächst ohne Webserver und ohne Benutzerkonten. Sie ist die gemeinsame Sicherheitsbasis für späteren Upload, Moderation und Katalog.

## Erkennung für den ersten Block

Automatisch ablehnen:

- ungültiges ZIP oder fehlendes `paket.json`
- Pfad-Ausbruch, Links, Sonderdateien, verschlüsselte ZIPs
- Größen-, Tiefen- oder Eintragsgrenzen überschritten
- unbekannte oder verbotene Dateitypen
- Format-/Versionsfehler
- Geheimnis- oder personenbezogene Datenfunde

`needs_review` erzeugen:

- enthaltene Prüf- oder Startskripte
- externe HTTPS-Links
- ~~neue oder unbekannte Rubrik~~ (entfällt: Pakete haben keine Rubrik)
- ungewöhnlich große oder komplexe Pakete innerhalb der technischen Grenzen
- mögliche Duplikate nach Paket-ID und Inhalt

`approved` ist im ersten Block nur eine technische Vorfreigabe und bedeutet noch nicht veröffentlicht.

## Nicht im ersten Block

- öffentliche Registrierung und Anmeldung
- E-Mail-Bestätigung und Passwort-Reset
- öffentliche Upload-API
- automatische Veröffentlichung
- Malware-Ausführung oder Sandbox-Ausführung fremder Skripte
- KI als alleinige Moderationsentscheidung
- Bezahlung, Marktplatz oder Autorenvergütung
- rechtliche Endprüfung

## Akzeptanzkriterien für die erste Implementierung

- Ein gültiges Paket erzeugt einen vollständigen, reproduzierbaren Prüfbericht.
- Ein manipuliertes oder gefährliches ZIP wird vor dem Entpacken abgewiesen.
- Kein Paket-Skript wird auf dem Entwicklungsrechner ausgeführt.
- Geheimnisfunde enthalten nur Datei, Zeile und Kategorie, niemals den Fundwert.
- Ein Paket mit Skripten kann nicht direkt als öffentlich freigegeben gelten, sondern landet mindestens in `needs_review`.
- Der Prüfbericht enthält keine privaten Pfade oder Zugangsdaten.
- Bestehende Kurspaket-Tests bleiben grün.

## Reihenfolge danach

1. ~~lokale Intake-Schicht und Tests~~ (erledigt, `kurspaket_portal.py`)
2. ~~Moderationsmodell und unveränderliche Prüf-/Versionshistorie~~ (erledigt, `kurspaket_moderation.py`)
3. ~~lokaler Admin-/Moderationsbildschirm~~ (erledigt, `gui/moderation_dialog.py`, nicht eingebunden)
4. authentifizierter Upload mit Rate-Limits – **Entwurf lokal fertig, nicht deployt** (28.10.): Annahme- und Prüfdienst in `packaging/kursportal-server/` als Overlay-Bundle für den bestehenden Docker-Stack der Schulungsseite, Domain `kurse.bony23.de`, Einladungs-Token, Prüfung auf dem Server im abgeschotteten Container. Bony deployed selbst; siehe README dort
5. öffentlicher Katalog und Download
6. Registrierung, E-Mail-Bestätigung und Kontoverwaltung

## Veröffentlichungsschranke

Dieser Plan beschreibt eine Entwicklungsgrundlage. Kein Portal, kein Upload-Endpunkt und kein Moderationssystem wird öffentlich aktiviert, bevor Bony den realen Test, die Sicherheitsprüfung und die Veröffentlichung ausdrücklich freigibt.
