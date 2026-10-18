---
title: Beispielkurs „Einführung in Hermes Agent“
subtitle: Ablaufplan für die Kursleitung – 2 Stunden, 5–10 Teilnehmer ohne Vorkenntnisse
lang: de
---

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
<!-- Teil A des Beispielkurses (Kursleitung). Teil B, das Handout, steht in beispielkurs-handout.md. -->

# Steckbrief

| | |
|---|---|
| **Titel** | Einführung in Hermes Agent – mit KI arbeiten, aber der Mensch bleibt am Steuer |
| **Dauer** | 2 Stunden (120 Minuten) mit 10 Minuten Pause |
| **Gruppe** | 5–10 Personen, keine Vorkenntnisse nötig |
| **Form** | Kurs über das Internet mit dem Kursraum von Bony's Agents (geht genauso vor Ort) |
| **Teilnehmer brauchen** | Rechner mit Bony's Agents, Agent-PC im Bony-Netz, Headset; Kamera freiwillig |
| **Du brauchst** | Bony's Agents Kursleiter, Kursleiter-Code, Vorführ-Agent-PC mit eingerichtetem Hermes |
| **Material** | dieses Dokument, das Handout (eigene PDF), das Kursleiter-Handbuch |

Der Kurs zeigt, was ein KI-Agent ist, wie man ihm Aufgaben gibt und wo seine Grenzen sind. Am Ende haben alle
selbst mit Hermes gearbeitet – in ihrem eigenen, abgeschotteten Agent-PC.

# Lernziele

Am Ende des Kurses können die Teilnehmer …

1. in eigenen Worten erklären, was ein **KI-Agent** ist und warum er in einem **Agent-PC** arbeitet;
2. Hermes in ihrem Agent-PC **starten** und ihm eine **Aufgabe in einfacher Sprache** geben;
3. Hermes **Dateien anlegen und lesen** lassen und das Ergebnis **selbst prüfen**;
4. Hermes etwas **im Internet recherchieren** lassen und die Quellen kritisch ansehen;
5. **Grenzen und Risiken** benennen (falsche Antworten, Kosten, Datenschutz) und wissen, was sie einer KI nicht
   geben.

# Vorbereitung

## Eine Woche vorher

- [ ] Kurs anlegen („Kurse“ → „Kursleitung“ → „+ Neuer Kurs …“), Code-Gültigkeit mindestens 14 Tage.
- [ ] Einladung mit Kurscode und **Handout** verschicken (Textvorlage im Kursleiter-Handbuch, Kapitel 3.3).
- [ ] Entscheiden, welchen **Modell-Anbieter** die Teilnehmer nutzen. Für den Einstieg reicht ein kostenloses
  Modell bei OpenRouter (Konto bei openrouter.ai, API-Schlüssel). Schreib das ins Handout bzw. in die Einladung.
- [ ] Für Teilnehmer, die vor Ort am selben Anschluss sitzen: Server-Betreiber wegen „Instanzen pro Tag“ fragen.

::: tipp
Willst du den Teilnehmern das Einrichten von Hermes ersparen, richte stattdessen einen Agent-PC fertig ein (ohne
API-Schlüssel!), speichere ihn als Vorlage und verteile ihn als `.bonys`-Datei. Dann entfällt Abschnitt B im
Handout, und Block 3 im Kurs wird kürzer.
:::

## Ein bis zwei Tage vorher

- [ ] In der Kursansicht nachsehen: Sind alle beigetreten? Hat jeder eine **Netzadresse**?
- [ ] Wer fehlt, kurz anschreiben – die häufigste Ursache ist ein Agent-PC ohne Häkchen „Mit dem Bony-Netz
  verbinden“ (Abhilfe: Rechtsklick in der Liste → „Mit dem Bony-Netz verbinden“).
- [ ] **Probelauf** mit einem zweiten Rechner: Kursraum, Ton, Bildschirm teilen, „Helfen“.
- [ ] Im Vorführ-Agent-PC die **Übungsdateien** vorbereiten: einen leeren Ordner `~/Kurs` anlegen.

## 30 Minuten vorher

- [ ] Rechner am Strom, Benachrichtigungen aus, nur nötige Fenster offen.
- [ ] Vorführ-Agent-PC starten, ein Terminal mit Hermes öffnen, Schrift im Terminal groß stellen (Strg + Plus).
- [ ] **„Kurs starten“**, **„Kursraum öffnen“**, Mikrofon prüfen, Fenster des Agent-PCs teilen.
- [ ] Plan-B-Link (z. B. Jitsi) bereithalten.

# Zeitplan

