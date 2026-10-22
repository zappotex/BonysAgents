---
title: Was ist ein MCP-Server? Hermes bekommt Werkzeuge
subtitle: Handout für Teilnehmerinnen und Teilnehmer
lang: de
---

## Dein Kurs

::: {.feld hoehe="1.3cm" text="Kurscode (bekommst du von der Kursleitung)"}
:::

::: {.feld hoehe="1.3cm" text="Datum und Uhrzeit"}
:::

## A – Vor dem Kurs

1. **Bony's Agents ab Version 0.24.0** – ältere Versionen aktualisieren (ⓘ → „Nach Updates suchen“ bzw. die
   Aktualisierungsverwaltung unter Linux).
2. Ein **Agent-PC mit Hermes Agent**. Auf dem Schreibtisch liegt **„Agenten-Apps“** – fehlt es: Agent-PC starten,
   in der Detailansicht bei „Programme“ → **„Programme hinzufügen …“** → Agenten-Apps.
3. **Hermes einrichten:** Symbol **Hermes Agent** → `hermes setup` → **Nous** → ein **kostenloses (free) Modell**,
   Anmeldung mit deinem **eigenen** Konto. Zum Test `hermes --tui` und „Hallo!“.
4. Dem Kurs beitreten: **„Kurse“** → Kurscode → Agent-PC wählen → **„Beitreten“**.

## B – Das Wichtigste in Kürze

- Ein **MCP-Server** ist ein kleines Programm, das einem Agenten **Werkzeuge** anbietet.
- Programme nur aus der **offiziellen Quelle** – die Liste „Agenten-Apps“ nennt sie.
- Die **Prüfsumme** muss **OK** melden. Bei **FEHLSCHLAG**: aufhören.
- Ein MCP-Server bekommt **nur einen Ordner** (`--root`).
- Im Terminal einfügen: **Strg + Umschalt + V**.

## C – Die Befehle

| Befehl | Was er tut |
|---|---|
| `hermes mcp add pdfcraft …` | meldet PdfCraft bei Hermes an (Befehl aus der Liste kopieren, mit **Y** bestätigen) |
| `hermes mcp test pdfcraft` | prüft die Verbindung und zeigt die Werkzeuge |
| `hermes mcp list` | zeigt alle angemeldeten MCP-Server |
| `hermes mcp remove pdfcraft` | meldet PdfCraft wieder ab |
| `/reload-mcp` | lädt im laufenden Hermes die MCP-Server neu |

## Übung – Hermes arbeitet mit PDFs

Die Dateien liegen in `~/Agent-Dateien/pdf`. Jeweils mit „Benutze PdfCraft: …“

1. *„Fasse protokoll.pdf zusammen. Was wurde beschlossen?“*
2. *„Seite 2 von protokoll.pdf steht quer. Dreh sie gerade und speichere das Ergebnis als protokoll-gerade.pdf.“*
3. *„Füge rechnung-maerz.pdf und rechnung-april.pdf zu rechnungen-gesamt.pdf zusammen.“*

Nach jedem Schritt: die Datei **selbst öffnen** und prüfen.

::: {.feld hoehe="2.2cm" text="Was ist dir aufgefallen?"}
:::

## Meine nächste Aufgabe für den Agenten

::: {.feld hoehe="2.2cm" text="Auslöser – was der Agent tut – Ergebnis"}
:::

## Wie es weitergeht

- Weitere Programme mit MCP-Server: Liste **„Agenten-Apps“** (online: zappotex.github.io/BonysAgents/agenten-apps).
  Viele sind noch **alpha** – mit wichtigen Dateien immer an einer Kopie arbeiten.
- **Benutzerhandbuch**, Kapitel „Agenten-Apps“: im Programm unter ⓘ → „Hilfe (Anleitung)“.
- Nächstes Kurspaket der Reihe: **„n8n-Grundlagen: der erste Workflow“**.
- **Videos:** youtube.com/@BonysAgents
