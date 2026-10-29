---
title: Controlling Hermes via Telegram
subtitle: Schedule for the trainer (draft) – 1 h 30 min
lang: en
---

::: warnung
This course package is a **draft**: outline and timetable are in place, the lessons aren't worked out yet. With the
editor (trainer edition) you can make your own version of it.
:::

# Profile

| | |
|---|---|
| **Level** | Beginner |
| **Duration** | 90 minutes with a 10-minute break |
| **Target group** | Participants of “Introduction to Hermes Agent” or people with their first Agent PC |
| **Prerequisites** | Agent PC with Hermes set up (course package “Introduction to Hermes Agent”); Telegram on your phone |

The course builds on “Introduction to Hermes Agent”. Every participant creates their **own** bot; there's no
shared bot and no shared token.

# Learning goals

1. create a Telegram bot of your own and connect it to Hermes
2. decide who may write to the bot
3. give Hermes tasks from your phone and check the result in the Agent PC
4. treat the bot token like a password

# Timetable

| Minute | Duration | Lesson | Type |
|---:|---:|---|---|
| 0 | 20 | 1 Creating a Telegram bot | Hands-on |
| 20 | 25 | 2 Connecting Hermes to the bot | Hands-on |
| 45 | 25 | 3 Tasks from your phone | Exercise |
| 70 | 10 | 4 Safety and wrap-up | Explanation + quiz |

# Outline

## Lesson 1 – Creating a Telegram bot (20 minutes)

**Goal:** A bot of your own with a token exists.

- In Telegram, open @BotFather, /newbot, choose a name and username
- Only transfer the token into the Agent PC – never into a chat, never while screen sharing
- Why one bot per participant?

## Lesson 2 – Connecting Hermes to the bot (25 minutes)

**Goal:** Hermes answers in Telegram.

- Go through hermes setup or the gateway setup for Telegram
- Enter your own Telegram ID as the only allowed person
- Check task (planned): gateway service running (template “Service running”)

## Lesson 3 – Tasks from your phone (25 minutes)

**Goal:** Hermes completes a task that came via phone.

- From Telegram: “Create ~/Course/note.txt with three ideas for the weekend”
- Check it yourself in the Agent PC
- What happens when the Agent PC is off?

## Lesson 4 – Safety and wrap-up (10 minutes)

**Goal:** Know the risks of a reachable agent.

- Whoever reaches the bot controls the agent – allow list
- Revoke the token (/revoke) if it was shown by accident
- Outlook: automating tasks
