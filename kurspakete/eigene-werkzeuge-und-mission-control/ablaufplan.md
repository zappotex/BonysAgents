---
title: Eigene Werkzeuge und Skills für Hermes, Mission Control mit Docker
subtitle: Ablaufplan für die Kursleitung (Entwurf) – 3 Stunden
lang: de
---

::: warnung
Dieses Kurspaket ist ein **Entwurf**: Gliederung und Zeitplan stehen, die Lektionen sind noch nicht
ausgearbeitet. Mit dem Editor (Kursleiter-Version) kannst du eine eigene Fassung daraus machen.
:::

# Steckbrief

| | |
|---|---|
| **Stufe** | Experte |
| **Dauer** | 180 Minuten mit 15 Minuten Pause |
| **Zielgruppe** | Menschen mit Erfahrung in Terminal und Skripten |
| **Voraussetzungen** | Agent-PC mit eingerichtetem Hermes und Docker; Sicherer Umgang mit dem Terminal; Grundkenntnisse in Python oder Bash |

Befehle und Dateipfade für Skills und MCP vor dem Ausarbeiten in der aktuellen Hermes-Dokumentation
nachsehen – sie ändern sich zwischen Versionen.

# Lernziele

1. den Aufbau von Werkzeugen und Skills in Hermes erklären
2. einen eigenen Skill schreiben und testen
3. einen MCP-Server anbinden
4. Mission Control mit Docker starten und Agenten beobachten
5. Rechte und Grenzen eigener Werkzeuge festlegen

# Zeitplan

| Minute | Dauer | Lektion | Art |
|---:|---:|---|---|
| 0 | 25 | 1 Wie Hermes Werkzeuge nutzt | Erklärung |
| 25 | 40 | 2 Einen eigenen Skill schreiben | Übung |
| 65 | 35 | 3 Einen MCP-Server anbinden | Mitmachen |
| 100 | 40 | 4 Mission Control | Mitmachen |
| 140 | 25 | 5 Grenzen und Abschluss | Gespräch |

# Gliederung

## Lektion 1 – Wie Hermes Werkzeuge nutzt (25 Minuten)

**Ziel:** Werkzeuge, Skills und MCP unterscheiden.

- /tools und die Konfiguration ansehen
- Skills: Aufbau und Ablageort laut Doku
- MCP in einem Satz

## Lektion 2 – Einen eigenen Skill schreiben (40 Minuten)

**Ziel:** Ein eigener Skill funktioniert.

- Kleiner Skill: Notiz mit Datum in ~/Kurs/notizen anlegen
- Testen und Fehler lesen
- Prüfaufgabe (geplant): Skill-Datei existiert

## Lektion 3 – Einen MCP-Server anbinden (35 Minuten)

**Ziel:** Hermes nutzt ein Werkzeug über MCP.

- Offiziellen Beispiel-Server wählen
- In der Hermes-Konfiguration eintragen
- Rechte begrenzen

## Lektion 4 – Mission Control (40 Minuten)

**Ziel:** Mission Control läuft und zeigt den Agenten.

- Mission Control (Docker) im Agent-PC starten
- Agenten und Aufgaben im Browser ansehen
- Prüfaufgabe (geplant): Dienst läuft

## Lektion 5 – Grenzen und Abschluss (25 Minuten)

**Ziel:** Eigene Werkzeuge verantwortungsvoll einsetzen.

- Was darf ein eigenes Werkzeug?
- Updates und Pflege
- Ausblick: mehrere Agenten zusammenarbeiten lassen
