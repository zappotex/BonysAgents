# Kill-Switch und automatisch verbinden

## 1. Automatisch verbinden

Schalter **„Automatisch verbinden“** einschalten: Der Tunnel steht ab jetzt bei **jedem Start** des Agent-PCs. Es
verbindet sich immer nur ein Tunnel automatisch.

## 2. Kill-Switch

Schalter **„Kill-Switch“** einschalten. Bony's VPN meldet: *„Kill-Switch an: Ohne Tunnel ist das Internet jetzt
gesperrt.“*

Ohne Kill-Switch würde dein Agent-PC bei einem Verbindungsabbruch **unbemerkt ohne Tunnel** weitersurfen – mit
deiner echten Adresse. Mit Kill-Switch kommt dann **gar nichts** mehr raus. Das gilt auch nach einem Neustart – bis
du ihn ausschaltest.

## 3. Testen

1. Öffne in Brave `https://ipinfo.io`.
2. In Bony's VPN auf **„Trennen“** klicken.
3. In Brave neu laden (**F5**): *„Die Website ist nicht erreichbar“* – genau so soll es sein.
4. In Bony's VPN wieder **„Verbinden“**, in Brave neu laden – alles läuft wie vorher.

::: hinweis
Das eigene Netz des Agent-PCs bleibt mit Kill-Switch erreichbar, sonst könnte Bony's Agents ihn nicht steuern.
Weitere Ausnahmen (z. B. fürs Heimnetz) stehen im **Menü** unter **„Kill-Switch-Ausnahmen …“**.
:::

Fertig – und wieder verbunden? Klick auf **„Prüfen“**.
