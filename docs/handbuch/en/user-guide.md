---
title: User Guide
subtitle: Your own Agent PCs with AI – step by step
lang: en
---

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
<!-- English user guide, translated from ../benutzer.md (keep both in step). PDF: docs/handbuch/erstellen.sh.
     Images: bilder/en/ (automatic, English interface), bilder/eigene/ (by hand, shared with the German guide). Numbers ①②③ in the text belong to the markers in the images. -->

# Welcome

## What is Bony's Agents?

Bony's Agents is a program for your computer. With a few clicks it builds you a **second computer in a window**.
We call this second computer an **Agent PC**.

In an Agent PC, an artificial intelligence (AI) can work for you. It can search the internet, create files and
install programs. Your own computer stays protected: the AI can't get at your photos, documents or passwords.

Bony's Agents is **free software** (license GPL-3.0-or-later). There are no ads, no account and no telemetry.

## What is an Agent PC?

An Agent PC is a **virtual machine**: a computer that only runs as a program on your computer. It has:

- its own operating system (**Debian 13**, a free Linux),
- its own desktop with a start menu, windows and icons,
- ready-to-use programs: the **Brave** browser, the **Telegram** messenger and the AI agent **Hermes Agent**.

You can have several Agent PCs, for example one for the office and one for a course.

::: tipp
Think of an Agent PC as a room of its own for the AI. It may rearrange everything in there. The door to your flat
stays closed.
:::

## What is Hermes Agent?

**Hermes Agent** is an AI agent by Nous Research. You tell it in plain words what to do, for example: "Make a
shopping list" or "Find the opening hours of the public library". Hermes then carries out the steps itself in the
Agent PC.

Instead of or alongside Hermes, you can also choose **OpenClaw** (a personal assistant with chat integration) or
**Claude Code** (a coding assistant by Anthropic, needs a paid account).

## Which version do I need?

Bony's Agents comes in two editions:

| You want to … | Edition |
|---|---|
| use your own Agent PCs **or take part in a course** | **Bony's Agents** |
| **run courses** yourself | **Bony's Agents Trainer** |

This guide describes the normal edition. The trainer edition has its own Trainer Guide. You can switch at any
time: just install the other edition. Your Agent PCs, templates and settings are kept.

## What your computer needs

- **Windows 10 or 11**, **Linux** (Debian, Ubuntu, Linux Mint) or **macOS 14** (Sonoma) and later.
- **Memory (RAM):** 8 GB or more is good. Bony's Agents always leaves a quarter (at least 3 GB) for your computer;
  the Agent PC gets at least 2 GB.
- **Free disk space:** a set-up Agent PC takes a few gigabytes and grows as you use it – at most up to the size you
  chose (default 64 GB).
- **Virtualization** must be turned on. On most computers it is. If not, see the chapter "Frequently asked
  questions and problems".
- An **internet connection** for the setup.

## Language

Bony's Agents follows the language of your system: German on German systems, English everywhere else. You can
change it in the menu **ⓘ → "Sprache / Language"**; it takes effect after a restart.

Each Agent PC has its own language, which you choose when you create it (**"Agent PC language"**). It decides the
menus and folder names in the Agent PC, the keyboard suggestion and the language Hermes listens and speaks in.

# Installation

Download the file for your system from the releases page:
**github.com/zappotex/BonysAgents/releases/latest**

| System | File |
|---|---|
| Windows 10/11 | `BonysAgents-Setup-<version>.exe` |
| Debian, Ubuntu, Linux Mint | `bonys-agents_<version>_amd64.deb` (ARM computers: `_arm64.deb`) |
| Mac with Apple chip (M1, M2 …) | `BonysAgents-<version>-macos-applesilicon.dmg` |
| Mac with Intel processor | `BonysAgents-<version>-macos-intel.dmg` |

`<version>` is the number on the releases page, for example `0.22.0`.

## Windows

1. Double-click `BonysAgents-Setup-<version>.exe`.
2. Windows shows a blue warning: **"Windows protected your PC"**. That's normal, because Bony's Agents doesn't
   have a purchased Microsoft certificate (yet).
3. Click the small link **"More info"**.
4. Click **"Run anyway"** at the bottom.
5. In the installer, click **"Next"** and then **"Install"**. The installer also sets up QEMU (the program that
   runs the Agent PCs) and hardware acceleration.
6. If the installer asks you to: restart your computer once.

![Windows warns on first launch. First "More info", then "Run anyway".](bilder/eigene/windows-smartscreen.png){width=70%}

Afterwards you'll find **"Bony's Agents"** in the start menu.

## Linux (Debian, Ubuntu, Linux Mint)

1. Double-click `bonys-agents_<version>_amd64.deb`.
2. The package installer opens. Click **"Install"** and enter your password.
3. QEMU is installed along with it.

![The .deb file in the Linux Mint package installer](bilder/eigene/linux-paketinstallation.png){width=70%}

The package also adds a package source. Later updates therefore arrive as usual through your system's **Update
Manager**.

## macOS

**Which chip is in my Mac?** Apple menu → "About This Mac". If it says "Chip Apple M…", take the file with
`applesilicon`. If it says "Processor Intel …", take the file with `intel`.

1. Open the `.dmg` file and drag **"Bony's Agents"** onto **"Applications"**.
2. Open Bony's Agents in the Applications folder. macOS reports: *"Bony's Agents" Not Opened*. Click **"Done"**
   (not "Move to Trash").
3. Open Apple menu → **System Settings** → **Privacy & Security**. Scroll all the way down to **"Security"**. It
   says *"Bony's Agents" was blocked*. Click **"Open Anyway"** and confirm with your password or Touch ID.
4. Open Bony's Agents again and choose **"Open Anyway"** in the dialog.

