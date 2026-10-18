---
title: Einführung in Hermes Agent
subtitle: Handout für Teilnehmerinnen und Teilnehmer
lang: de
---

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
<!-- Teil B des Beispielkurses: Handout (2–4 Seiten, ohne Inhaltsverzeichnis). -->

## Dein Kurs

::: {.feld hoehe="1.3cm" text="Kurscode (bekommst du von der Kursleitung, z. B. K7QX-M3PA)"}
:::

::: {.feld hoehe="1.3cm" text="Datum und Uhrzeit"}
:::

::: {.feld hoehe="1.3cm" text="Plan B, falls der Kursraum nicht geht (z. B. Jitsi-Link)"}
:::

## A – Vor dem Kurs: Bony's Agents einrichten

Bitte **spätestens zwei Tage vor dem Kurs** erledigen. Es dauert etwa eine Stunde – das meiste davon ist Warten.

1. **Installieren:** Lade Bony's Agents von **github.com/zappotex/BonysAgents/releases/latest** und installiere es.
   Windows und macOS warnen beim ersten Start – das ist normal (Windows: „Weitere Informationen“ → „Trotzdem
   ausführen“; macOS: Systemeinstellungen → Datenschutz & Sicherheit → „Dennoch öffnen“).
2. **Rechner vorbereiten:** Erscheint beim Start „Rechner vorbereiten“, klicke auf **„Automatisch einrichten“**.
3. **Bony-Netz einschalten:** Klicke auf das **ⓘ** neben „Bony's Agents“ → **„Bony-Netz …“** → Häkchen
   **„Bony-Netz verwenden“** → **„Instanz anlegen“** → „Schließen“.
4. **Agent-PC erstellen:** **„+ Neuer Agent-PC“** → Name (z. B. `agent-kurs`) und Passwort eingeben → prüfen, dass
   **„Mit dem Bony-Netz verbinden“** und **„Hermes Agent“** angehakt sind → **„Erstellen und starten“**. Warten,
   bis sich der Agent-PC von selbst mit Desktop öffnet (15–60 Minuten).
5. **Dem Kurs beitreten:** **„Kurse“** → Kurscode eintragen → deinen Agent-PC wählen → deinen Namen →
   **„Beitreten“**.

## B – Vor dem Kurs: Hermes einrichten

1. Im Agent-PC das Symbol **Hermes Agent** doppelklicken.
2. `hermes setup` eingeben und den Fragen folgen. Für den Einstieg: Anbieter **OpenRouter**, ein Modell mit
   `:free` im Namen. Dafür brauchst du ein kostenloses Konto bei **openrouter.ai** und dort einen **API-Schlüssel**.
3. Zum Test: `hermes` eingeben und `Hallo!` schreiben.

Klappt etwas nicht? Kein Problem – im Kurs nehmen wir uns Zeit dafür.

## C – Am Kurstag

1. Bony's Agents öffnen, deinen Agent-PC **starten**.
2. **„Kurse“** → Kurs wählen → **„Kursraum betreten“**.
3. Du kommst mit Mikrofon und Kamera **aus** herein. Schalte sie selbst ein, wenn du möchtest.
4. **✋ Hand heben**, wenn du etwas sagen möchtest. **🆘 Hilfe anfordern**, wenn du festhängst.
5. Möchte die Kursleitung deinen Agent-PC sehen, wirst du **jedes Mal gefragt**: „Nur ansehen“, „Ansehen und
   bedienen“ oder „Ablehnen“. Mit **„Beenden“** trennst du jederzeit. Die Kursleitung sieht nur diesen Agent-PC –
   nie deinen eigenen Bildschirm.

## Übung 1 – Eine Einkaufsliste

1. Bitte Hermes: *„Lege im Ordner ~/Kurs eine Datei einkaufsliste.txt an. Darin stehen Brot, Milch und Äpfel, jedes
   in einer eigenen Zeile.“*
2. Prüfe **selbst**, ob die Datei da ist und richtig aussieht (Dateimanager → Ordner `Kurs`).
3. Bitte Hermes: *„Füge Käse hinzu und sortiere die Liste alphabetisch.“*
4. Prüfe noch einmal.

::: {.feld hoehe="2.2cm" text="Was ist dir aufgefallen?"}
:::

## Übung 2 – Recherche

1. Bitte Hermes: *„Suche im Internet die Öffnungszeiten der Stadtbibliothek in [deiner Stadt] und nenne mir die
   Quelle.“*
2. Öffne die Quelle in **Brave** im Agent-PC und vergleiche.
3. Bitte Hermes: *„Fasse die Seite in drei Sätzen zusammen.“*

::: {.feld hoehe="2.2cm" text="Stimmte die Antwort? Woran hast du es gemerkt?"}
:::

## Übung 3 – Grenzen erkennen

Stelle Hermes diese Fragen. Wo traust du der Antwort?

1. *„Wie viel ist 17 mal 23?“*
2. *„Wer hat gestern das Fußballspiel gewonnen?“*
3. *„Was steht in der Datei ~/Kurs/geheim.txt?“*
4. *„Lösche alle Dateien in meinem Home-Ordner.“* – **Nicht bestätigen!** Nur ansehen, was Hermes vorhat.

::: {.feld hoehe="2.2cm" text="Wo lag Hermes daneben?"}
:::

## Das gebe ich einer KI nicht

- keine Passwörter, Kontodaten oder Gesundheitsdaten,
- keine Daten anderer Menschen,
- meinen API-Schlüssel nur in `hermes setup` – nie in einen Chat und nie, während ich meinen Bildschirm teile.

Und: Antworten **prüfen**, besonders Zahlen, Termine und alles Rechtliche.

## Notizen

::: {.feld hoehe="4cm" text=""}
:::

## Wie es weitergeht

- Dein Agent-PC bleibt bei dir – mit allem, was du heute gemacht hast. Probier weiter!
- **Benutzerhandbuch** von Bony's Agents: auf der Releases-Seite (github.com/zappotex/BonysAgents/releases) und
  im Programm unter ⓘ → „Hilfe (Anleitung)“.
- **Videos:** youtube.com/@BonysAgents
- **Hermes Agent:** github.com/NousResearch/hermes-agent (Befehle: `hermes model` wechselt das Modell,
  `hermes update` aktualisiert, `hermes doctor` prüft)
