---
title: n8n basics – the first workflow
subtitle: Handout for participants
lang: en
---

## Your course

::: {.feld hoehe="1.3cm" text="Course code (you get it from the trainer)"}
:::

::: {.feld hoehe="1.3cm" text="Date and time"}
:::

## A – Before the course

1. **Bony's Agents version 0.24.0 or later** – update older versions (ⓘ → "Check for updates" or the Update Manager on
   Linux).
2. An **Agent PC with n8n** and at least **4 GB RAM**. The **"n8n"** icon is on the desktop – if it's missing: start
   the Agent PC, in the detail view next to "Programs" → **"Add programs …"** → n8n.
3. **Telegram** on your phone or computer, with your own account.
4. Join the course: **"Courses"** → course code → choose the Agent PC → **"Join"**.

## B – The essentials in brief

| Term | Meaning |
|---|---|
| **Workflow** | a process that always runs the same way |
| **Trigger** | when the workflow starts – today: a new article in the RSS feed |
| **Node** | a work step – today: a message via Telegram |
| **Execution** | a run, with a log |
| **Publish** | the workflow runs by itself from now on |

- n8n **only runs in your Agent PC** (`http://localhost:5678`), not in the home network, not in the Bony Network.
- Your bot's **token** is a **password** – only enter it in n8n, never show it.
- After every change: **Ctrl + S** and **"Publish"** again.

## C – Creating a Telegram bot

1. In Telegram, open **@BotFather** (blue checkmark) → `/newbot` → name → username ending in `bot`.
2. Note the **token** securely.
3. Write `/start` to your bot.
4. Chat ID: open `https://api.telegram.org/botYOUR-TOKEN/getUpdates` in Brave, the number after `"chat":{"id":`.

::: {.feld hoehe="1.3cm" text="Username of my bot (the token does NOT belong here)"}
:::

## D – The workflow

1. **"Create workflow"** → name *News via Telegram*
2. **"Add first step…"** → **RSS Feed Trigger** → feed URL `https://feeds.bbci.co.uk/news/rss.xml`
   → Poll Times **"Every Hour"** → **"Fetch Test Event"**
3. **+** → **Telegram** → **"Send a text message"** → credential with token → chat ID → text: drag in **title** and
   **link** → **"Execute step"**
4. **Ctrl + S** → **"Publish"**

## E – More feeds

| Source | Feed URL |
|---|---|
| BBC News | `https://feeds.bbci.co.uk/news/rss.xml` |
| Ars Technica | `https://feeds.arstechnica.com/arstechnica/index` |
| The Guardian | `https://www.theguardian.com/world/rss` |
| NPR | `https://feeds.npr.org/1001/rss.xml` |

## My idea for the next workflow

::: {.feld hoehe="2.2cm" text="Trigger – steps – result"}
:::

## How to continue

- **Saving:** in the workflow **"…"** → **"Export JSON"**; importing: **"…"** → **"Import"** → **"From file"**.
- **User Guide**, chapter "n8n": in the program under ⓘ → "Help (manual)".
- n8n documentation: docs.n8n.io.
- Next course in the series: **Hermes and n8n as a team**.
- **Videos:** youtube.com/@BonysAgents
