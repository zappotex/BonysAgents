---
title: Trainer Guide
subtitle: Preparing, running and wrapping up courses with Bony's Agents
lang: en
---

<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
<!-- English trainer guide, translated from ../kursleiter.md (keep both in step). PDF: docs/handbuch/erstellen.sh.
     Images with "kl-" show the trainer edition; bilder/en/ has the English interface. -->

# Introduction

## What the trainer edition can do in addition

**Bony's Agents Trainer** contains everything from the normal edition plus the tools to run courses yourself.
Your participants only need the normal edition.

| Feature | Bony's Agents | Trainer |
|---|:---:|:---:|
| Agent PCs, templates, remote access, VPN, Mission Control | ✓ | ✓ |
| Take part in courses, course room, request help | ✓ | ✓ |
| Redeem a trainer code, create, start, pause and end courses | – | ✓ |
| In the course room: share screen, mute, allow speaking, remove from the room | – | ✓ |
| "Help": view and control a participant's Agent PC (after consent) | – | ✓ |
| Training in your own network: share a template, present, accept help requests | – | ✓ |
| Work through course packages (self-study mode), work with the guide in a course | ✓ | ✓ |
| Choose a course package for a course, see participants' progress, notes and schedule | – | ✓ |
| Course package editor: create, check and print your own course packages as PDF | – | ✓ |

This guide assumes you know the normal features (User Guide: creating an Agent PC, setting up Hermes, turning on the
Bony Network).

## Two kinds of courses

| | **Course over the internet** (Bony Network) | **Training in your own network** |
|---|---|---|
| Where are people? | everyone in their own place | in the same room (Wi-Fi) or the same VPN |
| Server | a Bony Network server (central server and course room) | none – everything directly between the computers |
| What do you need? | a trainer code from the server operator | just the trainer edition |
| Picture and sound | course room: screen, sound, cameras, chat, hand signals | presentation in the browser, without sound |
| Help | "Help" in the course room | help desk |
| Distributing a template | as a `.bonys` file (USB stick, cloud) | directly with "Share on the network" |

**Rule of thumb:** courses over the internet take a lot of technology off your hands and also work when everyone is
at home. Training in your own network is the way to go when there's no reliable internet on site.

# Setting up

## Installing the trainer edition

On the releases page, download the file with **"Kursleiter"** (trainer) in its name:

| System | File |
|---|---|
| Windows | `BonysAgents-Kursleiter-Setup-<version>.exe` |
| Debian, Ubuntu, Linux Mint | `bonys-agents-kursleiter_<version>_amd64.deb` |
| macOS | `BonysAgents-Kursleiter-<version>-macos-applesilicon.dmg` or `-intel.dmg` |

Installation works just like the normal edition (User Guide, chapter "Installation"). If you already have the
normal edition, simply install the trainer edition over it: it replaces the normal one. Agent PCs, templates and
settings are kept. It works the same the other way round.

The main window then says **"Trainer"** below the name. New is the **"Present …"** button ① for the Agent PC. You
run courses via **"Courses"** ②, and distribute templates via **"Templates"** ③:

![Main window of the trainer edition](bilder/en/kl-hauptfenster.png)

## Bony Network and instance

For courses over the internet you need, like your participants: menu ⓘ → **"Bony Network …"** → "Use the Bony
Network", check the server, **"Create instance"** (User Guide, chapter "Bony Network").

Also create an **Agent PC in the Bony Network** to present with – for example `agent-kursleitung`.

## Bringing your computer into the Bony Network

For **"Help"**, **your own computer** must be in the Bony Network, not just your Agent PC – otherwise the viewer
window can't reach the participants' Agent PCs.

- **Linux:** with **Bony's VPN**. In Bony's VPN, under "Bony Network", turn on **"Connect this computer"**. You open
  Bony's VPN with the **"VPN"** button at the top of the main window (if it isn't installed, Bony's Agents offers to
  install it).
- **Windows and macOS:** with the official **Tailscale app**, signed in to the login server of your Bony Network.

When you **"Start course"**, Bony's Agents checks this and tells you if your computer isn't in the network:

![Notice when starting a course: this computer is not in the Bony Network](bilder/en/kl-netz-pruefung.png){width=55%}

## Redeeming a trainer code

An instance may only create courses with a **trainer code**. You get it from the operator of your Bony Network
server. Redeeming it once is enough – also for Bony's VPN.

