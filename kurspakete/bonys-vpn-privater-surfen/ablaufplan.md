---
title: Kurs „Bony's VPN: sicher und privater ins Internet“
subtitle: Ablaufplan für die Kursleitung – 90 Minuten, 3–10 Teilnehmer ohne Vorkenntnisse
lang: de
---

# Steckbrief

| | |
|---|---|
| **Titel** | Bony's VPN: sicher und privater ins Internet |
| **Dauer** | 90 Minuten ohne Pause |
| **Gruppe** | 3–10 Personen, keine Vorkenntnisse nötig |
| **Form** | Kurs über das Internet mit dem Kursraum von Bony's Agents (geht genauso vor Ort) |
| **Teilnehmer brauchen** | Bony's Agents ab 0.23.0, Agent-PC mit Bony's VPN und Brave, E-Mail-Adresse für Proton VPN (oder Zugang zur eigenen FRITZ!Box), Headset |
| **Du brauchst** | Bony's Agents Kursleiter, Vorführ-Agent-PC mit Bony's VPN, eigenes kostenloses Proton-Konto |
| **Kosten** | keine |
| **Material** | Kurspaket „Bony's VPN“ (Ablaufplan, Handout, Lektionen mit Quiz und Prüfaufgaben), Video „Bony's VPN“ auf youtube.com/@BonysAgents |

Am Ende hat jeder einen verbundenen WireGuard-Tunnel in seinem Agent-PC, mit Kill-Switch und automatischem
Verbinden, hat Prüfseiten für DNS und Tracker ausprobiert und die `.conf` aus Downloads gelöscht. Ehrlich bleiben:
**privater, nicht anonym.**

# Lernziele

Am Ende des Kurses können die Teilnehmer …

1. erklären, was ein **VPN** ist und wer mit und ohne VPN was sieht;
2. **Vorteile und Grenzen** nennen – ein VPN macht privater, nicht anonym;
3. eine **WireGuard-Konfiguration** (`.conf`) beim Anbieter holen und wie ein Passwort behandeln;
4. sie in **Bony's VPN** importieren, **verbinden** und die öffentliche Adresse **prüfen**;
5. **Kill-Switch** und **automatisch verbinden** einschalten und testen;
6. mit **Prüfseiten**, **privatem Fenster mit Tor** und **Wegwerf-PC** privater surfen.

# Grundsätze für dich

- **Zeig nie deine eigene `.conf`** und nie die Tunnel-Karte (Adresse, DNS, Endpunkt) länger als nötig. Teilnehmer
  holen ihre eigene Konfiguration – nie eine vom Kursleiter.
- **Kill-Switch an, bevor du trennst.** Sonst zeigt Brave beim Bildschirmteilen die echte Adresse deines Anschlusses.
- Teile nur das Fenster des **Vorführ-Agent-PCs** – nicht deinen Rechner, auf dem vielleicht eigene Tunnel laufen.
- Proton VPN ist ein **Beispiel**, keine Werbung. Wer einen anderen Anbieter mit WireGuard hat, nimmt den.

# Vorbereitung

## Eine Woche vorher

