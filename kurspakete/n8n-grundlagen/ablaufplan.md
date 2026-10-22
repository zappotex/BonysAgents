---
title: Kurs „n8n-Grundlagen: der erste Workflow“
subtitle: Ablaufplan für die Kursleitung – 90 Minuten, 3–10 Teilnehmer ohne Vorkenntnisse
lang: de
---

# Steckbrief

| | |
|---|---|
| **Titel** | n8n-Grundlagen: der erste Workflow |
| **Dauer** | 90 Minuten ohne Pause |
| **Gruppe** | 3–10 Personen, keine Vorkenntnisse nötig (Hermes wird nicht gebraucht) |
| **Form** | Kurs über das Internet mit dem Kursraum von Bony's Agents (geht genauso vor Ort) |
| **Teilnehmer brauchen** | Bony's Agents ab 0.24.0, Agent-PC mit n8n (mind. 4 GB RAM), Telegram auf Handy oder Rechner, Headset |
| **Du brauchst** | Bony's Agents Kursleiter, Vorführ-Agent-PC mit n8n und Konto, eigenen Telegram-Bot |
| **Kosten** | keine |
| **Material** | Kurspaket „n8n-Grundlagen“ (Ablaufplan, Handout, Lektionen mit Quiz und Prüfaufgaben), Liste mit RSS-Feeds (in Lektion 6) |

Am Ende hat jeder einen veröffentlichten Workflow, der neue Artikel aus einem RSS-Feed per Telegram schickt, und
eine gesicherte Kopie davon. Der Kurs gehört zur Reihe „Agenten, MCP-Apps und n8n“, steht aber für sich allein.

# Lernziele

Am Ende des Kurses können die Teilnehmer …

1. erklären, was ein **Workflow** ist: Auslöser, Knoten, Verbindungen, Ausführungen;
2. **n8n** im Agent-PC öffnen und ein eigenes Konto anlegen;
3. einen **Telegram-Bot** anlegen und dessen **Token** wie ein Passwort behandeln;
4. einen Workflow **„RSS → Telegram“** bauen, testen und **veröffentlichen**;
5. den Workflow **abwandeln** (anderer Feed, andere Zeit, andere Nachricht);
6. einen Workflow mit **„Export JSON“** sichern und wissen, wo n8n seine Daten speichert.

# Vorbereitung

## Eine Woche vorher

- [ ] Kurs anlegen, bei **„Kurspaket“** „n8n-Grundlagen“ wählen.
- [ ] Einladung mit Kurscode und **Handout** verschicken. Wichtig: Agent-PC **mit n8n** und **mindestens 4 GB RAM**,
  Telegram vorher installieren.
- [ ] Entscheiden: **jeder einen eigenen Bot** (empfohlen) oder ein gemeinsamer Kursbot.
- [ ] Den Kurs einmal selbst durcharbeiten (Selbstlern-Modus) – so hast du einen fertigen Vorführ-Workflow.

## Ein bis zwei Tage vorher

- [ ] Die RSS-Feeds aus Lektion 5 und 6 einmal mit **„Fetch Test Event“** prüfen (Adressen ändern sich selten, aber
  manchmal).
- [ ] In der Kursansicht: Sind alle beigetreten? Läuft bei allen der Agent-PC?

## 30 Minuten vorher

- [ ] Vorführ-Agent-PC starten (n8n braucht danach etwa eine Minute), n8n in Brave öffnen, Zoom auf 125 %.
- [ ] Telegram-Credential im Vorführ-n8n schon anlegen – so musst du den Token nie zeigen.
- [ ] **„Kurs starten“**, **„Kursraum öffnen“**, Fenster des Agent-PCs teilen.

# Zeitplan

| Minute | Dauer | Block | Inhalt |
|---:|---:|---|---|
| 0 | 5 | 1 Ankommen | Begrüßung, Ablauf, „Was macht ihr jede Woche gleich?“ |
| 5 | 10 | 2 Was ist ein Workflow? | Auslöser, Knoten, Verbindung, Ausführung; Quiz |
| 15 | 15 | 3 n8n öffnen | Symbol „n8n“, Konto anlegen, umschauen (Prüfung) |
| 30 | 10 | 4 Telegram vorbereiten | Bot bei BotFather, Chat-ID über getUpdates |
| 40 | 25 | 5 Der erste Workflow | RSS Feed Trigger → Telegram, testen, veröffentlichen (Prüfung) |
| 65 | 15 | 6 Eigene Variante | anderer Feed, andere Zeit, schönere Nachricht |
| 80 | 10 | 7 Sichern und Abschluss | Export JSON (Prüfung), Runde, Quiz |

Die Blöcke 1–7 entsprechen den Lektionen 1–7 im Kurspaket. Wird die Zeit knapp, kürze Block 6 – nicht Block 5.

# Ablauf Schritt für Schritt

## Block 1 – Ankommen (0–5)

**Du zeigst:** Kursraum, geteilter Agent-PC. Ablauf. **Einstieg:** „Was macht ihr jede Woche wieder, immer
gleich?“ – zwei, drei Beispiele.

## Block 2 – Was ist ein Workflow? (5–15)

**Du erzählst:** „Wenn Post kommt, lege ich sie ins Fach“ – Auslöser, Schritte, Weg dazwischen. Zeig deinen
fertigen Workflow: zwei Knoten, eine Verbindung, unten **Executions**.