1. In the main window, click **"Courses"**. The **"Trainer"** tab is open.
2. Enter the code in the **"Trainer code"** field ①.
3. Click **"Redeem"** ②.

![The "Trainer" tab before redeeming](bilder/en/kl-code-einloesen.png){width=75%}

Afterwards you see the course list.

# Preparing a course

## Preparing the course Agent PC

Think about what your participants should work with. Two ways:

- **Everyone sets up their own Agent PC** (the normal way, see the handout of the sample course). That takes 15–60
  minutes for each person and has to happen **before** the course.
- **You distribute a template:** set up an Agent PC the way it should be in the course, save it as a template (with
  "Remove personal data") and pass it on as a file with **"Templates" → "Pass on (.bonys) …"**. The participants
  import it and have the same Agent PC within minutes. Agent PCs from a template keep its language – for an
  English course, set up the template in English.

::: warnung
A template you pass on must contain **nothing personal**: no sign-ins, no API keys. Bony's Agents checks this in a
copy when passing it on and stops if it finds anything. Programs that may not be passed on freely (Claude Code,
Obsidian) are taken out – participants then install them from the official source.
:::

## Creating a course

1. **"Courses"** → **"Trainer"** tab → **"+ New course …"**.
2. **Course name** ①: for example "Introduction to Hermes Agent".
3. **Your display name** ②: how participants see you.
4. **Code valid for** ③: 1 to 60 days (default 14). Participants can join with the code for that long.
5. **Course package** (optional): for example "Introduction to Hermes Agent" – participants get it automatically
   (chapter "Course packages"). If the course name is still empty, Bony's Agents suggests the name of the course
   package.
6. **"Create course"** ④.

![New course](bilder/en/kl-neuer-kurs.png){width=60%}

The course is now **open**: participants can join, but you can't reach their Agent PCs yet. The course only begins
with "Start course".

The course list shows all your courses with status, number of participants and code. **"+ New course …"** ①,
**"Open"** ② opens the course view, **"Show ended"** ③ also shows old courses:

![The course list in the "Trainer" tab](bilder/en/kl-kursliste.png){width=75%}

## Distributing the code

Open the course. At the top, the **course code** ① is shown in large, with **"Copy"** next to it. Below you see
until when it's valid.

![The course view of a running course](bilder/en/kl-kursansicht.png){width=80%}

Send your participants the code in good time before the course, together with the handout (see the sample course).
A template for the invitation:

> **Subject:** Invitation: Introduction to Hermes Agent on Saturday, 8 November, 10 am – 12 pm
>
> Hello,
>
> great that you're joining the course "Introduction to Hermes Agent". We'll meet online in the course room of
> Bony's Agents.
>
> **Please do this at least two days before** (takes about 1 hour, mostly waiting):
>
> 1. Install Bony's Agents: github.com/zappotex/BonysAgents/releases/latest
> 2. In the menu ⓘ → "Bony Network …", turn on the Bony Network and click "Create instance".
> 3. Create a "+ New Agent PC" with the box "Connect to the Bony Network" ticked and wait until it's ready.
> 4. "Courses" → enter the course code: **K7QX-M3PA** → choose your Agent PC → "Join".
>
> On the day of the course: open Bony's Agents, start your Agent PC, "Courses" → "Enter course room". A headset is
> good, a camera is optional.
>
> Attached you'll find a handout with all the steps. If something doesn't work, just reply to this e-mail.
>
> Best regards
> Eva

## How many participants?

How many participants a course may have and how many active courses you can have at the same time is set by the
**server**, not the app. If a limit is reached, Bony's Agents shows the server's message unchanged, for example
"Der Kurs ist voll" (the course is full). Ask your server operator which limits apply.

For a course with screen sharing and cameras, **5–10 participants** are easy to look after. With more people,
better turn cameras off and "Speaking only after permission" on.

## Technical check beforehand

Do a **trial run** one or two days before the course – ideally with a second computer or a volunteer:

1. Start the course, open the course room, try the microphone and screen sharing.
2. Join with the second computer: can you see your screen? Can you hear yourself?
3. Try "Help": does the question arrive? Do you see the Agent PC?
4. **Pause** the course again (or end a separate trial course afterwards).

Check in the course view whether every registered participant has a **network address**. If it's missing, the
participant's Agent PC isn't in the Bony Network.

# On site or over the internet

## Everyone is in the same room