- [ ] Kurs anlegen, bei **„Kurspaket“** „Bony's VPN“ wählen.
- [ ] Einladung mit Kurscode und **Handout** verschicken. Wichtig: Agent-PC **mit Bony's VPN** (beim Erstellen unter
  „Programme“ „WireGuard VPN (Bony's VPN)“ anhaken), Proton-Konto möglichst **vorher** anlegen (E-Mail bestätigen).
- [ ] Den Kurs einmal selbst durcharbeiten (Selbstlern-Modus).

## Ein bis zwei Tage vorher

- [ ] Im Vorführ-Agent-PC eine Proton-Konfiguration erstellen und importieren – testen, ob der Free-Server antwortet.
  Danach die `.conf` aus Downloads löschen.
- [ ] In der Kursansicht: Sind alle beigetreten? Läuft bei allen der Agent-PC?

## 30 Minuten vorher

- [ ] Vorführ-Agent-PC starten, Bony's VPN öffnen. Tunnel **getrennt**, Kill-Switch **aus** – du führst beides vor.
- [ ] Brave mit einem leeren Tab, Zoom auf 125 %.
- [ ] **„Kurs starten“**, **„Kursraum öffnen“**, Fenster des Agent-PCs teilen.

# Zeitplan

| Minute | Dauer | Block | Inhalt |
|---:|---:|---|---|
| 0 | 5 | 1 Ankommen | Begrüßung, Ablauf, „Wo seid ihr im fremden WLAN?“ |
| 5 | 15 | 2 Was ist ein VPN? | ohne/mit VPN, Vorteile und Grenzen; Quiz |
| 20 | 15 | 3 Konfiguration holen | Proton Free (oder FRITZ!Box), `.conf` in Downloads (Prüfung) |
| 35 | 15 | 4 Importieren und verbinden | Importieren → Verbinden → Öffentliche IP, ipinfo.io (Prüfung) |
| 50 | 15 | 5 Kill-Switch | automatisch verbinden, Kill-Switch, Trennen-Test (Prüfung) |
| 65 | 15 | 6 Privater surfen | dnsleaktest, EFF-Test, privates Fenster mit Tor, Wegwerf-PC; Quiz |
| 80 | 10 | 7 Aufräumen und Abschluss | `.conf` löschen (Prüfung), Sicherheit, Ausblick, Quiz |

Die Blöcke 1–7 entsprechen den Lektionen 1–7 im Kurspaket. Wird die Zeit knapp, kürze Block 6 – nicht Block 4 und 5.

# Ablauf Schritt für Schritt

## Block 1 – Ankommen (0–5)

**Du zeigst:** Kursraum, geteilter Agent-PC, Symbol „Bony's VPN“. Ablauf. **Einstieg:** „Wo seid ihr mit dem
Laptop im fremden WLAN – Café, Hotel, Zug?“

## Block 2 – Was ist ein VPN? (5–20)

**Du erzählst:** Ohne VPN geht alles über Internetanbieter oder Café-WLAN, die Webseite sieht deine Adresse. Mit VPN
ein verschlüsselter Tunnel bis zum VPN-Server, die Webseite sieht dessen Adresse. Dann die Tabelle „bringt – bringt
nicht“, Schwerpunkt **nicht anonym**. Wer mag: das Video „Bony's VPN“, Kapitel 1–2 (etwa 1 Minute).

**Teilnehmer machen:** zuhören, Fragen, **Quiz**.

## Block 3 – Die Konfiguration holen (20–35)

**Du zeigst** in Brave: account.protonvpn.com → **Downloads** → **WireGuard-Konfiguration** → Name, **GNU/Linux** →
Free-Server → **„Erstellen“**. **Hier anhalten** – das Herunterladen machst du ohne geteilten Bildschirm.

**Teilnehmer machen:** Konto (falls noch keins), Konfiguration erstellen, herunterladen, **„Prüfen“**.

**Nachhaken:** „Was steckt in der Datei?“ – der private Schlüssel. „Wie behandelt ihr sie?“ – wie ein Passwort.

## Block 4 – Importieren und verbinden (35–50)

**Du zeigst:** Bony's VPN → **„Importieren …“** → Downloads → Datei → **„Öffnen“** → Tunnel erscheint →
**„Verbinden“** → „verbunden“, Handshake, Datenmenge → **„Öffentliche IP“ – „Prüfen“** → Brave: ipinfo.io zeigt den
VPN-Server.

**Teilnehmer machen:** dasselbe, **„Prüfen“**.

**Nachhaken:** ✋ heben, sobald ipinfo.io ein anderes Land oder den VPN-Anbieter zeigt.

## Block 5 – Kill-Switch und automatisch verbinden (50–65)

**Du zeigst:** **„Automatisch verbinden“** an → **„Kill-Switch“** an (Meldung abwarten) → Brave mit ipinfo.io →
**„Trennen“** → F5: „Die Website ist nicht erreichbar“ → **„Verbinden“** → F5: läuft wieder.

**Teilnehmer machen:** dasselbe, am Ende **verbunden** lassen, **„Prüfen“**.

**Nachhaken:** „Was wäre ohne Kill-Switch passiert?“ – unbemerkt ohne Tunnel weitersurfen. Wenn Zeit ist: Bony's
Agents → laufender Agent-PC → Reiter **„VPN“** – dasselbe von außen.

## Block 6 – Übung: privater surfen (65–80)

Siehe Übung unten.

## Block 7 – Aufräumen und Abschluss (80–90)

**Du zeigst:** Dateimanager → Downloads → `.conf` löschen → Papierkorb leeren. Dann die vier Punkte „Sicherheit in
Kürze“ und der Ausblick: VPN gleich beim Erstellen, Reiter „VPN“, Knopf „VPN“ für den eigenen Rechner.

**Teilnehmer machen:** aufräumen, **„Prüfen“**, **Quiz**.

**Abschluss:** „Wo nutzt ihr das VPN als Erstes?“ Noch einmal: **privater, nicht anonym.** Kurs beenden.

# Übung mit Lösung (Block 6)

**Aufgabe:** Punkte 1 (DNS) und 2 (Tracker) für alle, dazu mindestens einer von 3–5.

**Lösung / Erwartung:**

- **dnsleaktest.com → „Standard test“:** nur Server des VPN-Anbieters (bei Proton: „Proton AG“ o. ä.), keine des
  eigenen Internetanbieters.
- **coveryourtracks.eff.org → „TEST YOUR BROWSER“:** Tracker geblockt (Brave), aber meist „einzigartiger
  Fingerabdruck“. Genau die Grenze aus Block 2.
- **Privates Fenster mit Tor:** Brave-Menü → „Neues privates Fenster mit Tor“ (Alt + Umschalt + N); verbindet nach
  einigen Sekunden, langsamer, manchmal Captchas.
- **Wegwerf-PC / Tor Browser:** nur zeigen bzw. erklären – Installieren dauert zu lange für den Kurs.

**Für Schnelle:** Menü → **„Kill-Switch-Ausnahmen …“** ansehen: Welche Netze bleiben ohne Tunnel erreichbar – und
warum ist das Netz des Agent-PCs immer dabei?

# Typische Stolpersteine

| Problem | Woran du es erkennst | Was hilft |
|---|---|---|
| Kein Symbol „Bony's VPN“ | Schreibtisch | Detailansicht → „Programme hinzufügen …“ → „WireGuard VPN (Bony's VPN)“ |
| Proton-Bestätigungsmail kommt nicht | E-Mail | Spam-Ordner; sonst Plan B |
| Datei auf dem eigenen Rechner gelandet | Downloads im Agent-PC leer | Konfiguration im Brave **des Agent-PCs** neu erstellen – nicht per Mail schicken |
| Kein Handshake / „Server antwortet nicht“ | Bony's VPN | anderen Free-Server wählen, neu erstellen, alten Tunnel „Löschen …“ |
| Free-Konto schon belegt | verbindet nicht oder trennt gleich | Proton auf dem Handy trennen (ein Gerät gleichzeitig) |
| Warnung „Befehle in der Konfiguration“ | beim Import | nicht übernehmen – bei Proton/FRITZ!Box nicht zu erwarten |
| Nach dem Test kein Internet | Brave „nicht erreichbar“ | richtig so – Kill-Switch; in Bony's VPN wieder „Verbinden“ |
| DNS-Test zeigt eigenen Internetanbieter | dnsleaktest | Konfiguration ohne `DNS =`-Zeile → bei Proton neu erstellen |
| Prüfung „aufgeräumt“ schlägt fehl | Lektion 7 | Datei liegt noch in Downloads (ZIP entpackt?) oder nur im Papierkorb – Papierkorb leeren |

# Plan B

**Kein Proton-Konto möglich** (keine Mail, Bestätigung kommt nicht): Wer eine **FRITZ!Box** zu Hause hat und dort
sitzt, nimmt Weg B. Sonst schaut er bei dir zu und holt die Lektionen 3–5 im Selbstlern-Modus nach. **Gib niemals
deine eigene Konfiguration weiter** – auch nicht „nur für heute“.

**Proton ist gestört:** Zeig Import, Kill-Switch und Prüfseiten mit deinem vorbereiteten Tunnel; die Teilnehmer holen
die Konfiguration später nach.

**Agent-PC ohne Internet nach Block 5:** Kill-Switch an, Tunnel getrennt → „Verbinden“. Hilft das nicht, Kill-Switch
ausschalten, Tunnel neu verbinden, Kill-Switch wieder an.
