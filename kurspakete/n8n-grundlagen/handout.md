---
title: n8n-Grundlagen – der erste Workflow
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
2. Ein **Agent-PC mit n8n** und mindestens **4 GB RAM**. Auf dem Schreibtisch liegt das Symbol **„n8n“** – fehlt es:
   Agent-PC starten, in der Detailansicht bei „Programme“ → **„Programme hinzufügen …“** → n8n.
3. **Telegram** auf dem Handy oder Rechner, mit eigenem Konto.
4. Dem Kurs beitreten: **„Kurse“** → Kurscode → Agent-PC wählen → **„Beitreten“**.

## B – Das Wichtigste in Kürze

| Begriff | Bedeutung |
|---|---|
| **Workflow** | ein Ablauf, der immer gleich läuft |
| **Auslöser** (Trigger) | wann der Workflow startet – heute: neuer Artikel im RSS-Feed |
| **Knoten** (Node) | ein Arbeitsschritt – heute: Nachricht per Telegram |
| **Ausführung** (Execution) | ein Durchlauf, mit Protokoll |
| **Publish** | veröffentlichen: Der Workflow läuft ab jetzt von selbst |

- n8n läuft **nur in deinem Agent-PC** (`http://localhost:5678`), nicht im Heimnetz, nicht im Bony-Netz.
- Der **Token** deines Bots ist ein **Passwort** – nur in n8n eintragen, nie zeigen.
- Nach jeder Änderung: **Strg + S** und erneut **„Publish“**.

## C – Telegram-Bot anlegen

1. In Telegram **@BotFather** öffnen (blauer Haken) → `/newbot` → Name → Benutzername auf `bot`.
2. Den **Token** sicher notieren.
3. Deinem Bot `/start` schreiben.
4. Chat-ID: in Brave `https://api.telegram.org/botDEIN-TOKEN/getUpdates` öffnen, die Zahl hinter `"chat":{"id":`.

::: {.feld hoehe="1.3cm" text="Benutzername meines Bots (der Token gehört NICHT hierher)"}
:::

## D – Der Workflow

1. **„Create workflow“** → Name *Nachrichten per Telegram*
2. **„Add first step…“** → **RSS Feed Trigger** → Feed URL `https://www.tagesschau.de/index~rss2.xml`
   → Poll Times **„Every Hour“** → **„Fetch Test Event“**
3. **+** → **Telegram** → **„Send a text message“** → Credential mit Token → Chat ID → Text: **title** und **link**
   hineinziehen → **„Execute step“**
4. **Strg + S** → **„Publish“**

## E – Weitere Feeds

| Quelle | Feed URL |
|---|---|
| Tagesschau | `https://www.tagesschau.de/index~rss2.xml` |
| heise online | `https://www.heise.de/rss/heise-atom.xml` |
| Deutschlandfunk | `https://www.deutschlandfunk.de/nachrichten-100.rss` |
| DER SPIEGEL | `https://www.spiegel.de/schlagzeilen/index.rss` |

## Meine Idee für den nächsten Workflow

::: {.feld hoehe="2.2cm" text="Auslöser – Schritte – Ergebnis"}
:::

## Wie es weitergeht

- **Sichern:** im Workflow **„…“** → **„Export JSON“**; übernehmen: **„…“** → **„Import“** → **„From file“**.
- **Benutzerhandbuch**, Kapitel „n8n“: im Programm unter ⓘ → „Hilfe (Anleitung)“.
- Dokumentation von n8n: docs.n8n.io (englisch).
- Nächster Kurs der Reihe: **Hermes und n8n im Team**.
- **Videos:** youtube.com/@BonysAgents
