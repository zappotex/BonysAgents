# Was ist ein VPN?

## Ohne VPN

Dein Rechner schickt alles über deinen **Internetanbieter** (oder das WLAN im Café) zur Webseite.

- Der Internetanbieter bzw. das WLAN sieht, **welche Seiten** du besuchst.
- Die Webseite sieht deine **echte Adresse** (IP) – und damit ungefähr deinen Ort.
- Bei `https://` sind die **Inhalte** verschlüsselt – aber nicht, **mit wem** du sprichst.

## Mit VPN

Ein VPN baut einen **verschlüsselten Tunnel** von deinem Rechner bis zu einem **VPN-Server**, zum Beispiel in den
Niederlanden. Erst dort geht es ins offene Internet.

- Internetanbieter und WLAN sehen nur noch: verschlüsselte Daten zu einem VPN-Server.
- Die Webseite sieht die Adresse des **VPN-Servers**, nicht deine.
- Der **VPN-Anbieter** kennt dafür dein Ziel – ihn wählst du mit Bedacht.

Bony's VPN nutzt **WireGuard**: modern, schnell und direkt im Linux-Kern.

## Was ein VPN bringt – und was nicht

| Bringt | Bringt nicht |
|---|---|
| Öffentliches WLAN: niemand liest mit | **Anonymität** – der VPN-Anbieter sieht, wohin du gehst |
| Internetanbieter sieht deine Seiten nicht | Wer sich anmeldet, ist erkannt – egal über welche Adresse |
| Webseiten sehen nicht deine Adresse | Cookies und Tracker erkennen dich wieder |
| Von unterwegs ins Heimnetz (FRITZ!Box) | Der Browser hat einen „Fingerabdruck“ |
| Kill-Switch: ohne Tunnel kein Internet | Schutz vor Viren oder Betrugsseiten |

::: tipp
Merksatz: **Ein VPN macht dich privater, nicht anonym.** Für mehr Privatsphäre kommen Gewohnheiten dazu – die übst
du in Lektion 6.
:::

Zum Schluss: das **Quiz**.