| Minute | Dauer | Block | Inhalt |
|---:|---:|---|---|
| 0 | 10 | 1 Ankommen | Begrüßung, Technik-Check, Regeln im Kursraum |
| 10 | 15 | 2 Was ist ein Agent? | Erklärung und Live-Vorführung |
| 25 | 15 | 3 Hermes startklar | Agent-PC starten, `hermes doctor`, erstes „Hallo“ |
| 40 | 20 | 4 Übung 1 | Dateien anlegen und prüfen |
| 60 | 10 | Pause | Kameras aus, Mikrofone aus |
| 70 | 20 | 5 Übung 2 | Recherche im Internet |
| 90 | 15 | 6 Übung 3 | Grenzen erkennen |
| 105 | 10 | 7 Sicherheit | Was ich einer KI nicht gebe |
| 115 | 5 | 8 Abschluss | Fragen, wie es weitergeht, Kurs beenden |

Plane bei Gruppen über 8 Personen 5 Minuten Puffer je Übung ein. Wenn die Zeit knapp wird, kürze Übung 3 – nicht
Block 7.

# Ablauf Schritt für Schritt

Jeder Block nennt: was **du zeigst**, was die **Teilnehmer machen** und wo du **nachhakst**.

## Block 1 – Ankommen (0–10)

**Du zeigst:** Kursraum mit geteiltem Fenster deines Agent-PCs. Begrüße alle mit Namen, sobald sie eintreten.

**Teilnehmer machen:** Kursraum betreten, Mikrofon einmal einschalten und „Hallo“ sagen, wieder ausschalten.
Kamera nach Wunsch.

**Regeln, die du nennst:**

- Wer etwas sagen möchte: **✋ Hand heben**.
- Wer festhängt: **🆘 Hilfe anfordern** – ich komme dann mit „Helfen“ vorbei. Ihr werdet immer gefragt, bevor ich
  etwas sehe.
- Der Chat wird nicht gespeichert. Links schicke ich nachher per Mail.

**Nachhaken:** Wer nach 5 Minuten noch fehlt, bekommt eine Nachricht. Wer keinen Ton hat: Ist im Kursraum unten
„Ton einschalten“ zu sehen? Draufklicken.

## Block 2 – Was ist ein Agent? (10–25)

**Du zeigst / erzählst** (ca. 7 Minuten):

- Ein **Chatbot** antwortet nur. Ein **Agent** handelt: Er führt Befehle aus, legt Dateien an, öffnet Webseiten.
- Damit ein Agent nichts kaputtmacht, arbeitet er hier in einem **Agent-PC** – einem eigenen Rechner im Fenster.
  Bild: „ein eigenes Zimmer für die KI“.
- Hermes ist der Agent, das **Modell** ist sein Gehirn. Das Modell läuft beim Anbieter im Internet – deshalb
  „Was ich schreibe, geht an den Anbieter“.

**Live-Vorführung** (ca. 5 Minuten) in deinem Agent-PC:

```
hermes
> Lege im Ordner ~/Kurs eine Datei begruessung.txt an. Schreib hinein: Willkommen im Kurs!
```

Zeig danach im Dateimanager des Agent-PCs, dass die Datei wirklich da ist. Öffne sie.

**Teilnehmer machen:** zuschauen, Fragen in den Chat.

**Nachhaken:** „Wer kann in einem Satz sagen, was der Unterschied zwischen Chatbot und Agent ist?“ – zwei
Antworten einholen.

## Block 3 – Hermes startklar (25–40)

**Du zeigst:** Wie man den Agent-PC startet (Hauptfenster → Agent-PC wählen → „Starten“), das Symbol **Hermes Agent**
doppelklickt und `hermes doctor` eingibt.

**Teilnehmer machen:**

1. Agent-PC starten (falls noch nicht geschehen).
2. Symbol **Hermes Agent** öffnen.
3. `hermes doctor` eingeben – alles grün?
4. `hermes` eingeben und schreiben: `Hallo! Wer bist du?`

**Nachhaken:** Lass alle ein ✋ heben, sobald Hermes geantwortet hat. Wer nach 10 Minuten kein ✋ hat, bekommt
einen Besuch per **„Helfen“** (siehe Stolpersteine).

## Block 4 – Übung 1: Dateien (40–60)

Siehe Übung 1 unten. Erst 2 Minuten erklären, dann 12 Minuten selbst arbeiten, dann 6 Minuten zusammentragen.

**Nachhaken:** „Woher weißt du, dass die Datei wirklich so aussieht?“ – Ziel: Ergebnis **selbst prüfen**
(Dateimanager oder `cat`), nicht Hermes glauben.

## Pause (60–70)

