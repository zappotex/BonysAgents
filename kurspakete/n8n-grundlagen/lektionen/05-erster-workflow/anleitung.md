# Der erste Workflow

Wir bauen: **RSS Feed Trigger** → **Telegram**. Die Oberfläche ist englisch – die Namen der Knöpfe stehen hier
**fett**.

## 1. Neuer Workflow

In n8n auf **„Create workflow“**. Oben links auf den Namen klicken und ihn ändern in *Nachrichten per Telegram*.

## 2. Der Auslöser: RSS Feed Trigger

1. Auf **„Add first step…“** klicken. Es erscheint **„What triggers this workflow?“**.
2. In der Suche `RSS` eingeben und **„RSS Feed Trigger“** wählen.
3. Bei **Feed URL** eintragen:

   ```
   https://www.tagesschau.de/index~rss2.xml
   ```

4. Bei **Poll Times** **„Every Hour“** wählen – n8n schaut dann jede Stunde nach neuen Artikeln.
5. Auf **„Fetch Test Event“** klicken. Rechts erscheint der neueste Artikel mit `title`, `link` und mehr.
6. Das Fenster schließen (oben links zurück zur Arbeitsfläche).

## 3. Der Arbeitsschritt: Telegram

1. Rechts am Auslöser auf das **+** klicken, `Telegram` suchen und **„Send a text message“** wählen.
2. Bei der Zugangsart (Credential) **„Create new credential“** → bei **Access Token** deinen Token aus der letzten
   Lektion einfügen → **„Save“**. Jetzt liegt der Token sicher in n8n.
3. Bei **Chat ID** deine Chat-ID eintragen.
4. Bei **Text** die Nachricht zusammensetzen: Links siehst du die Daten des Auslösers. Zieh **title** in das Feld
   Text, drück die Eingabetaste und zieh **link** dazu. Im Feld steht dann etwa:

   ```
   {{ $json.title }}
   {{ $json.link }}
   ```

5. Auf **„Execute step“** klicken – auf deinem Handy kommt die Nachricht an.

## 4. Speichern und veröffentlichen

1. Speichern: **Strg + S**.
2. Oben rechts auf **„Publish“** und im Fenster **„Publish workflow“** bestätigen. Danach steht dort **„Published“**.

Ab jetzt läuft der Workflow von selbst, solange dein Agent-PC läuft: Erscheint ein neuer Artikel, kommt er aufs
Handy. Unter **Executions** siehst du jeden Durchlauf.

Fertig? Klick auf **„Prüfen“**.

::: tipp
Kommt keine Nachricht? Hast du deinem Bot in Telegram schon einmal geschrieben (`/start`)? Stimmt die Chat-ID?
:::
