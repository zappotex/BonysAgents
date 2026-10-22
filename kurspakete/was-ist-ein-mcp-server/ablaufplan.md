---
title: Kurs „Was ist ein MCP-Server? Hermes bekommt Werkzeuge“
subtitle: Ablaufplan für die Kursleitung – 90 Minuten, 3–10 Teilnehmer mit eingerichtetem Hermes
lang: de
---

# Steckbrief

| | |
|---|---|
| **Titel** | Was ist ein MCP-Server? Hermes bekommt Werkzeuge |
| **Dauer** | 90 Minuten ohne Pause |
| **Gruppe** | 3–10 Personen; Hermes ist eingerichtet (z. B. nach „Einführung in Hermes Agent“) |
| **Form** | Kurs über das Internet mit dem Kursraum von Bony's Agents (geht genauso vor Ort) |
| **Teilnehmer brauchen** | Bony's Agents ab 0.24.0, Agent-PC mit Hermes und der Liste „Agenten-Apps“, Internet, Headset |
| **Du brauchst** | Bony's Agents Kursleiter, Vorführ-Agent-PC mit eingerichtetem Hermes, **ohne** PdfCraft |
| **Kosten** | keine – PdfCraft ist frei, Hermes läuft mit einem kostenlosen Modell |
| **Material** | Kurspaket „Was ist ein MCP-Server?“ (Ablaufplan, Handout, Lektionen mit Quiz und Prüfaufgaben) |

Erster Kurs der Reihe „Agenten, MCP-Apps und n8n“. Am Ende hat jeder PdfCraft aus der offiziellen Quelle
installiert, seinen MCP-Server bei Hermes angemeldet und Hermes echte PDFs bearbeiten lassen.

# Lernziele

Am Ende des Kurses können die Teilnehmer …

1. in eigenen Worten erklären, was ein **MCP-Server** ist und warum ein Agent ihn braucht;
2. die Liste **„Agenten-Apps“** finden und einen Eintrag lesen (Status, Lizenz, Quelle, Prüfsumme);
3. ein Programm aus der **offiziellen Quelle** installieren und die **Prüfsumme** kontrollieren;
4. einen MCP-Server mit **`hermes mcp add`** anmelden und mit **`hermes mcp test`** prüfen;
5. Hermes PDFs **zusammenfassen, drehen und zusammenfügen** lassen und das Ergebnis **selbst prüfen**;
6. erklären, warum der Agent nur in einem **freigegebenen Ordner** arbeiten darf.

# Vorbereitung

## Eine Woche vorher

- [ ] Kurs anlegen, bei **„Kurspaket“** „Was ist ein MCP-Server?“ wählen.
- [ ] Einladung mit Kurscode und **Handout** verschicken. Wichtig: **Hermes vorher einrichten** (Handout, Abschnitt A).
- [ ] Den Kurs einmal selbst durcharbeiten („Durcharbeiten“, Selbstlern-Modus) – so liegen die Beispiel-PDFs auch
  in deinem Vorführ-Agent-PC, und du siehst, wie dein Modell mit PdfCraft umgeht.

## Ein bis zwei Tage vorher

- [ ] Prüfen, ob die Liste „Agenten-Apps“ beim Eintrag PdfCraft noch **„Getestet“** zeigt (Online-Liste:
  zappotex.github.io/BonysAgents/agenten-apps). PdfCraft ist **alpha** – Änderungen sind möglich.
- [ ] Im Vorführ-Agent-PC PdfCraft wieder **entfernen** (`hermes mcp remove pdfcraft`, `rm ~/.local/bin/pdfcraft-cli`),
  damit du Block 2 und 4 vorführen kannst – oder einen zweiten Vorführ-Agent-PC ohne PdfCraft bereithalten.
- [ ] In der Kursansicht: Sind alle beigetreten? Haben Teilnehmer Lektion 1 schon „geschafft“?

## 30 Minuten vorher