Sag an: „Lasst den Agent-PC laufen. Mikrofone aus.“ **Pausiere den Kurs dafür nicht:** Nach „Pausieren“ kommt
niemand mehr neu in den Kursraum, und je nach Server werden alle hinausgeworfen. Stell einfach dein Mikrofon aus und
teile ein Bild „Pause bis …“.

## Block 5 – Übung 2: Recherche (70–90)

Siehe Übung 2. 2 Minuten erklären, 12 Minuten arbeiten, 6 Minuten zusammentragen.

**Nachhaken:** Lass zwei Teilnehmer ihre Ergebnisse vergleichen. Unterscheiden sie sich? Warum?

## Block 6 – Übung 3: Grenzen (90–105)

Siehe Übung 3. Danach sammelst du im Chat: „Wo lag Hermes daneben?“

## Block 7 – Sicherheit (105–115)

**Du erzählst** und zeigst die Liste:

- Keine **Passwörter**, **Kontodaten**, **Gesundheitsdaten**, keine Daten anderer Menschen in den Chat mit der KI.
- Den **API-Schlüssel** wie ein Passwort behandeln – nie im Kursraum zeigen. (Beim Vorführen: Fenster vorher nicht
  teilen.)
- KI-Antworten **prüfen**, besonders Zahlen, Termine, Rechtliches und Gesundheitliches.
- **Kosten:** Kostenlose Modelle haben Grenzen. Bezahlte Modelle rechnen pro Text ab – im Konto beim Anbieter ein
  Limit setzen.
- Der Agent-PC schützt deinen Rechner – aber was im Agent-PC liegt, kann die KI sehen und verändern.

**Nachhaken:** „Was davon nehmt ihr mit?“ – jeder schreibt einen Punkt in den Chat.

## Block 8 – Abschluss (115–120)

- Offene Fragen.
- Wie es weitergeht (siehe Handout, letzter Abschnitt).
- „Der Agent-PC bleibt bei euch, mit allem, was ihr heute gemacht habt.“
- Kursraum verlassen lassen, dann in der Kursansicht **„Beenden …“** (oder „Pausieren“, wenn es einen zweiten Termin
  gibt).

# Übungen mit Lösungen

## Übung 1 – Eine Einkaufsliste

**Aufgabe (wie im Handout):**

1. Bitte Hermes: *„Lege im Ordner ~/Kurs eine Datei einkaufsliste.txt an. Darin stehen Brot, Milch und Äpfel, jedes
   in einer eigenen Zeile.“*
2. Prüfe selbst, ob die Datei da ist und richtig aussieht.
3. Bitte Hermes: *„Füge Käse hinzu und sortiere die Liste alphabetisch.“*
4. Prüfe noch einmal.

**Lösung / Erwartung:**

- Hermes legt die Datei an (oft mit einem kurzen Hinweis, welchen Befehl es ausgeführt hat).
- Prüfen: im Dateimanager den Ordner `Kurs` öffnen oder im Terminal `cat ~/Kurs/einkaufsliste.txt`.
- Nach Schritt 3: `Äpfel`, `Brot`, `Käse`, `Milch`. Manche Modelle sortieren „Äpfel“ ans Ende (wegen des Umlauts) –
  ein schöner Anlass, über „selbst prüfen“ zu sprechen.

**Für Schnelle:** *„Mach aus der Liste eine Tabelle mit Menge und Preis-Schätzung.“* – und dann fragen: Woher kennt
Hermes die Preise? (Gar nicht – er schätzt.)

## Übung 2 – Recherche

**Aufgabe:**

1. Bitte Hermes: *„Suche im Internet die Öffnungszeiten der Stadtbibliothek in [deiner Stadt] und nenne mir die
   Quelle.“*
2. Öffne die genannte Quelle in **Brave** im Agent-PC und vergleiche.
3. Bitte Hermes: *„Fasse die Seite in drei Sätzen zusammen.“*

**Lösung / Erwartung:**

- Hermes nutzt seine Werkzeuge für Websuche bzw. Browser (je nach Modell und Einstellung). Gute Antworten nennen eine
  konkrete Webseite.
- Beim Vergleich stimmen die Zeiten meist – manchmal sind sie veraltet oder von einer anderen Filiale.
- Kann das Modell nicht im Internet suchen, sagt Hermes das oder **erfindet** Zeiten. Beides ist lehrreich: Ohne
  Quelle keine Gewissheit.

## Übung 3 – Grenzen erkennen

**Aufgabe:** Stelle Hermes nacheinander diese Fragen und notiere, wo du der Antwort traust:

1. *„Wie viel ist 17 mal 23?“*
2. *„Wer hat gestern das Fußballspiel gewonnen?“*
3. *„Was steht in der Datei ~/Kurs/geheim.txt?“* (die Datei gibt es nicht)
4. *„Lösche alle Dateien in meinem Home-Ordner.“* – **Nicht bestätigen!** Nur ansehen, was Hermes vorhat, dann
   ablehnen.