Even when everyone is in the same room, you can run a course over the internet. Then:

- **Many computers on the same internet connection:** to the server, all participants look the same (the same
  public IP address). Servers often limit how many **instances per day** may be created from one address. Ask your
  **server operator** to raise the "instances per day" limit for your course day – or have participants create
  their instance at home beforehand. Bony's Agents itself has no such setting.
- **Wi-Fi:** every Agent PC downloads several hundred megabytes during setup. Ten Agent PCs at the same time on the
  same Wi-Fi take a long time. Have the Agent PCs set up beforehand or distribute a template.
- **Sound:** in the same room you don't need the course room's sound. Keep all microphones off, otherwise there will
  be feedback. You can still share your screen – or simply show it on a projector.
- **No internet on site?** Then use **training in your own network** (section 5.6).

## Everyone is at home

- Ask for a **headset** – it prevents echo.
- Allow **10 minutes for technology** at the start. Start the course 15 minutes early.
- Agree on a **plan B**, for example a Jitsi room (meet.jit.si) for sound and picture in case the course room
  fails.
- Ask participants to start their Agent PC **before** the course. It must be running for "Help".

# During the course

## Starting, pausing, ending the course

In the course view:

| Button | Effect |
|---|---|
| **Start course** | The course is running: course room open, you reach the participants' chosen Agent PCs via the Bony Network. |
| **Pause** ② | Access to the Agent PCs is gone immediately, nobody new can enter the course room. "Start course" resumes. |
| **End …** | Closes the course for good – after a confirmation. Cannot be undone. |
| **Open course room** ③ | opens the "Course room" window (only while the course is running) |

At the bottom of the course view is the **participant table** ④ with display name, Agent PC, network address and
time of joining – with a course package also lesson and check (chapter "Course packages"). **"Help"** ⑤ opens the
course room and asks the selected participant. **"Remove …"** takes a participant out of the course completely.

Participants never reach each other. And you only reach the one Agent PC a participant chose when joining – never
their own computer.

## The course room

