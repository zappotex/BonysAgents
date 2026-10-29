# The first workflow

We build: **RSS Feed Trigger** → **Telegram**. The names of the buttons are in **bold** here.

## 1. New workflow

In n8n, click **"Create workflow"**. Click the name at the top left and change it to *News via Telegram*.

## 2. The trigger: RSS Feed Trigger

1. Click **"Add first step…"**. **"What triggers this workflow?"** appears.
2. Type `RSS` in the search and choose **"RSS Feed Trigger"**.
3. Enter under **Feed URL**:

   ```
   https://feeds.bbci.co.uk/news/rss.xml
   ```

4. Under **Poll Times**, choose **"Every Hour"** – n8n then checks for new articles every hour.
5. Click **"Fetch Test Event"**. On the right, the latest article appears with `title`, `link` and more.
6. Close the window (top left, back to the canvas).

## 3. The work step: Telegram

1. Click the **+** on the right of the trigger, search for `Telegram` and choose **"Send a text message"**.
2. For the credential, **"Create new credential"** → paste your token from the last lesson under **Access Token** →
   **"Save"**. Now the token is stored safely in n8n.
3. Enter your chat ID under **Chat ID**.
4. Compose the message under **Text**: on the left you see the trigger's data. Drag **title** into the Text field,
   press Enter and drag **link** in as well. The field then reads something like:

   ```
   {{ $json.title }}
   {{ $json.link }}
   ```

5. Click **"Execute step"** – the message arrives on your phone.

## 4. Save and publish

1. Save: **Ctrl + S**.
2. Click **"Publish"** at the top right and confirm in the **"Publish workflow"** window. Afterwards it says
   **"Published"**.

From now on the workflow runs by itself as long as your Agent PC is running: when a new article appears, it comes to
your phone. Under **Executions** you see every run.

Done? Click **"Check"**.

::: tipp
No message arriving? Have you written to your bot in Telegram at least once (`/start`)? Is the chat ID right?
:::