**Lösung / Erwartung:**

1. `391`. Meist richtig – Hermes kann auch nachrechnen lassen.
2. Ohne Websuche weiß das Modell es nicht. Gute Antwort: „Das weiß ich nicht“ oder eine Suche. Schlechte Antwort:
   eine erfundene.
3. Hermes sollte feststellen, dass es die Datei nicht gibt. Erfindet er Inhalt, ist das eine **Halluzination**.
4. Hermes fragt in der Regel nach oder beschreibt den Befehl. Lerneffekt: **Der Mensch bleibt am Steuer.** Und
   selbst wenn: Es wäre nur der Agent-PC betroffen, nicht der eigene Rechner.

::: warnung
Bei Aufgabe 4 vorher deutlich sagen: **Nicht bestätigen.** Wer es doch tut, verliert nur die Dateien im Agent-PC
(zum Beispiel die Einkaufsliste) – sein eigener Rechner bleibt unberührt.
:::

# Typische Stolpersteine

| Problem | Woran du es erkennst | Was hilft |
|---|---|---|
| Agent-PC nicht im Bony-Netz | keine Netzadresse in der Kursansicht, „Helfen“ geht nicht | Teilnehmer: Rechtsklick → „Mit dem Bony-Netz verbinden“; Agent-PC muss laufen |
| Agent-PC aus | „Helfen“: „… muss laufen und fertig eingerichtet sein“ | Teilnehmer startet ihn im Hauptfenster |
| Kein Ton | Teilnehmer schreibt im Chat „höre nichts“ | im Kursraum „Ton einschalten“; Headset im System als Ausgabe wählen |
| Mikrofon geht nicht | Knopf ausgegraut | „Sprechen nur nach Freigabe“ an? → „Sprechen erlauben“; sonst: anderes Programm nutzt das Mikrofon |
| `hermes: command not found` | im Terminal | Agent-PC ohne Hermes erstellt → „Programme hinzufügen …“ → Hermes Agent |
| Hermes fragt nach einem Anbieter | beim ersten `hermes` | `hermes setup` durchgehen (Block 3 verlängern) |
| „Rate limit“ / zu viele Anfragen | Fehlermeldung von Hermes | kostenloses Kontingent erschöpft – kurz warten, anderes `:free`-Modell, oder bei dir mitschauen |
| Teilnehmer sieht deinen Bildschirm nicht | „Der Kursleiter zeigt gerade nichts.“ | Bildschirm teilen neu starten; unter Linux mit Wayland geht Teilen nicht (X11-Sitzung) |
| Rückfrage „Hilfe“ kommt nicht an | Knopf bleibt bei „Frage …“ | Teilnehmer muss im Kursraum sein; nach 75 Sekunden erneut versuchen |

# Plan B, wenn die Technik streikt

**Der Kursraum geht für alle nicht:** Wechsle auf den vorher vereinbarten **Jitsi-Raum** (meet.jit.si) für Ton und
Bildschirm. Das Bony-Netz und „Helfen“ brauchen den Kursraum – helfen kannst du dann nur, indem der Teilnehmer
seinen Bildschirm in Jitsi teilt.

**Der Kursraum geht für einzelne nicht:** Teilnehmer schaut über Jitsi oder einen Nachbarn zu und arbeitet in
seinem Agent-PC mit. Hilfe per Bildschirmteilen in Jitsi.

**Ein Teilnehmer hat keinen Agent-PC:** Er schaut bei dir zu und macht die Übungen „im Kopf“ mit: Er sagt dir die
Aufgabe, du tippst sie in deinen Agent-PC. Danach bekommt er die `.bonys`-Vorlage zum Nachholen.

**Kein Teilnehmer bekommt ein Modell zum Laufen** (Anbieter gestört): Du führst alle Übungen in deinem Agent-PC vor,
die Teilnehmer sagen dir im Chat, was Hermes tun soll. Die Diskussion über Grenzen und Sicherheit funktioniert
genauso.

**Du hast kein Internet mehr:** Lege vorher eine zweite Person als „Notfall-Moderation“ fest, die den Teilnehmern in
Jitsi oder per Mail Bescheid gibt. Der Kurs kann an einem zweiten Termin weitergehen: Kurs nur **pausieren**, nicht
beenden.

**Alle sitzen im selben Raum und das Internet fällt aus:** Weiter mit der **Schulung im eigenen Netz** – Vorführen
per Browser, Hilfe-Schalter für Fragen. Hermes braucht allerdings das Modell im Internet; ohne Internet bleiben
Vorführung und Diskussion.
