# Die Konfiguration holen

Bony's VPN ist das **Programm** für den Tunnel. Den **Server** dazu bringst du selbst mit: als kleine Datei mit der
Endung **`.conf`** von einem VPN-Anbieter – oder von deiner eigenen FRITZ!Box.

::: warnung
Die `.conf` enthält deinen **privaten Schlüssel**. Behandle sie wie ein **Passwort**: nicht zeigen, nicht
verschicken, nicht in den Kurs-Chat stellen.
:::

Arbeite im **Brave deines Agent-PCs** – dann landet die Datei gleich im richtigen Ordner **Downloads**.

## Weg A: Proton VPN (kostenloser Tarif)

1. Öffne `https://account.protonvpn.com` und melde dich an – oder leg ein kostenloses Konto an (Tarif
   **„Free“**, E-Mail-Adresse bestätigen).
2. Links **„Downloads“** wählen, dann nach unten zu **„WireGuard-Konfiguration“**.
3. Einen **Namen** für das Gerät eingeben (z. B. `agent-pc`), Plattform **„GNU/Linux“**.
4. Die **VPN-Optionen** so lassen. Unter **Server** einen **kostenlosen Server** (Free) wählen – oder den
   empfohlenen – und auf **„Erstellen“** klicken.
5. Im Fenster **„Herunterladen“** – die `.conf` liegt jetzt in **Downloads**.

::: hinweis
Die Seiten von Proton ändern sich ab und zu – heißen Knöpfe etwas anders, such nach „WireGuard“. Ist die Seite
englisch: „Downloads“ → „WireGuard configuration“ → „Create“ → „Download“.
:::

## Weg B: deine FRITZ!Box

Für unterwegs ins **eigene Heimnetz** – geht nur, wenn du zu Hause bist oder die FRITZ!Box von außen erreichst.

1. In der FRITZ!Box: **Internet → Freigaben → VPN (WireGuard)**.
2. **„Verbindung hinzufügen“** → **„Einzelgerät verbinden“** → Namen eingeben, bestätigen.
3. Die Einstellungen als **Datei herunterladen** (`.conf`) und in den Ordner **Downloads** des Agent-PCs legen.

Fertig? Klick auf **„Prüfen“**. Die Prüfung sieht nur nach dem **Dateinamen** – sie öffnet die Datei nicht.
