---
title: Your own tools and skills for Hermes, Mission Control with Docker
subtitle: Schedule for the trainer (draft) – 3 hours
lang: en
---

::: warnung
This course package is a **draft**: outline and timetable are in place, the lessons aren't worked out yet. With the
editor (trainer edition) you can make your own version of it.
:::

# Profile

| | |
|---|---|
| **Level** | Expert |
| **Duration** | 180 minutes with a 15-minute break |
| **Target group** | People with experience in the terminal and with scripts |
| **Prerequisites** | Agent PC with Hermes and Docker set up; Confident use of the terminal; Basic knowledge of Python or Bash |

Before working this out, look up commands and file paths for skills and MCP in the current Hermes
documentation – they change between versions.

# Learning goals

1. explain how tools and skills are structured in Hermes
2. write and test a skill of your own
3. connect an MCP server
4. start Mission Control with Docker and observe agents
5. set the permissions and limits of your own tools

# Timetable

| Minute | Duration | Lesson | Type |
|---:|---:|---|---|
| 0 | 25 | 1 How Hermes uses tools | Explanation |
| 25 | 40 | 2 Writing a skill of your own | Exercise |
| 65 | 35 | 3 Connecting an MCP server | Hands-on |
| 100 | 40 | 4 Mission Control | Hands-on |
| 140 | 25 | 5 Limits and wrap-up | Discussion |

# Outline

## Lesson 1 – How Hermes uses tools (25 minutes)

**Goal:** Tell tools, skills and MCP apart.

- Look at /tools and the configuration
- Skills: structure and location according to the docs
- MCP in one sentence

## Lesson 2 – Writing a skill of your own (40 minutes)

**Goal:** A skill of your own works.

- Small skill: create a note with the date in ~/Course/notes
- Test it and read errors
- Check task (planned): skill file exists

## Lesson 3 – Connecting an MCP server (35 minutes)

**Goal:** Hermes uses a tool via MCP.

- Choose an official sample server
- Enter it in the Hermes configuration
- Limit permissions

## Lesson 4 – Mission Control (40 minutes)

**Goal:** Mission Control is running and shows the agent.

- Start Mission Control (Docker) in the Agent PC
- Look at agents and tasks in the browser
- Check task (planned): service running

## Lesson 5 – Limits and wrap-up (25 minutes)

**Goal:** Use your own tools responsibly.

- What may a tool of your own do?
- Updates and maintenance
- Outlook: letting several agents work together
