# Kurs 1: KI-Agenten für Einsteiger (Entwurf)

Oct 18, 2026 · @Bony Zappotex

## Überblick

In rund 2,5 Stunden richten Einsteiger ihren ersten eigenen KI-Agenten ein – sicher getrennt vom eigenen Rechner und ohne Kosten.

- **Zielgruppe:** Menschen ohne Vorkenntnisse, die KI-Agenten ausprobieren wollen
- **Dauer:** ca. 2,5 Stunden inkl. kurzer Pause
- **Stufe:** Anfänger
- **Voraussetzungen:** eigener Rechner (Linux, Windows oder Mac) mit mind. 8 GB RAM und 40 GB freiem Speicher, Internet, Telegram auf dem Handy (erst für Kurs 2 nötig)
- **Kosten:** keine – Hermes läuft im Kurs mit einem kostenlosen Modell

**Lernziele – nach dem Kurs können die Teilnehmer:**

1. erklären, was ein KI-Agent ist und worin er sich von einem Chatbot unterscheidet
2. mit Bony's Agents einen Agent-PC erstellen, starten und stoppen
3. Hermes Agent mit einem kostenlosen Modell starten und ihm Aufgaben geben
4. einschätzen, was ein Agent darf und warum er in einem eigenen Agent-PC läuft
5. einen Agent-PC zurücksetzen oder aus einer Vorlage neu erstellen

## Ablauf

Sieben Lektionen, zusammen ca. 155 Minuten plus 10 Minuten Pause nach Lektion 4.

| Nr. | Lektion | Dauer (min) | Art |
| --- | --- | --- | --- |
| 1 | Was ist ein KI-Agent? | 20 | Erklärung + Quiz |
| 2 | Bony's Agents installieren und ersten Agent-PC erstellen | 30 | Mitmachen |
| 3 | Rundgang im Agent-PC | 15 | Mitmachen |
| 4 | Hermes starten und mit einem kostenlosen Modell verbinden | 30 | Mitmachen |
| 5 | Erste Aufgaben für den Agenten | 30 | Übung |
| 6 | Sicherheit, Grenzen, Zurücksetzen | 20 | Erklärung + Übung |
| 7 | Abschluss und Ausblick | 10 | Gespräch |

## Lektionen

Jede Lektion hat Ziel, Schritte, eine Prüfaufgabe, eine Quizfrage und eine Notiz nur für den Kursleiter.

### Lektion 1 – Was ist ein KI-Agent? (20 min)

**Ziel:** Den Unterschied zwischen Chatbot und Agent verstehen.

1. Chatbot: beantwortet Fragen, handelt aber nicht selbst.
2. Agent: bekommt ein Ziel, plant Schritte und nutzt Werkzeuge – Websuche, Dateien, Terminal, Browser.
3. Beispiel: „Suche drei Rezepte mit Kartoffeln und speichere sie als Liste“ – der Agent sucht, liest, schreibt eine Datei.
4. Daraus folgt: Ein Agent kann auch Fehler machen oder auf falsche Anweisungen hereinfallen. Deshalb bekommt er einen eigenen Computer, den Agent-PC.

**Prüfaufgabe:** keine (Theorie).

**Quiz:** Was unterscheidet einen Agenten von einem Chatbot? – a) Er ist schneller · **b) Er führt mit Werkzeugen selbst Schritte aus** · c) Er braucht kein Internet

**Kursleiter-Notiz:** Mit einer Frage einsteigen: „Wer hat schon ChatGPT benutzt?“ Dann live zeigen, wie ein Agent eine Aufgabe in Schritte zerlegt (Vorführen-Funktion).

### Lektion 2 – Bony's Agents installieren und ersten Agent-PC erstellen (30 min)

**Ziel:** Ein eigener Agent-PC läuft.

1. Bony's Agents von der Download-Seite installieren (Windows: Setup.exe, Linux: .deb, Mac: .dmg).
2. Beim ersten Start die Einrichtung durchlaufen lassen (QEMU wird automatisch installiert).
3. „Neuer Agent-PC“: Name `mein-agent`, Festplatte 50 GB, Desktop Cinnamon, Apps Brave, Telegram, Hermes.
4. Erstellung starten und den Fortschritt beobachten. Im Schulungsmodus: stattdessen „Schulung beitreten“ mit dem Code des Kursleiters.

**Prüfaufgabe:** Agent-PC `mein-agent` existiert und läuft.

**Quiz:** Wo liegen deine eigenen Dateien, während der Agent arbeitet? – **a) Getrennt auf deinem Rechner, der Agent kommt nicht heran** · b) Im Agent-PC · c) In der Cloud

**Kursleiter-Notiz:** Die Erstellung dauert je nach Internet 10–20 Minuten. Bei Schulungen vorher eine Vorlage freigeben – dann geht es deutlich schneller. Zeit für Fragen nutzen.

### Lektion 3 – Rundgang im Agent-PC (15 min)

**Ziel:** Sich im Agent-PC zurechtfinden.

1. Desktop, Startmenü, Schreibtisch-Symbole zeigen.
2. Brave öffnen und eine Webseite aufrufen.
3. Terminal öffnen (Symbol „Terminal“) – keine Angst, wir tippen nur wenige Befehle.
4. Fenster vergrößern: Die Auflösung passt sich automatisch an.

**Prüfaufgabe:** Datei `~/Schreibtisch/hallo.txt` mit beliebigem Text anlegen.

