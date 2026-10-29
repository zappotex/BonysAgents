---
title: Introduction to Hermes Agent
subtitle: Handout for participants
lang: en
---

## Your course

::: {.feld hoehe="1.3cm" text="Course code (you get it from the trainer, e.g. K7QX-M3PA)"}
:::

::: {.feld hoehe="1.3cm" text="Date and time"}
:::

::: {.feld hoehe="1.3cm" text="Plan B if the course room doesn't work (e.g. Jitsi link)"}
:::

## A – Before the course: setting up Bony's Agents

Please do this **at least two days before the course**. It takes about an hour – most of it is waiting. Your
computer needs at least **8 GB RAM** and **40 GB free disk space**. The course costs nothing: Hermes runs with a free
model.

1. **Install:** download Bony's Agents from **github.com/zappotex/BonysAgents/releases/latest** and install it.
   Windows and macOS warn on the first start – that's normal (Windows: "More info" → "Run anyway"; macOS: System
   Settings → Privacy & Security → "Open Anyway").
2. **Prepare your computer:** if "Prepare computer" appears at startup, click **"Set up automatically"**.
3. **Turn on the Bony Network:** click the **ⓘ** next to "Bony's Agents" → **"Bony Network …"** → tick **"Use the
   Bony Network"** → **"Create instance"** → "Close".
4. **Create an Agent PC:** **"+ New Agent PC"** → enter a name (e.g. `agent-course`) and password → check that
   **"Connect to the Bony Network"** and **"Hermes Agent"** are ticked → **"Create and start"**. Wait until the
   Agent PC opens by itself with its desktop (15–60 minutes).
5. **Join the course:** **"Courses"** → enter the course code → choose your Agent PC → your name → **"Join"**.

## B – Before the course: setting up Hermes

1. In the Agent PC, double-click the **Hermes Agent** icon.
2. Type `hermes setup` and follow the questions. When choosing the provider, pick the top entry **Nous** and a
   **free model** there. If Hermes asks you to sign in, sign in with your **own** account – never with someone
   else's.
   *Alternative:* provider **OpenRouter** with a model that has `:free` in its name. For that you need a free account
   at **openrouter.ai** and your own **API key** there.
3. To test: type `hermes --tui` (or `hermes`) and write `Hello!`.

Something doesn't work? No problem – we'll take time for it in the course.

## C – On the day of the course

1. Open Bony's Agents, **start** your Agent PC.
2. **"Courses"** → choose the course → **"Enter course room"**. With **"Guide"** you open the steps of each lesson
   next to it – with quiz and **"Check"**. The trainer only sees which lesson you're in and whether the check task is
   done – nothing of your files.
3. You come in with microphone and camera **off**. Turn them on yourself if you like.
4. **✋ Raise hand** if you want to say something. **🆘 Request help** if you're stuck.
5. If the trainer wants to see your Agent PC, you're **asked every time**: "View only", "View and control" or
   "Decline". With **"End"** you can disconnect at any time. The trainer only sees this Agent PC – never your own
   screen.

## Exercise 1 – A shopping list

1. Ask Hermes: *"Create a file shopping-list.txt in the folder ~/Course. It contains bread, milk and apples, each
   on its own line."*
2. Check **yourself** whether the file is there and looks right (file manager → folder `Course`).
3. Ask Hermes: *"Add cheese and sort the list alphabetically."*
4. Check again.

::: {.feld hoehe="2.2cm" text="What did you notice?"}
:::

## Exercise 2 – Research

1. Ask Hermes: *"Search the internet for the opening hours of the public library in [your town] and tell me the
   source."*
2. Open the source in **Brave** in the Agent PC and compare.
3. Ask Hermes: *"Summarize the page in three sentences."*

::: {.feld hoehe="2.2cm" text="Was the answer right? How did you notice?"}
:::

## Exercise 3 – Recognizing limits

Ask Hermes these questions. Where do you trust the answer?

1. *"What is 17 times 23?"*
2. *"Who won the football match yesterday?"*
3. *"What is in the file ~/Course/secret.txt?"*
4. *"Delete all files in my home folder."* – **Don't confirm!** Just look at what Hermes intends to do.

::: {.feld hoehe="2.2cm" text="Where did Hermes get it wrong?"}
:::

## What I don't give an AI

- no passwords, account details or health data,
- no data about other people,
- my API key only in `hermes setup` – never in a chat and never while I'm sharing my screen.

And: **check** answers, especially numbers, dates and anything legal.

## Notes

::: {.feld hoehe="4cm" text=""}
:::

## How to continue

- Your Agent PC stays with you – with everything you did today. Keep experimenting!
- **User Guide** of Bony's Agents: on the releases page (github.com/zappotex/BonysAgents/releases) and in the program
  under ⓘ → "Help (manual)".
- **Videos:** youtube.com/@BonysAgents
- **More course packages:** "Courses" → "Course packages" tab – for example **"Controlling Hermes via Telegram"**.
  You can also work through any course package **on your own** ("Work through", self-study mode).
- **Hermes Agent:** github.com/NousResearch/hermes-agent (commands: `hermes --tui` starts the clearer interface,
  `/tools` shows the tools, `/help` all commands, `hermes model` or `/model` switches the model, `hermes update`
  updates, `hermes doctor` checks)
