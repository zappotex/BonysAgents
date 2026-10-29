---
title: What is an MCP server? Hermes gets tools
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
2. An **Agent PC with Hermes Agent**. On the desktop there's **"Agent Apps"** – if it's missing: start the Agent PC,
   in the detail view next to "Programs" → **"Add programs …"** → Agent Apps.
3. **Set up Hermes:** **Hermes Agent** icon → `hermes setup` → **Nous** → a **free model**, sign in with your **own**
   account. To test: `hermes --tui` and "Hello!".
4. Join the course: **"Courses"** → course code → choose the Agent PC → **"Join"**.

## B – The essentials in brief

- An **MCP server** is a small program that offers an agent **tools**.
- Programs only from the **official source** – the "Agent Apps" list names it.
- The **checksum** must report **OK**. With **FAILED**: stop.
- An MCP server only gets **one folder** (`--root`).
- Pasting in the terminal: **Ctrl + Shift + V**.

## C – The commands

| Command | What it does |
|---|---|
| `hermes mcp add pdfcraft …` | registers PdfCraft with Hermes (copy the command from the list, confirm with **Y**) |
| `hermes mcp test pdfcraft` | checks the connection and shows the tools |
| `hermes mcp list` | shows all registered MCP servers |
| `hermes mcp remove pdfcraft` | unregisters PdfCraft again |
| `/reload-mcp` | reloads the MCP servers in a running Hermes |

## Exercise – Hermes works with PDFs

The files are in `~/Agent-Files/pdf`. Each time with "Use PdfCraft: …"

1. *"Summarize minutes.pdf. What was resolved?"*
2. *"Page 2 of minutes.pdf is sideways. Rotate it upright and save the result as minutes-upright.pdf."*
3. *"Merge invoice-march.pdf and invoice-april.pdf into invoices-total.pdf."*

After each step: **open** the file **yourself** and check it.

::: {.feld hoehe="2.2cm" text="What did you notice?"}
:::

## My next task for the agent

::: {.feld hoehe="2.2cm" text="Trigger – what the agent does – result"}
:::

## How to continue

- More programs with an MCP server: the **"Agent Apps"** list (online: zappotex.github.io/BonysAgents/agenten-apps).
  Many are still **alpha** – always work on a copy of important files.
- **User Guide**, chapter "Agent Apps": in the program under ⓘ → "Help (manual)".
- Next course package in the series: **"n8n basics: the first workflow"**.
- **Videos:** youtube.com/@BonysAgents