![The course room from the trainer's point of view](bilder/en/kursraum-kursleiter.png)

You come in **with the microphone on** (participants with everything off). In the bar at the bottom:

- **Microphone** and **camera** on and off.
- **✋ Raise hand** – also for you, in case you're in a course with two trainers.
- **"Share screen"** ①: choose a whole screen or a single window. With "Stop sharing" you stop.

  ![Choose a screen or window](bilder/en/kursraum-bildschirm-waehlen.png){width=50%}

- **"Speaking only after permission"** ②: if ticked, participants can only switch on their microphone when you allow
  them to. Microphones that are on are switched off.

::: tipp
Better share a **single window** (for example your Agent PC's window) than the whole screen. That way nobody
accidentally sees your e-mails or notifications.
:::

## Managing participants

In the participant list on the right ③, every participant has small buttons:

| Button | Effect |
|---|---|
| **Help** | asks the participant whether you may see their Agent PC (see below) |
| **Allow speaking** / **Revoke permission** | only with "Speaking only after permission" |
| **Mute** | switches off their microphone (they can switch it on again themselves, except with "only after permission") |
| **Remove …** | takes them out of the **course room**. They stay in the course and can enter again. To remove them from the course entirely: course view → "Remove …" |

**✋** next to a name means: the participant wants to speak. **🆘** means: they're asking for help. The course room
also briefly shows a notice ④ for both.

## Chat

The chat is for everyone in the room. It's **not stored** – anyone who comes later doesn't see earlier messages,
and it's gone with the window. So better also send important links by e-mail.

## Help

With **"Help"** you see a participant's Agent PC in a window of its own – and can operate it if they allow it.

1. In the course room, click **"Help"** for the participant (or in the course view: select the participant →
   "Help"). The button shows "Asking …".
2. The participant gets the question: **"View only"**, **"View and control"** or **"Decline"**. Without an answer
   it's declined after 60 seconds.
3. If they agree, the window **"Help – name (View only)"** or "(View and control)" opens on your side with their
   Agent PC. At the top there are buttons to fit the picture to the window, to send **Ctrl+Alt+Del** and to end.
4. The button in the course room shows "Helping". If the participant declines, a notice appears.

![The course room for the trainer – as soon as participants are there, each has the "Help" button](bilder/eigene/kl-hilfe-fenster.png)

Help ends when you or the participant press "End", the course is paused or ended, one of you leaves the course
room, the participant's app stops responding (for example after a crash), or after 30 minutes at the latest. Only
your computer can connect – not your own Agent PCs.

::: datenschutz
Ask **anew every time** – and say out loud beforehand what you want to do ("I'll take a quick look at your
terminal"). Only choose "View and control" when it's really necessary. You only see the Agent PC the participant is
taking part with – nothing of their own computer. Nothing is recorded: picture, sound and chat run via the course
room server, which only forwards them. Ask participants not to record the course room.
:::

## Training in your own network

Without the Bony Network, in the same Wi-Fi or VPN. All participants find your offers under **"Courses" → "Join
training on the network …"**.

**Sharing a template:** **"Templates"** → choose a template → **"Share on the network …"** → "Start share". The
template is checked and packed once for this. The window then shows the **share code** ①, the **QR code** ②
(contains address, code and fingerprint) and the **participants** ③ with their progress:

![Sharing a template on the network](bilder/en/kl-freigeben.png){width=80%}

At most 4 participants download at the same time (adjustable), the others wait in a queue. The share ends by itself
after 120 minutes or with "End share". With a **course package** (field "Course package"), participants get it
along with the template; the table then shows their lesson and check.

**Presenting:** start the Agent PC → **"Present …"** → choose quality, number of viewers and duration → "Start
presentation". Participants open the address shown in the browser (or scan the QR code) and see your Agent PC –
**view only**, without sound.

![A presentation is running](bilder/en/kl-vorfuehren.png){width=80%}

- **Code** ① and **QR code** ② to pass on.
- **"Pause"** ③: everyone immediately only sees a "back in a moment" screen. Press pause **before** you enter
  passwords or API keys.
- **"Remove viewer"** ④: disconnects the selected viewer (their address is blocked for 5 minutes).

**Help requests:** menu ⓘ → **"Trainer: help requests …"** → "Start help desk" (if a presentation is already
running, the same code applies). New requests appear in the list ① with a sound. **"View"** ② asks the participant
and, after their consent, opens their Agent PC in the browser. **"Request control"** ③ asks for a second consent for
mouse and keyboard.

![Help requests in training in your own network](bilder/en/kl-hilfe-anfragen.png){width=80%}

::: hinweis
The pages participants see in the browser during a presentation, and the help view in your browser, are still in
German for now.
:::

::: hinweis
**Firewall:** Bony's Agents doesn't open anything permanently. Windows asks the first time you share – "Allow
access", only for **private networks**. On Linux there's usually no firewall active; the windows show the matching
commands for ufw and firewalld. In a VPN the automatic search doesn't work: participants then enter the VPN address
from the window or paste the link from the QR code.
:::

# Course packages

A **course package** is the *content* of a course: lessons with instructions for the participants, check tasks,
quiz, your **schedule** with times and solutions and a **handout**. The **course** is the *event* (course code,
participants, course room). A course doesn't need a course package – but with one it becomes much easier: every
participant has the steps next to their Agent PC, and you see who is where.

## Bundled course packages

| Level | Course package | Status |
|---|---|---|
| Beginner | **Introduction to Hermes Agent** – 2 hours, 9 lessons (the ninth is a bonus) | finished |
| Beginner | **What is an MCP server? Hermes gets tools** – 90 minutes | finished |
| Beginner | **n8n basics: the first workflow** – 90 minutes | finished |
| Beginner | **Bony's VPN: safer and more private online** – 90 minutes | finished |
| Beginner | Controlling Hermes via Telegram | draft |
| Advanced | Automating tasks: research, summaries, files | draft |
| Advanced | Security for AI agents: limiting permissions, recognizing prompt injection | draft |
| Expert | Your own tools and skills for Hermes, Mission Control with Docker | draft |
| Expert | Local models, VPN and several agents | draft |

Every bundled course package comes in German and English (ID with "-en"); the library shows the version in the
language of Bony's Agents, "All languages" shows both. A **draft** contains an outline,
learning goals and a timetable, but no worked-out instructions yet. With the editor ("Duplicate …" or "Edit …" → your
own version) you turn it into your own course package. The schedule of "Introduction to Hermes Agent" is also the
sample course for this guide (a separate PDF on each release).

## Choosing a course package for a course

When creating the course (**"+ New course …"**) or later in the course view under **"Course package"** →
**"Choose …"**. Bony's Agents packs the course package, checks it for credentials and uploads it to the Bony Network
server (at most 25 MB). Participants get it in their library automatically and open it with **"Guide"** next to
their Agent PC.

In the course view, the course package ① is shown with **"Guide"** ② and **"Change …"** ③, and the participant
table ④ gets two columns: **"Lesson"** (for example "3. Hermes ready to go") and **"Check"** ("✓ done", "✗ not
yet" or "–" without a check task):

![Course view with a course package: lesson and check per participant](bilder/en/kl-kurspaket-kursansicht.png){width=85%}

You don't see more than that – no files, no quiz answers – and only while the course is running. When the course
**ends**, the server deletes the course package and the progress. **"Guide"** opens the course package on your side,
with the schedule (menu "⋯") and the **notes for the trainer** for each lesson – only trainers see those.

::: tipp
If you choose a different course package, it replaces the previous one; participants' progress then starts anew.
Small corrections to the same course package (same ID) keep the progress.
:::

**Training in your own network:** the "Share on the network" window has the same **"Course package"** field.
Participants get it with the template; the table shows their lesson and check as long as the share is running.

## Creating your own course package

**"Courses"** → **"Course packages"** → **"New …"** (or **"Edit …"** / **"Duplicate …"** an existing one). The editor
shows the outline on the left and the selected part on the right:

![The course package editor](bilder/en/kl-kurspaket-editor.png){width=90%}

- **Profile:** name, description, level, duration, number of participants, target group, prerequisites, learning
  goals, sources – and the **language** of the course package.
- **Recipe:** what the participants' Agent PC should look like (desktop, programs, size) – **"Take over from an
  Agent PC …"** reads that from one of your Agent PCs. A course package never contains a disk image. The Agent PC is
  set up in the language of the course package.
- **Schedule** and **Handout:** Markdown with preview, boxes (tip, note, caution, privacy) and fields to fill in.
  **"PDF ▾"** builds the print version from it.
- **Lessons** (**"+ Lesson"**, ↑ ↓): tabs **Guide** (with **"Insert image …"** and **"Screenshot of the Agent
  PC"**), **Trainer** (your notes), **Check**, **Starting state** and **Quiz**.
- **Check:** built in ("Agent PC running", "template present") or a small script. **"Insert template ▾"** offers
  "File exists …", "Service running …" and "Hermes set up". A check script outputs nothing and never reads keys –
  "Hermes set up" only looks for the provider and model in `~/.hermes/config.yaml`.
- **Starting state:** an optional script that runs in the Agent PC at the beginning of the lesson (e.g. creating
  practice files). **"Take over from a folder in the Agent PC …"** turns a folder like `~/Kurs` into such a script.

**"Save"** checks everything first. If Bony's Agents finds **keys, tokens, passwords, e-mail addresses, phone
numbers or IBANs**, it doesn't save and shows the file and line (never the value). **"Increase version ▾"** counts
the version up – do that before passing it on.

## Checking a course package

**"Check course package …"** in the editor reports what doesn't fit: missing images, links without https, outdated
programs in the recipe, errors in scripts. Optionally it checks the links on the internet and plays through the
lessons in a **test Agent PC**: starting state, check before (must not be done yet), solution script, check after.
That way you notice when a course package no longer fits after a Hermes update. Afterwards Bony's Agents resets the
test Agent PC.

## Passing on and publishing

- **"Export …"** in the library saves a `.bonyspaket` file, for example for the invitation.
- A course package gets into the open library (**"From the internet …"**, repository
  `zappotex/bonys-agents-kurspakete` on GitHub) via a pull request. Course packages there are under **CC BY-SA 4.0**.
- Course packages that aren't bundled or signed with the Bony's Agents key show participants the list of their
  scripts before the first start. That's intended: the scripts only run in the Agent PC, but everyone should know
  what happens there.

## Checking and approving community course packages

The trainer edition has the entry **"Course portal: moderation …"** at the bottom of the **ⓘ** menu. There you
decide about submitted course packages. Packages are only data: Bony's Agents doesn't run anything from them.

1. At the top, choose **"Online (course portal)"** and enter the **moderator token** the first time. It's only
   stored if the connection works, and is kept in a file of its own on your computer. The operator of the course
   portal creates the token on the server; without a token there's nothing to do here. "Local (this computer)" is
   for submissions you check yourself as a file.
2. Choose a submission. You see the automatic check report (scripts, links, places where secrets were found –
   without the values) and the history. **"View contents …"** shows texts and scripts as plain text; images aren't
   opened.
3. **Approve**, **Decline**, **Publish** or **Withdraw** – every decision needs a reason and is recorded with your
   name in the history. Published means: the package appears in the community catalog of all users. Packages whose
   ID belongs to a bundled course package are never published.

The dialog only exists in the trainer edition. Users see published packages under **Courses → Course packages →
"From the internet …"**.

# After the course

## Ending the course

Course view → **"End …"** → confirm. Then the following applies immediately:

- You **can't reach any** participant's Agent PC any more.
- The **course room is closed.** Anyone still inside sees "The course room was closed – the course has ended or is
  paused." Entering again is no longer possible.
- Any **help in progress ends.**
- The **course code** is no longer valid.
- The **course package** and the participants' progress are deleted on the server. Participants keep their copy in
  the library.

This cannot be undone. For a follow-up date, create a new course. With **"Show ended"** in the course list you can
still see old courses.

The **participants' Agent PCs stay** with them – with everything they did in the course. They can keep practicing
with them at home. Their instance in the Bony Network stays too; only the connection to your course is gone.

## Cleaning up

- Training in your own network: share, presentation and help desk end with their window or by themselves after the
  set time.
- If you opened ports in the firewall for the training, close them again.
- If you entered API keys in your presentation Agent PC that you don't want to keep: delete them there (`hermes
  setup` or `~/.hermes/.env`) or recreate the Agent PC from the template.

# Known limitations

- **Screen sharing on Linux only works in an X11 session** (for example Cinnamon or "GNOME on Xorg"), not on
  **Wayland**. The button then explains this. Camera, sound and chat still work. Remedy: choose the X11 session when
  logging in.
- **Linux on ARM** (for example a Raspberry Pi): the course room – and thus also "Help" – isn't available there yet.
  Use another computer to run the course (Linux on x86, Windows or macOS).
- **macOS:** allow camera, microphone and **screen recording** the first time (System Settings → Privacy &
  Security).
- **Pausing:** whether the server also closes the course room when pausing depends on the server. It refuses new
  entries in any case.
- **Presentation in your own network:** no sound. Use the room or Jitsi in addition.
- **Kill switch** of Bony's VPN in a participant's Agent PC: without a connected tunnel, the Bony Network can't get
  through either.
- **Course packages in a course:** at most 25 MB (packed). You only see the progress while the course or the share
  in your own network is running. Participants only report it while their guide is open.
- **Messages from the server** (for example "the course is full") currently arrive in German.
- **Not much tested yet** (as of this version): the course room and "Help" have so far only been tested thoroughly
  on Linux, not on Windows and macOS. Be sure to do a trial run there beforehand.

# Checklist to print

**Course:** ______________________________ **Date:** ______________ **Course code:** ______________

## Before the course (1–2 weeks before)

- [ ] Trainer edition installed, Bony Network on, trainer code redeemed
- [ ] Your own computer in the Bony Network (Bony's VPN or Tailscale) – for "Help"
- [ ] Presentation Agent PC set up, Hermes runs, no private data in it
- [ ] Course created, code valid until after the course day
- [ ] Course package chosen and tested with "Check course package …" (or deliberately without)
- [ ] Invitation with code and handout sent
- [ ] Many participants on the same connection: asked the server operator about "instances per day"
- [ ] Plan B agreed (e.g. a Jitsi link) and mentioned in the invitation

## Before the course (1–2 days before)

- [ ] Trial run: course room, sound, screen sharing, "Help"
- [ ] In the course view: all participants joined, all with a network address
- [ ] Anyone missing or without a network address has been contacted

## Start of the course (15 minutes before)

- [ ] Computer plugged in, notifications off, private windows closed
- [ ] Presentation Agent PC started
- [ ] **"Start course"** pressed, Bony Network notice checked
- [ ] **"Open course room"**, microphone on, sound checked
- [ ] Screen (better: a window) shared
- [ ] With many participants: "Speaking only after permission"

## End of the course

- [ ] Questions answered, tips for further practice given
- [ ] Help sessions in progress ended
- [ ] **"End …"** in the course view (or "Pause" if it continues)
- [ ] Course room closed
- [ ] Presentation Agent PC: entered keys removed
- [ ] Share, presentation, help desk ended; opened firewall ports closed again
