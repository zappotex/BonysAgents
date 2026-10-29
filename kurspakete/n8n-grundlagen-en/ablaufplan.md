---
title: Course "n8n basics: the first workflow"
subtitle: Schedule for the trainer – 90 minutes, 3–10 participants without prior knowledge
lang: en
---

# Profile

| | |
|---|---|
| **Title** | n8n basics: the first workflow |
| **Duration** | 90 minutes without a break |
| **Group** | 3–10 people, no prior knowledge needed (Hermes isn't needed) |
| **Format** | Course over the internet with the course room of Bony's Agents (works just the same on site) |
| **Participants need** | Bony's Agents 0.24.0 or later, an Agent PC with n8n (at least 4 GB RAM), Telegram on phone or computer, a headset |
| **You need** | Bony's Agents Trainer, a presentation Agent PC with n8n and an account, your own Telegram bot |
| **Cost** | none |
| **Material** | Course package "n8n basics" (schedule, handout, lessons with quiz and check tasks), list of RSS feeds (in lesson 6) |

By the end, everyone has a published workflow that sends new articles from an RSS feed via Telegram, and a saved copy
of it. The course belongs to the series "Agents, MCP apps and n8n" but stands on its own.

# Learning goals

By the end of the course, participants can …

1. explain what a **workflow** is: trigger, nodes, connections, executions;
2. open **n8n** in the Agent PC and create their own account;
3. create a **Telegram bot** and treat its **token** like a password;
4. build, test and **publish** an **"RSS → Telegram"** workflow;
5. **adapt** the workflow (another feed, another time, another message);
6. save a workflow with **"Export JSON"** and know where n8n stores its data.

# Preparation

## One week before

- [ ] Create the course, choose "n8n basics" under **"Course package"**.
- [ ] Send the invitation with the course code and the **handout**. Important: an Agent PC **with n8n** and **at least
  4 GB RAM**, install Telegram beforehand.
- [ ] Decide: **everyone their own bot** (recommended) or a shared course bot.
- [ ] Work through the course once yourself (self-study mode) – that way you have a finished demo workflow.

## One or two days before

- [ ] Check the RSS feeds from lessons 5 and 6 once with **"Fetch Test Event"** (addresses rarely change, but
  sometimes they do).
- [ ] In the course view: has everyone joined? Is everyone's Agent PC running?

## 30 minutes before

- [ ] Start the presentation Agent PC (n8n then needs about a minute), open n8n in Brave, zoom to 125 %.
- [ ] Create the Telegram credential in your demo n8n beforehand – that way you never have to show the token.
- [ ] **"Start course"**, **"Open course room"**, share the Agent PC's window.

# Timetable

| Minute | Duration | Block | Content |
|---:|---:|---|---|
| 0 | 5 | 1 Getting started | Welcome, flow, "What do you do the same way every week?" |
| 5 | 10 | 2 What is a workflow? | Trigger, node, connection, execution; quiz |
| 15 | 15 | 3 Opening n8n | "n8n" icon, create an account, look around (check) |
| 30 | 10 | 4 Preparing Telegram | Bot at BotFather, chat ID via getUpdates |
| 40 | 25 | 5 The first workflow | RSS Feed Trigger → Telegram, test, publish (check) |
| 65 | 15 | 6 Your own variant | another feed, another time, a nicer message |
| 80 | 10 | 7 Saving and wrap-up | Export JSON (check), round, quiz |

Blocks 1–7 correspond to lessons 1–7 in the course package. If time gets short, shorten block 6 – not block 5.

# Step by step

## Block 1 – Getting started (0–5)

**You show:** the course room, the shared Agent PC. The flow. **Opening:** "What do you do every week, always the
same way?" – two or three examples.

## Block 2 – What is a workflow? (5–15)

**You tell:** "When mail arrives, I put it in the tray" – trigger, steps, the way in between. Show your finished
workflow: two nodes, one connection, **Executions** below.

**Participants do:** listen, **quiz**.

## Block 3 – Opening n8n (15–30)

**You show:** double-click **"n8n"** → **"Set up owner account"** → skip the questions with **"Continue"** →
overview.

**Participants do:** the same, then **"Check"**.

**Follow up:** "The account only applies to your n8n – remember the password." Anyone without the icon: "Add
programs …" → n8n (takes a few minutes – watch along with you in the meantime).

## Block 4 – Preparing Telegram (30–40)

**You show** (on your phone via the camera or as a picture): @BotFather → `/newbot` → name → username ending in
`bot` → token. **Never show the real token.** Then `/start` to your own bot and `getUpdates` in Brave.

**Participants do:** create their own bot, note the chat ID.

**Follow up:** "Where do you keep the token?" – only in n8n, not in the chat.

## Block 5 – The first workflow (40–65)

**You show** step by step, participants build along: **"Create workflow"** → name → **"Add first step…"** → **RSS
Feed Trigger** → feed URL → Poll Times **"Every Hour"** → **"Fetch Test Event"** → **+** → **Telegram** → **"Send a
text message"** → credential → chat ID → text (drag in title and link) → **"Execute step"** → message arrives →
**Ctrl + S** → **"Publish"**.

**Participants do:** finish building, **"Check"**.

**Follow up:** raise ✋ as soon as the test message is on the phone. Anyone without one after 15 minutes: "Help".

## Block 6 – Your own variant (65–80)

See the exercise below.

## Block 7 – Saving and wrap-up (80–90)

**You show:** **"…"** → **"Export JSON"** → file in the Downloads folder. Import into another n8n via **"Import"** →
**"From file"**.

**Participants do:** export, **"Check"**, **quiz**.

**Wrap-up:** "Which process would you automate next?" Outlook on "Hermes and n8n as a team". End the course.

# Exercise with solution (block 6)

**Task:** carry out two or three points from the guide – another feed, another time, a nicer message, a second
workflow.

**Solution / expectation:**

- Another feed: swap the feed URL, **"Fetch Test Event"** shows new data right away.
- Another time: Poll Times **"Every Day"** with hour and minute.
- A nicer message: text e.g. `📰 {{ $json.title }}` + line break + `{{ $json.link }}`; under **Additional Fields**
  turn off **Append n8n Attribution**.
- After every change **Ctrl + S** and **"Publish"** again.

**For fast learners:** a **"Filter"** node between the trigger and Telegram, condition "contains" on the title.

# Common pitfalls

| Problem | How you notice | What helps |
|---|---|---|
| n8n page stays empty | Brave shows "This site can't be reached" | n8n is still starting – wait a minute, F5 |
| No "n8n" icon | desktop | "Add programs …" → n8n |
| Agent PC too slow | n8n responds sluggishly | create the Agent PC with at least 4 GB RAM (the "New Agent PC" window warns if it's too little) |
| `getUpdates` shows `"result":[]` | Brave | write `/start` to the bot first, reload the page |
| "chat not found" | Telegram node red | wrong chat ID or nobody has ever written to the bot |
| "Unauthorized" | Telegram node red | token copied wrongly – create the credential again |
| `{{ $json.title }}` appears literally in the message | phone | switch the Text field to **Expression** or drag the values in |
| A change has no effect | the old message format keeps coming | **"Publish"** again after saving |
| Messages don't arrive right away | after publishing | that's correct – Poll Times "Every Hour" |

# Plan B

**Telegram doesn't work for someone** (no account, no phone number): they build the workflow along with a shared
course bot and your chat ID – or watch with you. They catch up on their own bot in self-study mode.

**n8n doesn't start for someone:** restart the Agent PC. If that doesn't help, they watch with you; the lessons can be
caught up later in self-study mode.

**An RSS feed is down:** switch to another feed from lesson 6.
