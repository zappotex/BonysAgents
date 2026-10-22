# Übung: eigene Variante

Jetzt machst du den Workflow zu **deinem**. Such dir zwei oder drei Punkte aus:

1. **Anderer Feed:** Tausche die Feed URL, zum Beispiel:

   | Quelle | Feed URL |
   |---|---|
   | heise online (Technik) | `https://www.heise.de/rss/heise-atom.xml` |
   | Deutschlandfunk (Nachrichten) | `https://www.deutschlandfunk.de/nachrichten-100.rss` |
   | DER SPIEGEL (Schlagzeilen) | `https://www.spiegel.de/schlagzeilen/index.rss` |

   Oder such auf deiner Lieblingsseite nach „RSS“.

2. **Andere Zeit:** Bei **Poll Times** z. B. **„Every Day“** mit einer Uhrzeit – dann kommen die Neuigkeiten einmal
   am Tag.

3. **Schönere Nachricht:** Im Feld Text etwas davorschreiben, z. B. `📰 ` vor den Titel. Unter **Additional
   Fields** → **Append n8n Attribution** ausschalten – dann fehlt der Zusatz „sent automatically with n8n“.

4. **Zweiter Workflow:** Mit **„Create workflow“** einen zweiten für einen anderen Feed bauen.

Nach jeder Änderung: **Strg + S** und wieder **„Publish“**, sonst läuft die alte Fassung weiter.

::: tipp
**Für Schnelle:** Füg zwischen Auslöser und Telegram den Knoten **„Filter“** ein und lass nur Artikel durch, deren
Titel ein bestimmtes Wort enthält.
:::