- [ ] Vorführ-Agent-PC starten, Terminal und die Liste „Agenten-Apps“ öffnen, Schrift groß stellen (Strg + Plus).
- [ ] **„Kurs starten“**, **„Kursraum öffnen“**, Fenster des Agent-PCs teilen.

# Zeitplan

| Minute | Dauer | Block | Inhalt |
|---:|---:|---|---|
| 0 | 10 | 1 Ankommen | Begrüßung, Ablauf, Hermes antwortet (Prüfung) |
| 10 | 15 | 2 Ein Kopf ohne Hände | MCP erklären, Live: Hermes ohne PDF-Werkzeug, Quiz |
| 25 | 10 | 3 Die Liste | Eintrag PdfCraft lesen, Quiz |
| 35 | 25 | 4 PdfCraft einrichten | installieren, Prüfsumme, `hermes mcp add`, testen, neu starten |
| 60 | 20 | 5 Übung | zusammenfassen, drehen, zusammenfügen – selbst prüfen |
| 80 | 10 | 6 Abschluss | Runde, Ausblick, Quiz |

Die Blöcke 1–6 entsprechen den Lektionen 1–6 im Kurspaket. Wird die Zeit knapp, kürze Block 3 (die Liste lässt
sich in Block 4 nebenbei erklären) – nicht Block 4.

# Ablauf Schritt für Schritt

## Block 1 – Ankommen (0–10)

**Du zeigst:** Kursraum, geteilter Agent-PC. Ablauf der fünf Schritte.

**Teilnehmer machen:** Agent-PC starten, Kurspaket-Anleitung öffnen, `hermes --tui`, „Hallo!“ – dann **„Prüfen“**.

**Nachhaken:** In der Kursansicht siehst du, wer „Hermes eingerichtet“ hat. Wer nicht: sofort per **„Helfen“** zu
`hermes setup` (Nous → Free-Modell).

## Block 2 – Ein Kopf ohne Hände (10–25)

**Du erzählst** (5 Minuten): Ein Sprachmodell versteht und plant – zum Handeln braucht es Werkzeuge. **MCP** ist die
gemeinsame Sprache für Werkzeuge, ein **MCP-Server** der Werkzeugkasten. Er bekommt nur einen Ordner.

**Live-Vorführung** (5 Minuten) in deinem Agent-PC **ohne** PdfCraft:

```
Seite 2 von ~/Agent-Dateien/pdf/protokoll.pdf steht quer. Dreh sie gerade.
```

Kommentiere, was Hermes tut: Umweg über das Terminal? Vorschlag, etwas zu installieren (**nicht bestätigen**)?
„Er weiß, was zu tun wäre – aber er hat kein passendes Werkzeug.“

**Teilnehmer machen:** zuschauen oder dasselbe ausprobieren, dann das **Quiz**.

## Block 3 – Die Liste (25–35)

**Du zeigst:** Doppelklick auf **„Agenten-Apps“**, Eintrag **PdfCraft**: Alpha, Getestet, „Dein Agent kann damit“,
Lizenz, Prüfsumme, „Installieren & mit Hermes verbinden“ aufklappen.

**Teilnehmer machen:** dasselbe in ihrem Agent-PC, dann das **Quiz**.

**Nachhaken:** „Woher wissen wir, dass der Download echt ist?“ – offizielle Quelle **und** Prüfsumme.

## Block 4 – PdfCraft einrichten (35–60)

**Du zeigst** (5 Minuten): ersten Block kopieren → Terminal → **Strg + Umschalt + V** → Zeile mit **OK** zeigen.
Zweiten Block (`hermes mcp add pdfcraft …`) → Werkzeuge erscheinen → **Y** → **Saved 'pdfcraft'**.
`hermes mcp test pdfcraft` → **✓ Connected**. Hermes neu starten bzw. `/reload-mcp`.

**Teilnehmer machen** (15 Minuten): dieselben Schritte, dann **„Prüfen“**.

**Nachhaken:** Wer nach 10 Minuten kein ✋ hat, bekommt „Helfen“. Häufigste Ursachen: Einfügen mit Strg + V statt
Strg + Umschalt + V; nur der erste Block ausgeführt.

