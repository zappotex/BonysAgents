# Importieren und verbinden

## 1. Bony's VPN öffnen

Doppelklick auf **„Bony's VPN“** auf dem Schreibtisch. Es erscheint **„Noch keine Tunnel“**.

::: hinweis
Im Agent-PC fragt Bony's VPN nach **keinem Passwort** – der Agent-PC gehört dir allein. Auf deinem eigenen Rechner
fragt es nach dem Administrator-Passwort.
:::

## 2. Importieren

Klick auf **„Importieren …“**, links **„Downloads“**, deine `.conf` wählen, **„Öffnen“**. Der Tunnel erscheint mit
dem Namen der Datei.

Bony's VPN zeigt Adresse, DNS und Server – **nie den Schlüssel**. Er liegt jetzt geschützt im System
(`/etc/wireguard`, nur für root lesbar).

## 3. Verbinden

Klick auf **„Verbinden“**. Nach ein, zwei Sekunden steht **„verbunden“**, dazu der letzte Kontakt zum Server
(Handshake) und die übertragene Datenmenge.

## 4. Prüfen

- In Bony's VPN bei **„Öffentliche IP“** auf **„Prüfen“** – das ist jetzt die Adresse des VPN-Servers.
- Zum Vergleich in Brave `https://ipinfo.io` öffnen: Ort und Anbieter sind der VPN-Server (z. B. Niederlande).

::: datenschutz
Die Adresse, die du jetzt siehst, gehört dem **VPN-Anbieter** – sie darf jeder sehen. Deine eigene Adresse bleibt
verborgen.
:::

Fertig? Klick auf **„Prüfen“**.
