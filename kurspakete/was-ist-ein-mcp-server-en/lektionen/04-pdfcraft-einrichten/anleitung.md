# Setting up PdfCraft

Now Hermes gets its hands: you install **PdfCraft** and register its MCP server with Hermes.

## 1. Open the entry

In the **"Agent Apps"** list, click **"Install & connect to Hermes"** for the entry **PdfCraft**.

## 2. Install

Open a **terminal** in the Agent PC. Copy the first block (**"Copy"**) and paste it into the terminal
(**Ctrl + Shift + V**), then press Enter.

The commands download the latest version from the official site, verify the **checksum** and put the program in
`~/.local/bin`. Look out for this line:

```
pdfcraft-cli-…-linux-x86_64.tar.gz: OK
```

**OK** means: the file is unchanged. If it says **FAILED**, stop and get help.

## 3. Register with Hermes

Copy the second block – it starts with `hermes mcp add pdfcraft` – and paste it into the terminal. Hermes shows
PdfCraft's tools and asks whether it may use all of them: confirm with **Y**. At the end it says
**Saved 'pdfcraft'**.

::: hinweis
The command contains `--root …/Agent-Files/pdf`. That way PdfCraft may **only** read and save in this folder.
:::

## 4. Test and restart Hermes

Check the connection in the terminal:

```
hermes mcp test pdfcraft
```

If it says **✓ Connected** with a list of tools below (e.g. `doc_open`), everything is ready.

Hermes loads new MCP servers when it starts: end a running Hermes with `/exit` and start it again with
`hermes --tui` – or type `/reload-mcp` in the running Hermes.

Then ask: *"Which tools do you have for PDFs now?"*

Done? Click **"Check"**.

::: tipp
**It can be more convenient:** you can ask Hermes itself: *"Install PdfCraft from the agent list and set up the MCP
server."* It shows you beforehand what it intends to do. How to check these steps before you say "yes" is the topic
of a course of its own – today we do it once by hand so you know every step.
:::