**Teilnehmer machen:** zuhören, **Quiz**.

## Block 3 – n8n öffnen (15–30)

**Du zeigst:** Doppelklick auf **„n8n“** → **„Set up owner account“** → Fragen mit **„Continue“** überspringen →
Übersicht.

**Teilnehmer machen:** dasselbe, dann **„Prüfen“**.

**Nachhaken:** „Das Konto gilt nur für dein n8n – merkt euch das Passwort.“ Wer kein Symbol hat: „Programme
hinzufügen …“ → n8n (dauert einige Minuten – in der Zwischenzeit bei dir zuschauen).

## Block 4 – Telegram vorbereiten (30–40)

**Du zeigst** (am Handy über die Kamera oder als Bild): @BotFather → `/newbot` → Name → Benutzername auf `bot` →
Token. **Den echten Token nie zeigen.** Dann `/start` beim eigenen Bot und `getUpdates` in Brave.

**Teilnehmer machen:** eigenen Bot anlegen, Chat-ID notieren.

**Nachhaken:** „Wo bewahrt ihr den Token auf?“ – nur in n8n, nicht im Chat.

## Block 5 – Der erste Workflow (40–65)

**Du zeigst** Schritt für Schritt, die Teilnehmer bauen mit: **„Create workflow“** → Name → **„Add first step…“** →
**RSS Feed Trigger** → Feed URL → Poll Times **„Every Hour“** → **„Fetch Test Event“** → **+** → **Telegram** →
**„Send a text message“** → Credential → Chat ID → Text (title und link hineinziehen) → **„Execute step“** →
Nachricht kommt an → **Strg + S** → **„Publish“**.

**Teilnehmer machen:** fertig bauen, **„Prüfen“**.

**Nachhaken:** ✋ heben, sobald die Testnachricht auf dem Handy ist. Wer nach 15 Minuten keine hat: „Helfen“.

## Block 6 – Eigene Variante (65–80)

Siehe Übung unten.

## Block 7 – Sichern und Abschluss (80–90)

**Du zeigst:** **„…“** → **„Export JSON“** → Datei im Ordner Downloads. Import in ein anderes n8n über **„Import“**
→ **„From file“**.

**Teilnehmer machen:** exportieren, **„Prüfen“**, **Quiz**.

**Abschluss:** „Welchen Ablauf würdet ihr als Nächstes automatisieren?“ Ausblick auf „Hermes und n8n im Team“. Kurs
beenden.

# Übung mit Lösung (Block 6)

**Aufgabe:** zwei oder drei Punkte aus der Anleitung umsetzen – anderer Feed, andere Zeit, schönere Nachricht,
zweiter Workflow.

**Lösung / Erwartung:**

- Anderer Feed: Feed URL tauschen, **„Fetch Test Event“** zeigt sofort neue Daten.
- Andere Zeit: Poll Times **„Every Day“** mit Stunde und Minute.
- Schönere Nachricht: Text z. B. `📰 {{ $json.title }}` + Zeilenumbruch + `{{ $json.link }}`; unter
  **Additional Fields** **Append n8n Attribution** aus.
- Nach jeder Änderung **Strg + S** und erneut **„Publish“**.

**Für Schnelle:** Knoten **„Filter“** zwischen Auslöser und Telegram, Bedingung „contains“ auf den Titel.

# Typische Stolpersteine

| Problem | Woran du es erkennst | Was hilft |
|---|---|---|
| n8n-Seite bleibt leer | Brave zeigt „Diese Seite ist nicht erreichbar“ | n8n startet noch – eine Minute warten, F5 |
| Kein Symbol „n8n“ | Schreibtisch | „Programme hinzufügen …“ → n8n |
| Agent-PC zu langsam | n8n reagiert zäh | Agent-PC mit mindestens 4 GB RAM erstellen (das Fenster „Neuer Agent-PC“ warnt bei zu wenig) |
| `getUpdates` zeigt `"result":[]` | Brave | dem Bot zuerst `/start` schreiben, Seite neu laden |
| „chat not found“ | Telegram-Knoten rot | Chat-ID falsch oder dem Bot nie geschrieben |
| „Unauthorized“ | Telegram-Knoten rot | Token falsch kopiert – Credential neu anlegen |
| `{{ $json.title }}` steht wörtlich in der Nachricht | Handy | Feld Text auf **Expression** umstellen bzw. Werte hineinziehen |
| Änderung wirkt nicht | alte Nachrichten-Form kommt weiter | nach dem Speichern erneut **„Publish“** |
| Nachrichten kommen nicht sofort | nach dem Veröffentlichen | richtig so – Poll Times „Every Hour“ |

# Plan B

**Telegram geht bei jemandem nicht** (kein Konto, keine Handynummer): Er baut den Workflow mit einem gemeinsamen
Kursbot und deiner Chat-ID mit – oder schaut bei dir zu. Den eigenen Bot holt er im Selbstlern-Modus nach.

**n8n startet bei jemandem nicht:** Agent-PC neu starten. Hilft das nicht, schaut er bei dir zu; die Lektionen
lassen sich später im Selbstlern-Modus nachholen.

**Ein RSS-Feed ist gestört:** auf einen anderen Feed aus Lektion 6 ausweichen.