![macOS reports on first launch that Bony's Agents was not opened](bilder/eigene/macos-nicht-geoeffnet.png){width=55%}

![System Settings → Privacy & Security → "Open Anyway"](bilder/eigene/macos-dennoch-oeffnen.png){width=75%}

**On macOS 14 (Sonoma)** it's quicker: in the Applications folder, right-click Bony's Agents → **"Open"** → **"Open"**
again in the dialog.

::: hinweis
If macOS says *"is damaged and can't be opened"*, open the **Terminal** program and enter:
`xattr -cr "/Applications/Bony's Agents.app"` – after that the app starts normally. These warnings only appear on
the very first launch.
:::

## Is the file genuine?

The releases page has a file `SHA256SUMS`. It contains a checksum for every file. If you want to be sure, compare
them, for example on Windows in PowerShell with `Get-FileHash .\BonysAgents-Setup-<version>.exe`. The list itself
is digitally signed.

## The first start

On the first start, Bony's Agents checks whether everything is there. If something is missing, **"Prepare
computer"** opens.

![Prepare computer: QEMU and access to acceleration are still missing here.](bilder/en/rechner-vorbereiten.png){width=65%}

1. Click **"Set up automatically"** ①. Bony's Agents installs what's missing. On Linux it asks for your password
   once, on Windows for your consent.
2. On macOS it installs QEMU via Homebrew. If Homebrew is missing, a terminal opens with the official installer.
   Confirm there with Enter and your password.
3. On Linux, Bony's Agents also recommends **Remmina** for remote access. That's optional.

Then Bony's Agents asks whether it may **check for updates once a day**. That's your decision. Nothing is ever
installed without your consent.

![The question about checking for updates](bilder/en/update-frage.png){width=50%}

Later you can check at any time with **"Check system"** at the top of the window whether everything is fine.

# Your first Agent PC

## The main window

![The main window without an Agent PC](bilder/en/hauptfenster-leer.png)

At first the list is empty. Click **"+ Create your first Agent PC"** or **"+ New Agent PC"** ① at the top right.

Once you have Agent PCs, the window looks like this:

![The main window with three Agent PCs](bilder/en/hauptfenster.png)

- ① **List** of your Agent PCs. The dot shows the state: green = running, grey = off, yellow = being set up, red =
  setup aborted. The small network icon shows whether the Agent PC is in the Bony Network. The ⇄ means: remote
  access is on.
- ② **Detail view** of the selected Agent PC with all buttons.
- ③ **"+ New Agent PC"**.
- ④ **"Courses"**: take part in a course.

At the top there are also **"Check system"**, **"VPN"** (Linux only), **"Add …"** (take in an existing Agent PC from
an SSD) and **"Templates"**. The small **ⓘ** next to the name opens the menu:

![The menu behind the ⓘ](bilder/en/menue.png)

There you'll find, among other things, "About Bony's Agents", this guide, the update settings, "Bony Network …",
"Sprache / Language" and under "View" the **display size** (larger or smaller, also with Ctrl + Plus and Ctrl +
Minus).

## Creating an Agent PC

Click **"+ New Agent PC"**. This window opens:

![New Agent PC: upper part](bilder/en/neuer-agent-pc.png){width=75%}

1. **Base** ①: leave "New installation (Debian 13)". (Once you have templates, you can choose one here – then the
   Agent PC is ready in seconds. For security courses there's also "New installation (Kali Linux)", see the chapter
   "Kali Linux".)
2. **Name** ②: for example `agent-buero`. Letters, digits, hyphen and underscore are allowed, at most 40
   characters, no spaces.
3. **User**: leave `agent`.
4. **Password** ③ and **Repeat**: think of a password for the Agent PC and write it down. You rarely need it, for
   example for remote access.
5. **CPU cores, Memory, Disk** ④: Bony's Agents suggests suitable values. You don't have to change anything. The
   disk only grows as far as it's actually filled.
6. **Agent PC language** and **Keyboard**: the language of the Agent PC – menus, folders and Hermes' voice input.
   It starts out as the language of Bony's Agents; the keyboard follows it (English: US layout) unless you pick
   another one.
7. **Desktop**: Cinnamon is the default and looks similar to Windows. Xfce is good for less powerful computers.

Scroll down in the window:

![New Agent PC: lower part with location, programs and AI tools](bilder/en/neuer-agent-pc-programme.png){width=75%}

8. **Location**: where the Agent PC should be stored. Usually on your computer. You can also choose an external
   SSD.
9. **Programs**: Brave, Telegram, remote access (RDP), the **Software Center**, the **Agent Apps** list and **n8n**
   are already ticked. You can also choose **Obsidian** (notes) and **Mission Control**.
10. **VPN**: only if you have your own WireGuard access (see the chapter "VPN").
11. **Bony Network**: the box "Connect to the Bony Network" only appears if you've turned on the Bony Network. For
    courses over the internet it must be ticked (see the chapter "Bony Network").
12. **AI tools**: **Hermes Agent** is ticked. OpenClaw and Claude Code are optional.
13. Click **"Create and start"**.

## Waiting for the setup

The very first time, Bony's Agents downloads the Debian system (about 450 MB). Then the Agent PC sets itself up
**invisibly in the background**. Depending on your computer and internet connection, this takes **15 to 60
minutes**.

![Setup in progress: progress and time remaining](bilder/en/einrichtung-laeuft.png)

- ① The bar shows the progress; above it are the current step and the estimated time remaining.
- ② **"Show anyway"** shows the console in large. You only need that if you're curious or something is stuck.

When everything is done, the Agent PC briefly turns off and then opens **by itself in a window** with the finished
desktop. You can close Bony's Agents in the meantime: the Agent PC then starts the next time you open the app.

::: hinweis
If the setup is interrupted (computer restarted, window closed, not enough memory), the list says "setup aborted"
with the probable cause. Then click **"Resume setup"** ①. Finished steps are skipped.
:::

![The setup was interrupted and can be resumed](bilder/en/einrichtung-abgebrochen.png)

## Start, shut down, full screen

In the detail view you'll find these buttons:

| Button | What it does |
|---|---|
| **Start** | turns on the Agent PC; its window opens |
| **Shut down** | shuts it down cleanly – right away, without asking inside the Agent PC |
| **Power off now** | appears if shutting down hangs: like pulling the plug |
| **Full screen** | shows the Agent PC across the whole monitor – back with **Ctrl + Alt + F** |
| **Copy SSH command** | for advanced users: log in from a terminal |
| **Update Agent PC** | fetches all updates for Debian and the programs in the Agent PC |
| **Save as template …** | turns the Agent PC into a template (see the chapter "Templates") |
| **Delete** | deletes the Agent PC with all files in it |

Next to the values in the detail view there are small buttons: **"Change performance …"** for the memory (see
"Programs hang or a window doesn't open" under "Frequently asked questions") and **"Enlarge disk …"** for the disk.

The Agent PC's screen size follows the window: just drag the window edge. If that ever doesn't work, you can choose
a fixed resolution under **"Screen"**. It applies from the next start.

::: warnung
**"Delete" cannot be undone.** Everything in the Agent PC is gone afterwards – including files the AI created for
you. Save anything important somewhere else first.
:::

## Inside the Agent PC

![The finished Agent PC with the Cinnamon desktop](bilder/eigene/agent-pc-desktop.png)

In the Agent PC you're **logged in automatically**. On the desktop there are icons for **Brave**, **Telegram** and
**Hermes Agent**, plus the programs you additionally chose during setup – in the picture, for example, Claude
Code, Mission Control, Obsidian and Bony's VPN (with the GNOME desktop they're in the bar on the left edge). A
double-click starts the program.

