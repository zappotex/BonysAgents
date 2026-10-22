# Telegram vorbereiten

n8n schickt die Nachrichten über einen **eigenen Telegram-Bot**. Den legst du in zwei Minuten an.

## 1. Bot anlegen

1. Öffne in Telegram den Chat mit **@BotFather** (blauer Haken – nur dieser ist echt).
2. Schreib `/newbot`.
3. Gib einen **Namen** ein, z. B. *Meine Nachrichten*.
4. Gib einen **Benutzernamen** ein, der auf `bot` endet, z. B. *meine_nachrichten_123_bot*.
5. BotFather antwortet mit einem **Token** – einer langen Zeichenkette mit Doppelpunkt.

::: warnung
Der **Token ist ein Passwort**: Wer ihn hat, kann in deinem Namen über den Bot schreiben. Nicht in den Kurs-Chat,
nicht zeigen, während du deinen Bildschirm teilst. Er kommt nur in n8n.
:::

## 2. Deine Chat-ID herausfinden

Der Bot darf dir erst schreiben, wenn du ihm zuerst geschrieben hast.

1. Such in Telegram deinen neuen Bot (Benutzername) und tippe auf **Starten** bzw. schreib `/start`.
2. Öffne im Agent-PC in Brave diese Adresse – statt `DEIN-TOKEN` deinen Token einsetzen:

   ```
   https://api.telegram.org/botDEIN-TOKEN/getUpdates
   ```

3. Such in der Antwort `"chat":{"id":` – die Zahl dahinter ist deine **Chat-ID**. Notier sie.

Steht dort nur `"result":[]`, schreib deinem Bot noch einmal etwas und lade die Seite neu.

Den Token und die Chat-ID brauchst du in der nächsten Lektion.