**Quiz:** Wie heißt der Benutzer im Agent-PC? – a) admin · **b) agent** · c) root

**Kursleiter-Notiz:** Für Windows-Nutzer kurz erklären, dass es ein Linux-Desktop ist, der aber ähnlich funktioniert.

### Lektion 4 – Hermes starten und mit einem kostenlosen Modell verbinden (30 min)

**Ziel:** Hermes antwortet im Terminal.

1. Terminal öffnen und `hermes setup` eingeben.
2. Bei der Anbieter-Wahl den obersten Punkt **Nous** wählen und dort ein **kostenloses (free) Modell** auswählen. Fragt das Setup nach einer Anmeldung, meldet sich jeder mit seinem eigenen Konto an – niemals mit einem fremden.
3. Hermes starten: `hermes --tui` (moderne Oberfläche) oder `hermes`.
4. Erste Nachricht: „Hallo, wer bist du und was kannst du?“
5. `/tools` eingeben: zeigt die Werkzeuge des Agenten. `/help` zeigt alle Befehle. Mit `/model` lässt sich das Modell später jederzeit wechseln.

**Prüfaufgabe:** Hermes ist eingerichtet (Modell konfiguriert).

**Quiz:** Was zeigt `/tools`? – a) Die Einstellungen des Agent-PCs · **b) Die Werkzeuge, die Hermes benutzen darf** · c) Die installierten Apps

**Kursleiter-Notiz:** Kostenlose Modelle haben Nutzungsgrenzen und sind manchmal langsam – vorher ansprechen. Hermes braucht ein Modell mit mindestens 64K Kontext.

### Lektion 5 – Erste Aufgaben für den Agenten (30 min)

**Ziel:** Hermes löst selbstständig kleine Aufgaben.

1. Recherche: „Suche die Wettervorhersage für morgen in meiner Stadt und fasse sie in drei Sätzen zusammen.“
2. Datei: „Lege auf dem Schreibtisch eine Datei `einkauf.txt` mit einer Einkaufsliste für Spaghetti Bolognese an.“
3. Zusammenfassen: „Lies die Datei `hallo.txt` und schreibe sie als Gedicht um.“
4. Beobachten: Welche Werkzeuge nutzt Hermes? Fragt er nach Erlaubnis?

**Prüfaufgabe:** Datei `~/Schreibtisch/einkauf.txt` existiert und ist nicht leer.

**Quiz:** Was ist eine gute Aufgabe für einen Agenten? – a) „Mach was“ · **b) Ein klares Ziel mit erwartetem Ergebnis** · c) Möglichst viele Aufgaben gleichzeitig

**Kursleiter-Notiz:** Teilnehmer eigene Ideen ausprobieren lassen. Wer hängt, nutzt „Hilfe anfordern“.

### Lektion 6 – Sicherheit, Grenzen, Zurücksetzen (20 min)

**Ziel:** Risiken kennen und wissen, wie man neu anfängt.

1. Was ein Agent nie bekommen sollte: Bank-Zugangsdaten, Hauptpasswörter, Zugriff auf private Dateien.
2. Kurzes Beispiel für eine versteckte Anweisung auf einer Webseite (Prompt-Injection) – nur erklären, im Detail in Kurs 4.
3. Agent-PC stoppen und wieder starten.
4. Aus dem Agent-PC eine frische Vorlage machen und daraus einen zweiten Agent-PC erstellen.

**Prüfaufgabe:** Eine Vorlage existiert.

**Quiz:** Der Agent hat im Agent-PC etwas kaputtgemacht. Was tust du? – a) Rechner neu installieren · **b) Agent-PC löschen und aus der Vorlage neu erstellen** · c) Nichts, das geht nicht mehr

**Kursleiter-Notiz:** Die Botschaft: „Im Agent-PC darf man Fehler machen.“

### Lektion 7 – Abschluss und Ausblick (10 min)

**Ziel:** Gelerntes festigen, Lust auf mehr machen.

1. Rückblick: Was war überraschend, was schwierig?
2. Ausblick auf Kurs 2 „Hermes über Telegram steuern“: den Agenten vom Handy aus nutzen.
3. Hinweis auf den Selbstlern-Modus, die Kurs-Bibliothek und den YouTube-Kanal.

**Prüfaufgabe:** keine.

**Kursleiter-Notiz:** Handout verteilen, Feedback einsammeln.

## Offene Punkte vor dem ersten Kurs

Drei Punkte sind noch zu klären, bevor der Kurs echt laufen kann.

- [x] **Kostenloses Modell:** Im `hermes setup` bei der Anbieter-Wahl den obersten Punkt **Nous** wählen und dort ein Free-Modell nehmen. Vor dem Kurs noch prüfen: Nutzungsgrenzen und Geschwindigkeit bei vielen Teilnehmern gleichzeitig.
- [ ] **Prüfaufgabe Lektion 4:** Woran erkennt ein Skript sicher, dass Hermes eingerichtet ist (z. B. Eintrag in der Hermes-Konfiguration), ohne einen Schlüssel auszulesen?
- [ ] **Hardware:** Reichen 8 GB RAM auf dem Teilnehmer-Rechner im Praxistest?
- [ ] **Probedurchlauf:** Kurs einmal selbst komplett durchspielen und die Zeiten anpassen.

Quellen: [Hermes Agent Docs](https://hermes-agent.nousresearch.com/docs) · [Hermes Quickstart](https://hermes-agent.nousresearch.com/docs/getting-started/quickstart)