- **Brave** is a browser like Chrome or Firefox.
- **Telegram** is a messenger. You can sign in with your phone number – or leave it out.
- **Hermes Agent** opens a terminal window in which you write with Hermes.

The Agent PC uses the language and keyboard you chose when creating it. After a few minutes without input a screen
saver appears. It goes away with a key press, without a password.

## Adding programs later

Your Agent PC must be running for this. In the detail view, click **"Add programs …"** next to "Programs", tick
what you want and click "Install".

![Add programs](bilder/en/programme-hinzufuegen.png){width=65%}

Likewise there's **"Add desktop …"** if you'd like to try a different desktop. The previous one stays installed.

# Setting up Hermes

On the first start, Hermes needs to know **which AI model** to use. A model is the "brain" behind Hermes. The models
run at providers on the internet. You need an account there and an **API key** (a kind of password for programs).

## The first start

1. In the Agent PC, double-click **Hermes Agent**. A terminal opens.
2. Type `hermes setup` and press Enter.
3. The setup wizard asks you step by step: choose a provider, paste the API key, choose a model. Select with the
   arrow keys, confirm with Enter.
4. At the end you can optionally connect a Telegram bot. You can also skip that.
5. Check the installation with `hermes doctor`.
6. Start Hermes with `hermes`. Now you can write to it.

![Setting up Hermes with "hermes setup"](bilder/eigene/hermes-setup.png)

## Getting started for free

The easiest way: in `hermes setup`, choose the **top entry "Nous"** as the provider and a **free model** there. If
Hermes asks you to sign in, sign in with your **own** account – never with someone else's. The bundled course
packages work this way too.

An alternative is **OpenRouter**: models with `:free` in their name cost nothing. For that you need a free account
at openrouter.ai and your own API key there.

Useful in Hermes: `hermes --tui` starts a clearer interface, `/tools` shows the tools Hermes may use, `/help` all
commands, `/model` switches the model. Hermes needs a model with at least 64K context.

::: hinweis
Which models are free and how many requests you get changes often (as of October 2026: about 50 requests a day at
OpenRouter without credit). Free models are also sometimes slow. That's enough for a few exercises. If you work a
lot with Hermes, you'll soon hit the limit and then add credit or switch providers.
:::

## Switching providers

Type `hermes model` in the terminal. There you choose another provider or model, for example **Nous Portal**
(subscription by Nous Research), **OpenRouter**, **OpenAI** or your own server. `hermes setup` runs the whole wizard
again.

Hermes updates itself with `hermes update`. Easier is **"Update Agent PC"** in Bony's Agents: it updates everything
at once.

## Talking to Hermes

You can also **tell** Hermes what to do – and it answers with a voice. For that you need a microphone on your
computer, and the Agent PC must run in its **own window** (not in the background).

1. In the Agent PC, double-click **Hermes Agent (Voice)**. Hermes starts with voice input and read-aloud already on.
2. Press **Ctrl+B**, say your sentence and press **Ctrl+B** again.
3. Hermes shows what it understood and answers in text and with a voice.

Speech is recognized in the language of the Agent PC, directly in the Agent PC – your voice doesn't go to the
internet for that. In the normal Hermes window you turn on voice with `/voice on`. Mission Control works the same
way: in the chat and when creating a mission there's a **"Speak"** button, and every answer has a button to read it
aloud. The first time, the browser asks whether the page may use the microphone – allow it.

::: datenschutz
What you write to Hermes goes to the chosen provider. Don't enter passwords, account details or health data. Your
API key is only stored in the Agent PC (`~/.hermes/.env`), not on your computer.
:::

## OpenClaw and Claude Code

- **OpenClaw**: open the "OpenClaw" icon. The first time, the setup starts: choose a model, sign in, optionally
  connect a chat.
- **Claude Code**: open the "Claude Code" icon. It needs your **own paid Claude account**. You sign in in the
  browser on the first start. Claude Code is not open source. It starts in the folder `~/Projects`.

# More features

## Templates

A **template** is a fully set-up Agent PC for copying. New Agent PCs from a template are ready in seconds – without
download and without setup.

**Saving a template:** shut down the Agent PC → **"Save as template …"** → enter a name and description →
**"Create template"**. The original stays unchanged.

![Save as template](bilder/en/vorlage-speichern.png){width=70%}

The box **"Remove personal data"** is ticked by default. It deletes sign-ins, API keys, Hermes' memory, browser
data and your own files in the template. The programs stay installed. The box below lists exactly what is deleted.

**Using a template:** "+ New Agent PC" → choose the template at the top under **"Base"**.

- **Fast (linked)**: ready immediately, needs hardly any space. The template must stay on the same drive.
- **Independent (full copy)**: needs more space but works without the template.

A new Agent PC from a template keeps the template's language and keyboard.

**Managing templates:** the **"Templates"** button at the top of the main window. There you can rename, change the
description, delete, pass on and import.

![The "Templates" window](bilder/en/vorlagen.png)

