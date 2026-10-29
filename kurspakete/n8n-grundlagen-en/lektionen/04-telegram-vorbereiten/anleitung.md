# Preparing Telegram

n8n sends the messages through a **Telegram bot of your own**. You create it in two minutes.

## 1. Create a bot

1. In Telegram, open the chat with **@BotFather** (blue checkmark – only that one is genuine).
2. Write `/newbot`.
3. Enter a **name**, e.g. *My news*.
4. Enter a **username** that ends in `bot`, e.g. *my_news_123_bot*.
5. BotFather replies with a **token** – a long string with a colon.

::: warnung
The **token is a password**: whoever has it can write in your name through the bot. Not in the course chat, don't
show it while you're sharing your screen. It only goes into n8n.
:::

## 2. Find your chat ID

The bot may only write to you once you've written to it first.

1. In Telegram, search for your new bot (username) and tap **Start** or write `/start`.
2. In the Agent PC, open this address in Brave – put your token in place of `YOUR-TOKEN`:

   ```
   https://api.telegram.org/botYOUR-TOKEN/getUpdates
   ```

3. Look for `"chat":{"id":` in the answer – the number after it is your **chat ID**. Write it down.

If it only says `"result":[]`, write something to your bot again and reload the page.

You need the token and the chat ID in the next lesson.
