---
title: Hermes über Telegram steuern
subtitle: Ablaufplan für die Kursleitung (Entwurf) – 1 h 30 min
lang: de
---

::: warnung
Dieses Kurspaket ist ein **Entwurf**: Gliederung und Zeitplan stehen, die Lektionen sind noch nicht
ausgearbeitet. Mit dem Editor (Kursleiter-Version) kannst du eine eigene Fassung daraus machen.
:::

# Steckbrief

| | |
|---|---|
| **Stufe** | Anfänger |
| **Dauer** | 90 Minuten mit 10 Minuten Pause |
| **Zielgruppe** | Teilnehmer von „Einführung in Hermes Agent“ oder mit erstem Agent-PC |
| **Voraussetzungen** | Agent-PC mit eingerichtetem Hermes (Kurspaket „Einführung in Hermes Agent“); Telegram auf dem Handy |

Der Kurs baut auf „Einführung in Hermes Agent“ auf. Jeder Teilnehmer legt einen **eigenen** Bot an; es gibt
keinen gemeinsamen Bot und kein gemeinsames Token.

# Lernziele

1. einen eigenen Telegram-Bot anlegen und mit Hermes verbinden
2. festlegen, wer dem Bot schreiben darf
3. Hermes vom Handy aus Aufgaben geben und das Ergebnis im Agent-PC prüfen
4. das Bot-Token wie ein Passwort behandeln

# Zeitplan

| Minute | Dauer | Lektion | Art |
|---:|---:|---|---|
| 0 | 20 | 1 Einen Telegram-Bot anlegen | Mitmachen |
| 20 | 25 | 2 Hermes mit dem Bot verbinden | Mitmachen |
| 45 | 25 | 3 Aufgaben vom Handy | Übung |
| 70 | 10 | 4 Sicherheit und Abschluss | Erklärung + Quiz |

# Gliederung

## Lektion 1 – Einen Telegram-Bot anlegen (20 Minuten)

**Ziel:** Ein eigener Bot mit Token existiert.

- In Telegram @BotFather öffnen, /newbot, Name und Benutzername wählen
- Das Token nur in den Agent-PC übertragen – nie in einen Chat, nie beim Bildschirmteilen
- Warum ein eigener Bot je Teilnehmer?

## Lektion 2 – Hermes mit dem Bot verbinden (25 Minuten)

**Ziel:** Hermes antwortet in Telegram.

- hermes setup bzw. die Gateway-Einrichtung für Telegram durchgehen
- Eigene Telegram-ID als einzige erlaubte Person eintragen
- Prüfaufgabe (geplant): Gateway-Dienst läuft (Vorlage „Dienst läuft“)

## Lektion 3 – Aufgaben vom Handy (25 Minuten)

**Ziel:** Hermes erledigt eine Aufgabe, die per Handy kam.

- Aus Telegram: „Lege ~/Kurs/notiz.txt mit drei Ideen für das Wochenende an“
- Im Agent-PC selbst prüfen
- Was passiert, wenn der Agent-PC aus ist?

## Lektion 4 – Sicherheit und Abschluss (10 Minuten)

**Ziel:** Risiken eines erreichbaren Agenten kennen.

- Wer den Bot erreicht, steuert den Agenten – Freigabeliste
- Token zurückziehen (/revoke), wenn es versehentlich gezeigt wurde
- Ausblick: Aufgaben automatisieren