**Pass on (.bonys) …** saves a template as a single file, for example for a course. Beforehand, Bony's Agents checks
in a copy that no sign-ins, tokens or keys are left in it. Enter **Creator** ① and **Version** ② and click
**"Check and export"** ③. Whoever receives the file simply drags it into the "Templates" window or clicks
**"Import …"**.

![Passing on a template as a .bonys file](bilder/en/vorlage-weitergeben.png){width=65%}

## Remote access

With remote access you can reach an Agent PC from another device in your home network, for example from a laptop
or tablet.

![The "Remote access" section in the detail view](bilder/en/fernzugriff.png)

1. Click **"Turn on remote access"** ①. You choose whether it stays on **only until shutdown** or **permanently**.
2. At the bottom, in the **"Remote access"** section ②, you see the address, port and user. **"Connect (RDP)"**
   opens the connection; **"Export profiles for another PC …"** creates ready-made files for other devices.
3. Log in with the user `agent` and the Agent PC's password.

::: warnung
Only use remote access in your **home network**. Do **not** open these ports in your router. Remote access is off by
default.
:::

## Obsidian

**Obsidian** is a note-taking program. You can tick it when creating the Agent PC or via "Add programs …". There's
then a shortcut on the Agent PC's desktop, and the empty notes folder `~/Agent Notes` (on German Agent PCs
`~/Agent-Notizen`) is already open. Obsidian is free of charge but not open source.

There's deliberately no shared folder between your computer and the Agent PC – otherwise the AI would have access to
your files.

## Mission Control

**Mission Control** is an overview and control center for your agents in the browser. It only runs in the Agent PC
(with Docker) and needs about 2 GB more disk space and 512 MB more memory.

![The "Mission Control" section in the detail view](bilder/en/mission-control.png)

In the **"Mission Control"** section ① you can see whether it's running. **"Open"** shows the interface in the Agent
PC, **"Update"** fetches the latest version. Forwarding to your own computer is off and only needs to be turned on
when you need it.

## Software Center

With the **Software Center** you install more programs with a click – for example the image editors GIMP or
Inkscape. Open **"Software"** from the start menu or the desktop, search for the program and click **"Install"**. The
programs come from **Flathub**, the official collection of Linux programs; you don't need a password for it. On its
first start, the Software Center loads the list of all programs once; that takes a minute.

![The Software Center in the Agent PC](bilder/eigene/software-center.png){width=75%}

## Tor Browser

The **Tor Browser** (off by default; choose it when creating the Agent PC or via "Add programs …") routes your
connections through the **Tor network**. Websites then don't see your IP address but that of a Tor computer
somewhere in the world. On its first start it downloads the official Tor Browser from torproject.org and checks its
signature – that takes a minute. Then click **"Connect"**.

Together with the Agent PC this means: what you do in the Tor Browser stays in the Agent PC and doesn't touch your
own computer. **You're still not completely anonymous** – the Agent PC runs on your computer, and anyone who signs
in with their name can be recognized. The Tor Browser itself points out that some of its protections may be weaker
on this system. For real anonymity, the Tor Project recommends Tails on a USB stick.

::: hinweis
The Tor Browser for Linux only exists for **x86_64**. On a Mac with an Apple chip it's therefore not offered.
:::

The Software Center doesn't fetch its updates itself – **"Update Agent PC"** in Bony's Agents does that.

## Kali Linux

Instead of Debian 13, an Agent PC can also have **Kali Linux** as its base system – the well-known Linux collection
for security testing. To do so, choose "New installation (Kali Linux)" under **Base** when creating it. Bony's
Agents then downloads the official Kali image from kali.download, checks its checksum and sets it up just as usual:
language, desktop, Brave, Hermes and the other programs.

On top of that come the **Kali tools** (already ticked): the ten best known, including **nmap**, **Metasploit**,
**Burp Suite**, **Wireshark**, **John the Ripper**, **Hydra** and **sqlmap**. You'll find them in the start menu at
the top left under the Kali categories. Wireshark may capture without the administrator password.

This lets you learn in the Agent PC how attacks work – separate from your own computer. That's ideal for courses:
every participant has their own Kali, and after an exercise you reset it with a starting state.

::: warnung
Use the Kali tools **only against your own computers or those you have explicit permission for**. Attacking other
people's systems without permission is a criminal offense – even "just to try it out".
:::

Good to know:

- Kali is only available as an Agent PC on **x86_64** and only with the **Xfce** desktop (tested that way). On a Mac
  with an Apple chip it's not offered.
- Give the Agent PC at least **6 GB of memory** if you use Metasploit and Burp Suite at the same time.
- The setup takes a bit longer than with Debian: at the end, Bony's Agents switches Kali to the normal kernel with
  graphics drivers (the cloud image comes with a kernel without graphics).
- For its cloud images Kali only publishes checksums, no signature. Bony's Agents therefore only downloads over an
  encrypted connection directly from kali.download.

## n8n

**n8n** puts together workflows with a few clicks: fetch mail, read RSS feeds, send Telegram messages, edit files,
query websites and services. It's ticked when creating an Agent PC and can be added later via "Add programs …".

- n8n runs in the Agent PC in **Docker** and is **only reachable inside the Agent PC itself**
  (`http://localhost:5678`) – neither in your home network nor in the Bony Network.
