---
title: Sicherheit für KI-Agenten: Rechte begrenzen, Prompt-Injection erkennen
subtitle: Ablaufplan für die Kursleitung (Entwurf) – 2 Stunden
lang: de
---

::: warnung
Dieses Kurspaket ist ein **Entwurf**: Gliederung und Zeitplan stehen, die Lektionen sind noch nicht
ausgearbeitet. Mit dem Editor (Kursleiter-Version) kannst du eine eigene Fassung daraus machen.
:::

# Steckbrief

| | |
|---|---|
| **Stufe** | Fortgeschritten |
| **Dauer** | 120 Minuten mit 10 Minuten Pause |
| **Zielgruppe** | Menschen, die Agenten im Alltag oder im Beruf einsetzen wollen |
| **Voraussetzungen** | Agent-PC mit eingerichtetem Hermes; Grundkenntnisse aus „Einführung in Hermes Agent“ |

Die Beispiele für Prompt-Injection sind harmlos (sie bitten z. B. nur darum, ein Gedicht zu schreiben) und
liegen ausschließlich im Agent-PC.

# Lernziele

1. erklären, warum ein Agent mehr Risiken hat als ein Chatbot
2. Prompt-Injection an Beispielen erkennen
3. Werkzeuge und Freigaben von Hermes einschränken
4. Zugangsdaten so ablegen, dass der Agent sie nicht braucht oder nicht sieht
5. im Ernstfall den Agent-PC zurücksetzen und Schlüssel zurückziehen

# Zeitplan

| Minute | Dauer | Lektion | Art |
|---:|---:|---|---|
| 0 | 20 | 1 Was kann schiefgehen? | Erklärung + Quiz |
| 20 | 30 | 2 Prompt-Injection erkennen | Übung |
| 50 | 25 | 3 Rechte und Werkzeuge begrenzen | Mitmachen |
| 75 | 20 | 4 Zugangsdaten schützen | Erklärung + Übung |
| 95 | 15 | 5 Der Ernstfall | Übung |

# Gliederung

## Lektion 1 – Was kann schiefgehen? (20 Minuten)

**Ziel:** Die wichtigsten Risiken kennen.

- Falsche Antworten, falsche Handlungen, fremde Anweisungen
- Warum ein abgeschotteter Agent-PC
- Beispiele aus der Praxis

## Lektion 2 – Prompt-Injection erkennen (30 Minuten)

**Ziel:** Versteckte Anweisungen in Texten finden.

- Startzustand: harmlose Beispielseiten in ~/Kurs/seiten mit versteckten Anweisungen
- Hermes die Seiten zusammenfassen lassen – was passiert?
- Woran man es merkt, wie man sich schützt

## Lektion 3 – Rechte und Werkzeuge begrenzen (25 Minuten)

**Ziel:** Hermes darf nur, was nötig ist.

- /tools ansehen, Werkzeuge abschalten
- Bestätigung vor gefährlichen Befehlen
- Eigener Benutzer, keine Zugangsdaten im Agent-PC

## Lektion 4 – Zugangsdaten schützen (20 Minuten)

**Ziel:** Schlüssel richtig ablegen und zurückziehen.

- Wo liegen Schlüssel (~/.hermes/.env) und wer sieht sie?
- Limits beim Anbieter setzen
- Schlüssel zurückziehen und neu anlegen

## Lektion 5 – Der Ernstfall (15 Minuten)

**Ziel:** Wissen, was zu tun ist.

- Agent-PC zurücksetzen oder aus Vorlage neu
- Schlüssel zurückziehen
- Checkliste zum Mitnehmen
