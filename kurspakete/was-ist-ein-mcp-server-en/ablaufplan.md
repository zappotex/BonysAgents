---
title: Course "What is an MCP server? Hermes gets tools"
subtitle: Schedule for the trainer – 90 minutes, 3–10 participants with Hermes set up
lang: en
---

# Profile

| | |
|---|---|
| **Title** | What is an MCP server? Hermes gets tools |
| **Duration** | 90 minutes without a break |
| **Group** | 3–10 people; Hermes is set up (e.g. after "Introduction to Hermes Agent") |
| **Format** | Course over the internet with the course room of Bony's Agents (works just the same on site) |
| **Participants need** | Bony's Agents 0.24.0 or later, an Agent PC with Hermes and the "Agent Apps" list, internet, a headset |
| **You need** | Bony's Agents Trainer, a presentation Agent PC with Hermes set up, **without** PdfCraft |
| **Cost** | none – PdfCraft is free, Hermes runs with a free model |
| **Material** | Course package "What is an MCP server?" (schedule, handout, lessons with quiz and check tasks) |

First course in the series "Agents, MCP apps and n8n". By the end, everyone has installed PdfCraft from the official
source, registered its MCP server with Hermes and had Hermes edit real PDFs.

# Learning goals

By the end of the course, participants can …

1. explain in their own words what an **MCP server** is and why an agent needs one;
2. find the **"Agent Apps"** list and read an entry (status, license, source, checksum);
3. install a program from the **official source** and verify the **checksum**;
4. register an MCP server with **`hermes mcp add`** and check it with **`hermes mcp test`**;
5. have Hermes **summarize, rotate and merge** PDFs and **check** the result **themselves**;
6. explain why the agent may only work in an **approved folder**.

# Preparation

## One week before

- [ ] Create the course, choose "What is an MCP server?" under **"Course package"**.
- [ ] Send the invitation with the course code and the **handout**. Important: **set up Hermes beforehand** (handout,
  section A).
- [ ] Work through the course once yourself ("Work through", self-study mode) – that way the sample PDFs are also in
  your presentation Agent PC, and you see how your model handles PdfCraft.

## One or two days before

- [ ] Check whether the "Agent Apps" list still shows **"Tested"** for the PdfCraft entry (online list:
  zappotex.github.io/BonysAgents/agenten-apps). PdfCraft is **alpha** – changes are possible.
- [ ] **Remove** PdfCraft from your presentation Agent PC again (`hermes mcp remove pdfcraft`,
  `rm ~/.local/bin/pdfcraft-cli`) so you can demo blocks 2 and 4 – or keep a second presentation Agent PC without
  PdfCraft ready.
- [ ] In the course view: has everyone joined? Have participants already "done" lesson 1?

## 30 minutes before

- [ ] Start the presentation Agent PC, open a terminal and the "Agent Apps" list, make the font large (Ctrl + Plus).
- [ ] **"Start course"**, **"Open course room"**, share the Agent PC's window.

# Timetable

| Minute | Duration | Block | Content |
|---:|---:|---|---|
| 0 | 10 | 1 Getting started | Welcome, flow, Hermes answers (check) |
| 10 | 15 | 2 A head without hands | Explain MCP, live: Hermes without a PDF tool, quiz |
| 25 | 10 | 3 The list | Read the PdfCraft entry, quiz |
| 35 | 25 | 4 Setting up PdfCraft | install, checksum, `hermes mcp add`, test, restart |
| 60 | 20 | 5 Exercise | summarize, rotate, merge – check yourself |
| 80 | 10 | 6 Wrap-up | Round, outlook, quiz |

Blocks 1–6 correspond to lessons 1–6 in the course package. If time gets short, shorten block 3 (the list can be
explained along the way in block 4) – not block 4.

# Step by step

## Block 1 – Getting started (0–10)

**You show:** the course room, the shared Agent PC. The flow of the five steps.

**Participants do:** start the Agent PC, open the guide, `hermes --tui`, "Hello!" – then **"Check"**.

**Follow up:** in the course view you see who has "Hermes set up". Anyone who hasn't: right away via **"Help"** to
`hermes setup` (Nous → free model).

## Block 2 – A head without hands (10–25)