- Double-click **"n8n"** on the desktop to open it in Brave. The first time you open it, you create an account ("Set
  up owner account"). The account only applies to this n8n and stays in the Agent PC; after a restart, n8n needs
  about a minute until the page appears.
- Your workflows are kept in their own storage (Docker volume `n8n_data`) and survive every update.
- n8n needs about **1 GB more memory**. If the Agent PC is set too tight, the "New Agent PC" window warns you and
  suggests a better value.

![n8n in the Agent PC](bilder/eigene/n8n.png){width=75%}

::: hinweis
**License:** n8n is under the **Sustainable Use License**. The source code is open and you may use n8n for yourself
free of charge – but it's not an open-source license in the sense of the OSI. That's why n8n isn't included in
templates you pass on: whoever opens your template downloads n8n themselves from the official source.
:::

### n8n and Hermes together

According to the documentation of n8n and Hermes, the two work together like this:

1. **Hermes triggers a workflow (webhook).** Start the workflow in n8n with the **"Webhook"** node and publish it.
   The node shows the address ("Production URL"). Tell Hermes, for example: "Call this address with curl via POST
   and send the text …". The workflow can reply with the "Respond to Webhook" node.
2. **Hermes operates n8n via MCP.** In n8n, under **Settings → Instance-level MCP**, turn on access, enable the
   workflows you want and create an access key (token) under "Connect a client". Then enter in
   `~/.hermes/config.yaml`:

   ```yaml
   mcp_servers:
     n8n:
       url: "http://localhost:5678/mcp-server/http"
       headers:
         Authorization: "Bearer YOUR-TOKEN"
   ```

   After that, Hermes can find and run workflows. The token is a password – it stays in the Agent PC.
3. **n8n gives Hermes tasks.** Hermes has its own API server (only `127.0.0.1:8642`, with the key `API_SERVER_KEY`
   in `~/.hermes/.env`, started with `hermes gateway`). An **"HTTP Request"** node in n8n then sends a task to the
   endpoint `/v1/chat/completions`. But: n8n runs in Docker, and there `127.0.0.1` means the container itself. For
   this, the API server must listen on an address the container can reach (`API_SERVER_HOST`) – that's something
   for advanced users.

## Agent Apps

On the desktop of every new Agent PC there's **"Agent Apps"**: a list of well-known programs that have an **MCP
server** – Hermes can then operate them itself. They include, for example, PdfCraft (PDFs), PhotoCraft (images),
WordCraft, GridCraft and DeckCraft (texts, spreadsheets, presentations in Word, Excel and PowerPoint formats),
CADCraft and SolidCraft (design) as well as the official MCP servers for files and Git, and Playwright, with which
Hermes controls a browser.

![The "Agent Apps" list](bilder/eigene/agenten-apps.png){width=75%}

Bony's Agents does **not** install these programs by itself – you decide. Under **"Install & connect to Hermes"**,
each entry shows the commands to copy:

1. The official source (the vendor's download page).
2. The commands for the terminal – they download the latest version from the official site and verify the
   checksum.
3. The command that registers the MCP server with Hermes (`hermes mcp add …`).

You don't have to type anything yourself: tell Hermes, for example, "Install PdfCraft from the agent list and set up
the MCP server". It shows you beforehand what it intends to do. Files for the agents belong in the folder
`~/Agent-Files` (on German Agent PCs `~/Agent-Dateien`). The list works without internet and is shown in the Agent
PC's language; the latest version is always online at <https://zappotex.github.io/BonysAgents/agenten-apps/en/>.

Many of these programs are still young (alpha). Make a copy of important files first.

## VPN

With **Bony's VPN**, an Agent PC's internet traffic goes through your own **WireGuard tunnel**, for example to your
home router. You bring the access file (`.conf`) yourself.

- When creating: under **"VPN"** → tick "WireGuard VPN (Bony's VPN)" and choose the file.
- In a running Agent PC: the **"VPN"** section ① in the detail view – connect, disconnect, status, kill switch.

![The "VPN" section in the detail view](bilder/en/vpn.png)

The **kill switch** makes sure the Agent PC can't reach the internet at all without the tunnel.

For **your own computer** there's the **"VPN"** button at the top of the window on Linux. On Windows and macOS you'll
find the way to the official WireGuard app in the menu **ⓘ → Extras**.

# Bony Network

## What is the Bony Network?

The **Bony Network** is a private network over the internet. Through it, a trainer can reach your Agent PC during a
course – no matter where you are. You only need it for **courses over the internet**.

The Bony Network is **off by default**. As long as it's off, Bony's Agents makes no contact with a Bony Network
server.

::: datenschutz
When it's on, the server learns: your instance (a random ID, not a name), the names of your Agent PCs in the
network, their network addresses and whether they're online. For courses also the course name and the display
names. Nobody reaches your own computer this way – only the Agent PCs you choose for it.
:::

## Turning it on

1. Open the menu **ⓘ → "Bony Network …"**.
2. Tick **"Use the Bony Network"** ①.
3. The **Server** field ② already contains the suggestion. If your course names a different server, enter it and
   click **"Check"**.
4. Click **"Create instance"** ③. An **instance** is your registration with the server. You don't need an e-mail
   address or a password for it.

![The "Bony Network" window before turning it on](bilder/en/bony-netz-aus.png){width=60%}

Afterwards the window looks like this:

![Bony Network turned on, with an instance](bilder/en/bony-netz-an.png){width=60%}

- ① The Bony Network is on.
- ② The server and, below it, whether it answers.
- ③ The ID of your instance.
- ④ **"Delete instance …"** deletes your instance on the server – with your Agent PCs in the network, your courses
  and participations – and signs you out.

::: hinweis
If you also have **Bony's VPN** on your computer, both use the same registration. What you set here applies there
too.
:::

## Bringing Agent PCs into the Bony Network

- **New Agent PC:** in the "New Agent PC" window, the box **"Connect to the Bony Network"** is ticked as soon as
  the Bony Network is on. The Agent PC then joins the network during setup.
- **Existing Agent PC:** start it, **right-click** it in the list and choose **"Connect to the Bony Network"**.

![Right-click in the list: "Connect to the Bony Network"](bilder/en/kontextmenue.png)

In the list, a small **network icon** before the name shows the state: green = in the network, yellow = offline
(the Agent PC is off), grey = not connected.

## Your own server

If you run a Bony Network server yourself (for example a club or a school), enter its address in the **Server**
field of the "Bony Network" window and click **"Check"**. When you switch servers, the registration with the old
server is discarded; you create a new instance on the new one.

# Course packages – learning step by step

A **course package** is ready-made learning content: lessons with instructions, small check tasks, a quiz and a
handout to print. You can work through a course package **on your own** (self-study mode) – or it comes as part of
a **course** run by your trainer. A course is the event, the course package its content.

## The library

In the main window, click **"Courses"**. The first tab, **"Course packages"**, shows all course packages on your
computer with their level (Beginner, Advanced, Expert), duration and your progress.

![The "Course packages" library](bilder/en/kurspakete.png){width=80%}

- **Bundled** are "Introduction to Hermes Agent", "What is an MCP server?", "n8n basics" and "Bony's VPN" (finished)
  and five **drafts** – outlines for further course packages from "Controlling Hermes via Telegram" to "Local models,
  VPN and several agents". Each comes in German and English; the library shows the version in the language of Bony's
  Agents – tick **"All languages"** to see both.
- **"Import …"** takes in a `.bonyspaket` file you received. You can also simply drag it onto the window.
- **"From the internet …"** shows the course packages from the open library of Bony's Agents. Bony's Agents only
  downloads over HTTPS and checks every file before it goes into the library.
  On top of that there's the **community catalog**: course packages others have submitted and the Bony's Agents
  moderation has approved. In the catalog they're marked with "– Community". That's a technical check plus a
  decision by people, but **no signature by Bony's Agents**: before the first start, Bony's Agents therefore shows
  you the list of scripts, as with any third-party course package. This source is **off** until you turn on the
  switch **"Show community course packages"** in the catalog window. The first time, Bony's Agents explains that
  this sends requests to `kurse.bony23.de` (the server and its host see your IP address and the name and version of
  the program; Bony's Agents doesn't store this) – this only happens after you click "Turn on". The privacy policy
  is linked in the consent dialog and in the catalog window. You can turn the source off again at any time with the
  switch.
- **"Export …"** saves a course package as a file to pass on.

## Working through a package

1. Choose a course package → **"Work through"**.
2. Bony's Agents suggests a **separate Agent PC** for the course package (with the programs it needs) – or you
   choose an existing one. A separate Agent PC is better: then practicing can't break anything in your other Agent
   PCs. The new Agent PC is set up in the language of the course package.
3. Next to the Agent PC, the **"Guide"** window opens. It stays on top of all windows at the right edge so you can
   read and work in the Agent PC at the same time ("Always on top" can be turned off).

![The guide next to the Agent PC](bilder/en/kurspaket-anleitung.png){width=45%}

In the "Guide" window:

- At the top ① you jump directly to a lesson; **"Continue"** ⑤ and **"Back"** page through.
- **"Check"** ② looks in the Agent PC whether you've completed the task, for example whether a file exists. You only
  see **"done"** or **"not yet"** with a tip.
- **"Quiz"** ③ asks a few questions about the lesson. The result stays on your computer.
- **"↺ Reset"** ④ resets the Agent PC to the state at the beginning of the lesson. Bony's Agents saves this state by
  itself as soon as you enter a lesson for the first time. Everything you changed in the Agent PC afterwards is lost
  – Bony's Agents asks first.
- **"Show Agent PC"** brings the Agent PC to the front or starts it.
- Under **"⋯"** you'll find the handout, "Delete starting states …" (frees up space) and "Reset progress …".

::: hinweis
Some course packages set something up in the Agent PC at the beginning of a lesson, for example a practice folder,
and check your tasks with small scripts. These scripts run **only in the Agent PC**, never on your computer. For
course packages not checked by Bony's Agents, you see the list of scripts beforehand and decide yourself.
:::

::: datenschutz
In self-study mode everything stays on your computer: progress, check results and quiz. In a course, the trainer
only sees **which lesson** you're in and whether the **check task is done** – never your files and never your quiz
answers.
:::

## Learn with music too

At the bottom left of the main window there's **"Learn with music too:"** with a small player.

- **♪** opens the "Music & Radio" window. Under **"Radio"** you'll find the Hirschmilch channels (Chillout,
  Electronic, Techno …); with **"Add station …"** you add a station of your own (address with `https://`), with
  **"Open playlist …"** you take over stations from an `.m3u` or `.pls` file.
- Under **"My music"** you choose a folder or individual files from your computer (MP3, OGG, FLAC, M4A, WAV),
  shuffled if you like.
- **▶ / ⏸** starts and pauses, **⏭** skips to the next track, the slider sets the volume.

**Nothing plays by itself** – not even after a restart. The music keeps playing while you switch lessons and Agent
PCs.

# Taking part in a course

## Two kinds of courses

| | Course over the internet | Training in your own network |
|---|---|---|
| Where? | everyone at home | everyone in the same room or VPN |
| What do I need? | Bony Network, instance, Agent PC in the Bony Network | just Bony's Agents |
| Code | **course code**, e.g. `K7QX-M3PA` | **share code**, e.g. `4711-BONY` |
| Picture and sound | **course room** with screen, sound, camera, chat | presentation in the browser, without sound |

Your trainer tells you which kind it is. Most sections below apply to courses over the internet. Training in your
own network is at the end of the chapter.

## Preparation

Best do this **a few days before the course**:

1. Install Bony's Agents (chapter "Installation").
2. Turn on the Bony Network and create an instance (chapter "Bony Network").
3. Create an Agent PC with the box **"Connect to the Bony Network"** ticked. Wait until it's fully set up.
4. Set up Hermes (chapter "Setting up Hermes") if your trainer wants you to.

## Joining the course

1. In the main window, click **"Courses"**. The **"Participation"** tab opens.
2. Enter the **course code** ①. Upper and lower case and the hyphen don't matter.
3. Choose the **Agent PC** ② you'll take part with. Only this one Agent PC is reachable for the trainer, and only
   while the course is running.
4. Enter **your name** ③ the way the others should see you.
5. Click **"Join"** ④.

![The "Courses" window, "Participation" tab](bilder/en/kurse-teilnahme.png){width=75%}

The course is then listed under **"My courses"** with the trainer and status (open, running, paused). At the bottom
left ⑤ is the way to training in your own network.

When a course starts, Bony's Agents reports it at the bottom in the status bar ①:

!["The course … has started" in the status bar](bilder/en/kurs-begonnen.png)

::: hinweis
If it says *"The Bony Network is turned off or no instance has been created yet"*, step 2 of the preparation is
missing. The **"Bony Network …"** button in the notice takes you straight there. If there's nothing to choose under
"Agent PC", none of your Agent PCs is in the Bony Network yet.
:::

**"Leave course …"** ends your participation. After that, the trainer can no longer reach your Agent PC through
this course.

## Course with a course package

If the trainer has chosen a course package, it's shown in "My courses" in the **"Course package"** column. Bony's
Agents fetches it into your library by itself. With **"Guide"** you open it next to the Agent PC you're taking part
with – just like when working through a package (chapter "Course packages"). In their course view, the trainer only
sees your **lesson** and whether the **check task is done**, and only while the course is running. The course
package stays in your library after the course.

## The course room

As soon as the course is running: **"Courses"** → choose the course in "My courses" → **"Enter course room"**. The
course room is a window of its own.

![The course room from a participant's point of view](bilder/en/kursraum-teilnehmer.png)

- ① **Stage:** large, the screen the trainer shares (without sharing, their camera). Below it, the cameras that
  are switched on. Whoever is speaking has a green frame.
- ② **Participants:** everyone in the room, with 🎤 (microphone on) or 🔇 (off) and ✋ for a raised hand.
- ③ **Chat:** messages to everyone. The chat isn't stored anywhere and is gone when you close the window.
- ④ **Microphone and camera:** you come in with **microphone and camera off** and switch them on yourself.
- ⑤ **"🆘 Request help":** asks the trainer for help (see below).

With **"✋ Raise hand"** you ask to speak, with "✋ Lower hand" you take your hand down again. **"Leave course
room"** at the bottom right takes you out.

If the trainer has turned on **"Speaking only after permission"**, you can only switch on your microphone once
they allow it. Raise your hand to ask.

::: hinweis
**macOS** asks the first time whether Bony's Agents may use the camera and microphone – please allow it. If you
declined by mistake: System Settings → Privacy & Security → Camera or Microphone → turn on Bony's Agents.
:::

If the connection drops briefly, "Reconnecting …" appears at the top. If the course is paused or has ended, a
message with **"Enter again"** appears:

![The course room was closed](bilder/en/kursraum-getrennt.png){width=80%}

## Help from the trainer

If you're stuck, the trainer can **look at your Agent PC** and show you what to do – but **only if you agree. Every
time anew.**

1. In the course room, click **"🆘 Request help"**. The trainer then sees a 🆘 next to your name. You can take back
   the request with "🆘 Withdraw request".
2. If the trainer clicks **"Help"** for you, this question appears on your screen:

![The question before anyone may see your Agent PC](bilder/en/hilfe-rueckfrage.png){width=65%}

You have three options:

- ① **"Decline"**: the trainer sees nothing. Enter, Esc and closing the window do the same. If you don't answer
  within 60 seconds, the request counts as declined.
- ② **"View only"**: the trainer sees the screen of this one Agent PC but can't type anything.
- ③ **"View and control"**: the trainer can also use the mouse and keyboard in the Agent PC.

As long as the trainer can watch, this notice stays **on top of all windows**:

![Notice "… is viewing your Agent PC" with "End"](bilder/en/hilfe-laeuft.png){width=65%}

**"End"** ① disconnects immediately. Help also ends by itself when

- the trainer ends it,
- the course is paused or ended,
- you leave the course room,
- at the latest after **30 minutes**.

::: datenschutz
**What your consent means:** the trainer sees **only the one Agent PC** you're taking part with – never your own
screen, your other windows or your files. With "View only", their input doesn't arrive at all. With "View and
control", they can do everything in the Agent PC that you can do there – so only agree if you trust them, and don't
leave private data open in this Agent PC. Nothing is recorded. Bony's Agents only notes on your side when someone
watched (without any picture content).
:::

## Training in your own network

For training in the same room (or the same VPN), everything runs directly between the computers – without the
Bony Network and without the internet.

**Loading the template from the trainer:** **"Courses"** → **"Join training on the network …"**. In the same
network, the share appears by itself. Select it, enter the **share code** the trainer shows and click
**"Connect"**.

![Join training on the network](bilder/en/schulung-beitreten.png){width=70%}

Then compare the **fingerprint** with the one on the trainer's screen and tick the box. Click **"Load and
import"**. Your Agent PC is created from the loaded template in a few minutes.

If the trainer also shares a **course package**, it's listed below the template details. It goes into your library
too, and Bony's Agents offers to work through it right away. The trainer then sees your lesson and whether the
check task is done – as long as their share is running.

**Watching a presentation:** the trainer shows you an address like `https://192.168.178.30:47120` and a QR code.
Open the address in the browser (or scan the QR code with your phone), enter your name and the code. The browser
warns about the certificate (Brave: "Your connection is not private", Firefox: "Warning: Potential Security Risk
Ahead") – that's normal here: "Advanced" → "Proceed to …" or "Accept the Risk and Continue". You can only watch.
There's no sound.

![Brave's warning during a presentation; the address here is a different one](bilder/eigene/browser-zertifikat.png){width=70%}

**Requesting help:** in the detail view of your running Agent PC, **"Request help …"** → choose the course (it's
found in the same network), enter the code, optionally a short message → **"Request help"**.

![Requesting help in training in your own network](bilder/en/schulung-hilfe-anfordern.png){width=70%}

If the trainer wants to watch, Bony's Agents asks: **"Allow"** or **"Decline"**. For control there's a second,
separate question. As long as someone is watching, a colored notice with **"View only"** and **"End"** appears at
the top of the main window.

# Privacy in plain words

Bony's Agents has **no telemetry**, **no ads** and **no account**. Errors are only noted on your computer and sent
nowhere.

Only this goes to the internet:

| When? | Where to? | What? |
|---|---|---|
| Update check (only if you agreed) | GitHub | the question about the latest version – with it your IP address and your version |
| Installing an update (only after your consent) | GitHub or the package source | download |
| Setting up a new Agent PC | Debian and the programs' official sources | downloads – the Agent PC fetches them itself |
| Bony Network (only if turned on) | the chosen Bony Network server (central server and network) | your IP address with every request (no access log); stored: instance without name or e-mail, names and network addresses of your Agent PCs, when they were last online and via which public address they connect; for courses the course name and your display name (deleted when the course ends) |
| Course room | the course's course room server | your IP address; picture, sound and chat – only what you turn on. They run encrypted **via the server** (not directly from participant to participant) and aren't recorded there |
| Training in your own network | only the trainer's computer | your computer name or the name you enter; with a course package your lesson and "done / not yet" |
| Course packages from the internet (only on click) | GitHub (repository bonys-agents-kurspakete) | the list of course packages or the download |
| Course with a course package | the Bony Network server | your lesson and whether the check task is done |
| Listening to radio (only if you start a station) | the chosen station | your IP address and the stream – Bony's Agents stores nothing about it |

**What happens in the Agent PC** is up to you: the AI and the browser in the Agent PC send data to the services you
use there (for example to the provider of your AI model).

**Your rights in courses:** without your consent, nobody sees your Agent PC. During the course, the trainer only
reaches the screen share of your Agent PC's help function – and that only runs as long as you agree. The trainer
never reaches your own computer. Other participants never reach your Agent PC. Please don't record the course room;
the technology doesn't prevent recordings by other participants.

**Privacy policy:** for the Bony's Agents server (`zentrale.bony23.de`, course room and course portal) it's at
<https://kurse.bony23.de/datenschutz> (in German). For your own Bony Network server, its operator is responsible.

# Frequently asked questions and problems

## "No hardware virtualization" or everything is very slow

Virtualization is turned off in the **BIOS/UEFI**. Restart the computer, open the BIOS (usually with Del, F2 or F10
at startup) and turn on **Intel VT-x** or **AMD-V/SVM**. No program can do that for you. Without acceleration
(the status bar at the bottom says "Accelerator: tcg") the setup takes hours.

## The setup takes very long or hangs

15 to 60 minutes are normal. If the progress stands still for a long time, click **"Show anyway"** and look at the
console. **"Fetch setup log"** copies the logs into the Agent PC's folder, **"Open logs"** shows it.

## Programs hang or a window doesn't open

Usually the Agent PC's **memory** is too tight – for example when Brave, n8n and Hermes run at the same time. If the
detail view shows **"⚠ recommended: …"** next to the memory, click **"Change performance …"** next to it, then
**"Use recommendation"** and **"Apply and restart"**. Bony's Agents shuts down the Agent PC and restarts it with more
memory. Save open files in the Agent PC first.

If only one program hangs, it often helps to close the program completely and start it again.

## My Agent PC doesn't appear in the Bony Network

1. Is the Bony Network on and an instance created? (ⓘ → "Bony Network …")
2. Is the Agent PC running? When it's off, it's "offline".
3. If the list says "not connected": right-click → **"Connect to the Bony Network"**.
4. If it still doesn't work, the reason is in the log **inside the Agent PC**. Open a terminal there and enter:
   `sudo cat /var/log/bony-netz-beitritt.log`
5. If the **kill switch** of Bony's VPN is on in the Agent PC but no tunnel is connected, the Bony Network can't
   reach the internet either. Connect the tunnel first.

## "The course code is invalid or has expired" / "The course is full"

These messages come from the server (currently in German: „Der Kurscode ist ungültig oder abgelaufen“ / „Der Kurs
ist voll“). Check the code (typo?) and ask your trainer – they can create a new course with a new code.

## The course room won't open

- "The course isn't running right now": the trainer hasn't started yet or has paused.
- On **Linux on ARM** (for example a Raspberry Pi) the course room isn't available yet.
- Camera or microphone don't work: is the device being used by another program right now (Zoom, Teams …)? On
  macOS, check the permission in System Settings.

## The browser warns "Your connection is not private"

That only happens with a presentation in your own network. Every presentation has its own certificate. If you want
to be sure, compare the fingerprint in the certificate details with the one on the trainer's screen.

## Where is my data?

| System | Folder |
|---|---|
| Linux | `~/.local/share/bonys-agents/` |
| macOS | `~/Library/Application Support/bonys-agents/` |
| Windows | `%LOCALAPPDATA%\bonys-agents\` |

Each Agent PC has a subfolder there in `vms/`. If an Agent PC is on an external SSD, Bony's Agents finds it there by
itself as soon as the SSD is plugged in.

## How do I uninstall Bony's Agents?

Like any other program (Windows: Settings → Apps; Linux: package manager; macOS: drag from "Applications" to the
Trash). **Your Agent PCs are kept.** If you want to get rid of them too, delete them in the app first.

## I'd like to run courses myself

For that there's **Bony's Agents Trainer** and the Trainer Guide. In the ⓘ menu, "Want to run training sessions
yourself?" leads to the download.

# Glossary

**Agent PC**
: a separate, isolated computer in a window (virtual machine) in which an AI may work.

**API key**
: a kind of password that lets a program (for example Hermes) use an AI service.

**Bony Network**
: private network over the internet for courses. Off by default.

**Central server**
: the part of the Bony Network server that manages instances, Agent PCs and courses.

**Check task**
: a small check in the Agent PC whether a task is done – the result is only "done" or "not yet".

**Course**
: an event with a trainer – over the internet (course code) or in your own network (share code).

**Course code**
: code with which you join a course over the internet, for example `K7QX-M3PA`.

**Course package**
: the content for learning: lessons with instructions, check tasks, quiz and handout. As a `.bonyspaket` file. Works
  on your own (self-study mode) or in a course.

**Course room**
: the window for picture, sound, camera and chat during a course.

**Fingerprint**
: a check number for an encrypted connection. If it matches the one on the trainer's screen, the connection is
  genuine.

**Instance**
: your registration with a Bony Network server – without name, e-mail or password.

**Kill switch**
: a lock that blocks all internet traffic when no VPN tunnel is connected.

**Lesson**
: a section of a course package with instructions, often with a check task and quiz.

**Model**
: the "brain" of an AI. It runs at a provider on the internet.

**QEMU**
: the free program that runs Agent PCs.

**RDP / SPICE**
: two ways of remote access to an Agent PC.

**Self-study mode**
: working through a course package on your own, without a course and without a trainer.

**Share code**
: short code for training in your own network, for example `4711-BONY`.

**Starting state**
: the saved state of the Agent PC at the beginning of a lesson – "Reset" returns to it.

**Template**
: a fully set-up Agent PC for copying.

**Trainer code**
: code from the server operator that allows someone to create courses.

**.bonys file**
: a template as a single file to pass on.

**.bonyspaket file**
: a course package as a single file to pass on.
