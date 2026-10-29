---
title: Security for AI agents: limiting permissions, recognizing prompt injection
subtitle: Schedule for the trainer (draft) – 2 hours
lang: en
---

::: warnung
This course package is a **draft**: outline and timetable are in place, the lessons aren't worked out yet. With the
editor (trainer edition) you can make your own version of it.
:::

# Profile

| | |
|---|---|
| **Level** | Advanced |
| **Duration** | 120 minutes with a 10-minute break |
| **Target group** | People who want to use agents in everyday life or at work |
| **Prerequisites** | Agent PC with Hermes set up; Basic knowledge from “Introduction to Hermes Agent” |

The prompt injection examples are harmless (they only ask, for example, to write a poem) and are only kept
in the Agent PC.

# Learning goals

1. explain why an agent has more risks than a chatbot
2. recognize prompt injection in examples
3. restrict Hermes' tools and permissions
4. store credentials so the agent doesn't need or see them
5. reset the Agent PC and revoke keys in an emergency

# Timetable

| Minute | Duration | Lesson | Type |
|---:|---:|---|---|
| 0 | 20 | 1 What can go wrong? | Explanation + quiz |
| 20 | 30 | 2 Recognizing prompt injection | Exercise |
| 50 | 25 | 3 Limiting permissions and tools | Hands-on |
| 75 | 20 | 4 Protecting credentials | Explanation + exercise |
| 95 | 15 | 5 The emergency | Exercise |

# Outline

## Lesson 1 – What can go wrong? (20 minutes)

**Goal:** Know the most important risks.

- Wrong answers, wrong actions, other people's instructions
- Why an isolated Agent PC
- Examples from practice

## Lesson 2 – Recognizing prompt injection (30 minutes)

**Goal:** Find hidden instructions in texts.

- Starting state: harmless sample pages in ~/Course/pages with hidden instructions
- Have Hermes summarize the pages – what happens?
- How to notice it, how to protect yourself

## Lesson 3 – Limiting permissions and tools (25 minutes)

**Goal:** Hermes may only do what's needed.

- Look at /tools, turn tools off
- Confirmation before dangerous commands
- A user of its own, no credentials in the Agent PC

## Lesson 4 – Protecting credentials (20 minutes)

**Goal:** Store keys correctly and revoke them.

- Where are keys (~/.hermes/.env) and who sees them?
- Set limits at the provider
- Revoke keys and create new ones

## Lesson 5 – The emergency (15 minutes)

**Goal:** Know what to do.

- Reset the Agent PC or recreate it from a template
- Revoke keys
- Checklist to take away
