# Aufräumen und Abschluss

## 1. Die .conf aus Downloads löschen

Bony's VPN hat die Konfiguration beim Import **sicher abgelegt** – die Datei in Downloads brauchst du nicht mehr. Dort
kann sie jedes Programm lesen, das du startest.

Öffne den Dateimanager → **Downloads** → die `.conf` (oder das `.zip`) **löschen** und den **Papierkorb leeren**.

::: hinweis
Brauchst du die Konfiguration später woanders, erstellst du beim Anbieter einfach eine neue – oder exportierst sie
in Bony's VPN über **„Exportieren …“**.
:::

Fertig? Klick auf **„Prüfen“**.

## 2. Sicherheit in Kürze

- Nur ein kleiner **Helfer** hat Administrator-Rechte – und darf nur festgelegte Aktionen.
- **Schlüssel** liegen nur in `/etc/wireguard`, nur für root lesbar – in keiner Anzeige.
- **Befehle in einer .conf** (PostUp …) übernimmt Bony's VPN nur nach einer deutlichen Warnung.
- Der **Kill-Switch** gilt auch nach einem Neustart – bis du ihn ausschaltest.

## 3. Was du heute gelernt hast

- Ohne VPN sehen Internetanbieter und Webseiten viel – mit VPN sieht der **VPN-Anbieter** dein Ziel.
- Die `.conf` ist ein **Passwort**: holen, importieren, aus Downloads löschen.
- **Importieren → Verbinden → Prüfen**, dazu **Kill-Switch** und **automatisch verbinden**.
- **Privater, nicht anonym:** DNS prüfen, Tracker blocken, Anmeldungen trennen, Wegwerf-PC, Tor.

## Wie es weitergeht

- **Gleich beim Erstellen:** Im Fenster „Neuer Agent-PC“ gibt es den Abschnitt **VPN** – dort die `.conf` wählen,
  „Automatisch verbinden“ und „Kill-Switch“ anhaken. Der neue Agent-PC startet gleich mit Tunnel.
- **Von außen steuern:** Bony's Agents → laufender Agent-PC → Reiter **„VPN“**.
- **Auf dem eigenen Linux-Rechner:** Knopf **„VPN“** im Hauptfenster installiert Bony's VPN dort – dann gilt das VPN
  für alle Programme (mit Administrator-Passwort). Für Windows und Mac gibt es die offizielle WireGuard-App.
- **Video** „Bony's VPN“: youtube.com/@BonysAgents

Zum Schluss: das **Quiz**.