**You tell** (5 minutes): a language model understands and plans – to act, it needs tools. **MCP** is the common
language for tools, an **MCP server** the toolbox. It only gets one folder.

**Live demo** (5 minutes) in your Agent PC **without** PdfCraft:

```
Page 2 of ~/Agent-Files/pdf/minutes.pdf is sideways. Rotate it upright.
```

Comment on what Hermes does: a detour via the terminal? A suggestion to install something (**don't confirm**)? "It
knows what would need to be done – but it has no suitable tool."

**Participants do:** watch or try the same, then the **quiz**.

## Block 3 – The list (25–35)

**You show:** double-click **"Agent Apps"**, entry **PdfCraft**: alpha, tested, "What your agent can do with it",
license, checksum, expand "Install & connect to Hermes".

**Participants do:** the same in their Agent PC, then the **quiz**.

**Follow up:** "How do we know the download is genuine?" – official source **and** checksum.

## Block 4 – Setting up PdfCraft (35–60)

**You show** (5 minutes): copy the first block → terminal → **Ctrl + Shift + V** → show the line with **OK**. Second
block (`hermes mcp add pdfcraft …`) → tools appear → **Y** → **Saved 'pdfcraft'**. `hermes mcp test pdfcraft` →
**✓ Connected**. Restart Hermes or `/reload-mcp`.

**Participants do** (15 minutes): the same steps, then **"Check"**.

**Follow up:** anyone without ✋ after 10 minutes gets "Help". Most common causes: pasting with Ctrl + V instead of
Ctrl + Shift + V; only the first block run.

## Block 5 – Exercise (60–80)

See the exercise below. 2 minutes explaining, 13 minutes working, 5 minutes bringing it together.

**Follow up:** "Was page 2 the right way up for everyone?" – anyone who has it upside down has learned something
important: **check yourself**.

## Block 6 – Wrap-up (80–90)

Round "What worked, what didn't?", question to take away ("What task will you give your agent next?"), outlook on
the next courses, **quiz**, end the course.

# Exercise with solution

**Task (as in the guide):** each time with "Use PdfCraft: …"

1. *"Summarize minutes.pdf. What was resolved?"*
2. *"Page 2 of minutes.pdf is sideways. Rotate it upright and save the result as minutes-upright.pdf."*
3. *"Merge invoice-march.pdf and invoice-april.pdf into invoices-total.pdf."*

**Solution / expectation:**

1. The membership fee stays at **36 EUR** a year; summer party on **4 July**; a **rain barrel** for the community
   garden; all resolutions unanimous.
2. `minutes-upright.pdf`, page 2 upright. Some models rotate in the wrong direction – the page is then upside down.
3. `invoices-total.pdf` with two pages: invoice 2026-031 (March, 48.50 EUR), then 2026-042 (April, 41.90 EUR).

**For fast learners:** total of both invoices: **90.40 EUR**.

# Common pitfalls

| Problem | How you notice | What helps |
|---|---|---|
| Pasting doesn't work | `^V` appears in the terminal | **Ctrl + Shift + V** or right-click → Paste |
| Checksum **FAILED** | line in the terminal | delete the file, repeat the block; if it stays that way: stop, don't install |
| `hermes: command not found` | in the terminal | Agent PC without Hermes → "Add programs …" → Hermes Agent |
| PdfCraft doesn't show up in Hermes | Hermes uses the terminal instead of PdfCraft | restart Hermes or `/reload-mcp`; say "use PdfCraft" |
| File not found / no access | message from PdfCraft | PdfCraft may only work in `~/Agent-Files/pdf` |
| "Rate limit" | error message from Hermes | wait a moment, choose another free model with `/model` |
| "Agent Apps" list missing | no icon on the desktop | "Add programs …" → Agent Apps, or the online list in Brave |

# Plan B

**Downloading from GitHub doesn't work** (network, outage): you can still demo – show blocks 4 and 5 in your
prepared Agent PC, participants tell you in the chat what Hermes should do. They catch up on the installation as
homework (self-study mode, lesson 4).

**The free model is overloaded:** demo block 5 on your machine. The steps "list → install → register" work without a
model.

**PdfCraft has changed** (alpha): if the list no longer says "tested" or the installation doesn't work, switch to
**Filesystem (MCP)** – the same path, stable, without PDFs.
