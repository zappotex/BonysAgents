---
title: Bony's VPN – sicher und privater ins Internet
subtitle: Handout für Teilnehmerinnen und Teilnehmer
lang: de
---

## Dein Kurs

::: {.feld hoehe="1.3cm" text="Kurscode (bekommst du von der Kursleitung)"}
:::

::: {.feld hoehe="1.3cm" text="Datum und Uhrzeit"}
:::

## A – Vor dem Kurs

1. **Bony's Agents ab Version 0.23.0** – ältere Versionen aktualisieren (ⓘ → „Nach Updates suchen“ bzw. die
   Aktualisierungsverwaltung unter Linux).
2. Ein **Agent-PC mit Bony's VPN**: Auf dem Schreibtisch liegt das Symbol **„Bony's VPN“** – fehlt es: Agent-PC
   starten, in der Detailansicht bei „Programme“ → **„Programme hinzufügen …“** → „WireGuard VPN (Bony's VPN)“.
3. Ein **kostenloses Konto bei Proton VPN** (account.protonvpn.com, Tarif „Free“, E-Mail bestätigen) – oder Zugang
   zu deiner **FRITZ!Box**.
4. Dem Kurs beitreten: **„Kurse“** → Kurscode → Agent-PC wählen → **„Beitreten“**.

## B – Das Wichtigste in Kürze

| Begriff | Bedeutung |
|---|---|
| **VPN** | verschlüsselter Tunnel von deinem Rechner bis zu einem VPN-Server |
| **WireGuard** | die Technik dahinter – modern, schnell, im Linux-Kern |
| **`.conf`** | Datei vom Anbieter mit Server und deinem **privaten Schlüssel** |
| **Kill-Switch** | ohne Tunnel kein Internet – auch nach einem Neustart |
| **DNS** | die Frage „welche Adresse hat diese Seite?“ – soll durch den Tunnel gehen |

- Die `.conf` ist ein **Passwort**: nicht zeigen, nicht verschicken, nach dem Import aus Downloads löschen.
- Mit VPN sieht die Webseite die Adresse des VPN-Servers – dafür kennt der **VPN-Anbieter** dein Ziel.
- **Privater, nicht anonym:** Anmeldungen, Cookies und der Fingerabdruck des Browsers verraten dich weiter.

## C – Konfiguration holen (Proton VPN)

1. account.protonvpn.com → **Downloads** → **WireGuard-Konfiguration**
2. Name (z. B. `agent-pc`), Plattform **GNU/Linux**, einen **Free-Server** wählen → **„Erstellen“**
3. **„Herunterladen“** – im Brave des Agent-PCs, dann liegt sie in **Downloads**

Oder **FRITZ!Box:** Internet → Freigaben → VPN (WireGuard) → „Verbindung hinzufügen“ → „Einzelgerät verbinden“ →
Datei herunterladen.

## D – In Bony's VPN

1. **„Importieren …“** → Downloads → Datei → **„Öffnen“**
2. **„Verbinden“** – „verbunden“, Handshake, Datenmenge
3. **„Öffentliche IP“ → „Prüfen“** (oder ipinfo.io in Brave)
4. **„Automatisch verbinden“** und **„Kill-Switch“** einschalten
5. Test: „Trennen“ → Seite nicht erreichbar → „Verbinden“
6. Die `.conf` aus Downloads **löschen**, Papierkorb leeren

## E – Prüfseiten

| Was | Seite | Gut ist … |
|---|---|---|
| Adresse | `https://ipinfo.io` | Ort und Anbieter des VPN-Servers |
| DNS | `https://www.dnsleaktest.com` | nur Server des VPN-Anbieters |
| Tracker | `https://coveryourtracks.eff.org` | Tracker geblockt (der Fingerabdruck bleibt meist) |

## F – Privater surfen

- **Privates Fenster mit Tor** in Brave: Alt + Umschalt + N
- **Eigener Agent-PC** für alles, wo du dich anmeldest
- **Wegwerf-PC** aus einer Vorlage für Unbekanntes – danach löschen
- **Tor Browser** als App in Bony's Agents (Intel/AMD-Rechner)

## Wo ich das VPN nutzen will

::: {.feld hoehe="2.2cm" text="z. B. Café-WLAN, Hotel, von unterwegs ins Heimnetz"}
:::

## Wie es weitergeht

- **Gleich beim Erstellen:** Fenster „Neuer Agent-PC“ → Abschnitt **VPN** → `.conf` wählen.
- **Von außen:** Bony's Agents → laufender Agent-PC → Reiter **„VPN“**.
- **Eigener Linux-Rechner:** Knopf **„VPN“** im Hauptfenster; Windows/Mac: offizielle WireGuard-App.
- **Video** „Bony's VPN“ und mehr: youtube.com/@BonysAgents
- Quellcode und Doku: github.com/zappotex/bonys-vpn