## Block 5 – Übung (60–80)

Siehe Übung unten. 2 Minuten erklären, 13 Minuten arbeiten, 5 Minuten zusammentragen.

**Nachhaken:** „Stand Seite 2 bei allen richtig herum?“ – Wer sie auf dem Kopf hat, hat etwas Wichtiges gelernt:
**selbst prüfen**.

## Block 6 – Abschluss (80–90)

Runde „Was hat geklappt, was nicht?“, Frage zum Mitnehmen („Welche Aufgabe gibst du deinem Agenten als
Nächstes?“), Ausblick auf die nächsten Kurse, **Quiz**, Kurs beenden.

# Übung mit Lösung

**Aufgabe (wie in der Anleitung):** Jeweils mit „Benutze PdfCraft: …“

1. *„Fasse protokoll.pdf zusammen. Was wurde beschlossen?“*
2. *„Seite 2 von protokoll.pdf steht quer. Dreh sie gerade und speichere das Ergebnis als protokoll-gerade.pdf.“*
3. *„Füge rechnung-maerz.pdf und rechnung-april.pdf zu rechnungen-gesamt.pdf zusammen.“*

**Lösung / Erwartung:**

1. Mitgliedsbeitrag bleibt bei **36 EUR** im Jahr; Sommerfest am **4. Juli**; eine **Regentonne** für den
   Gemeinschaftsgarten; alle Beschlüsse einstimmig.
2. `protokoll-gerade.pdf`, Seite 2 aufrecht. Manche Modelle drehen in die falsche Richtung – die Seite steht dann
   auf dem Kopf.
3. `rechnungen-gesamt.pdf` mit zwei Seiten: Rechnung 2026-031 (März, 48,50 EUR), dann 2026-042 (April, 41,90 EUR).

**Für Schnelle:** Summe beider Rechnungen: **90,40 EUR**.

# Typische Stolpersteine

| Problem | Woran du es erkennst | Was hilft |
|---|---|---|
| Einfügen klappt nicht | im Terminal erscheint `^V` | **Strg + Umschalt + V** oder Rechtsklick → Einfügen |
| Prüfsumme **FEHLSCHLAG** | Zeile im Terminal | Datei löschen, Block wiederholen; bleibt es so: abbrechen, nicht installieren |
| `hermes: command not found` | im Terminal | Agent-PC ohne Hermes → „Programme hinzufügen …“ → Hermes Agent |
| PdfCraft taucht in Hermes nicht auf | Hermes nimmt das Terminal statt PdfCraft | Hermes neu starten oder `/reload-mcp`; „Benutze PdfCraft“ sagen |
| Datei nicht gefunden / kein Zugriff | Meldung von PdfCraft | PdfCraft darf nur in `~/Agent-Dateien/pdf` arbeiten |
| „Rate limit“ | Fehlermeldung von Hermes | kurz warten, mit `/model` ein anderes kostenloses Modell |
| Liste „Agenten-Apps“ fehlt | kein Symbol auf dem Schreibtisch | „Programme hinzufügen …“ → Agenten-Apps, oder Online-Liste in Brave |

# Plan B

**Download von GitHub klappt nicht** (Netz, Störung): Vorführen geht trotzdem – du zeigst Block 4 und 5 in deinem
vorbereiteten Agent-PC, die Teilnehmer sagen dir im Chat, was Hermes tun soll. Die Installation holen sie als
Hausaufgabe nach (Selbstlern-Modus, Lektion 4).

**Das kostenlose Modell ist überlastet:** Block 5 bei dir vorführen. Die Schritte „Liste → Installieren →
Anmelden“ funktionieren ohne Modell.

**PdfCraft hat sich geändert** (alpha): Steht in der Liste kein „Getestet“ mehr oder klappt die Installation nicht,
weiche auf **Dateisystem (MCP)** aus – derselbe Weg, stabil, ohne PDFs.
