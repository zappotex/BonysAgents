# Bony's Agents

🇩🇪 [Deutsch](README.md) · 🇬🇧 English

![Bony's Agents – learn, work and be creative with AI – but people stay in control](src/bonys_agents/resources/background.jpg)

▶ **Videos and tutorials:** [youtube.com/@BonysAgents](https://www.youtube.com/@BonysAgents)

📖 **Guides (PDF, attached to every release):** User Guide and Trainer Guide – on the
[releases page](https://github.com/zappotex/BonysAgents/releases/latest), source in
[docs/handbuch/en/](docs/handbuch/en/) ([User Guide](docs/handbuch/en/user-guide.md),
[Trainer Guide](docs/handbuch/en/trainer-guide.md)).

**Virtual Agent PCs with a few clicks – with Brave, Telegram and Hermes Agent.**
Runs on Linux, macOS and Windows. Free software under GPL-3.0-or-later.

Bony's Agents creates a separate computer, isolated from your main system (a virtual machine), with **Debian 13
"Trixie"** and a desktop of your choice (Cinnamon, Xfce, KDE Plasma, GNOME, MATE or LXQt). Ready to use inside:

- **Brave Browser** – from the official Brave repository
- **Telegram Desktop** – via Flathub
- **AI tools of your choice**, freely combinable – each with its official installer:
  - **Hermes Agent** – the self-improving AI agent by Nous Research (default), also with voice input and spoken
    answers
  - **OpenClaw** – personal AI assistant with chat integration (Telegram, WhatsApp and others)
  - **Claude Code** – AI coding assistant by Anthropic in the terminal

The AI agent works in an environment of its own: it can install programs, browse the web and create files without
getting at your actual system.

The app is available in **English and German** (it follows your system language; switch under ⓘ → "Sprache /
Language"). Each Agent PC gets its own language too – menus, folders, keyboard and Hermes' voice.

## Features

- Desktop app with overview, start/stop, live console and setup progress
- Complete command line for scripts and servers (`bonys-agents …`)
- Resources sized to the host automatically: all CPU cores, as much RAM as is safely possible, a disk from 32 GB to
  1 TB (default 64 GB, dynamic – only uses what's actually needed), enlargeable later
- Hardware acceleration automatically: KVM (Linux), HVF (macOS), WHPX (Windows), with a software fallback
- Runs on x86_64 and ARM64 (Apple Silicon)
- The image is verified (SHA512); password data is deleted after the setup
- Free choice of location – e.g. an external SSD; Agent PCs are found again on any drive
- Ready-made installers: `.deb` for the package manager, Setup.exe for Windows, `.dmg` for macOS
- Remote access via RDP (xrdp, with sound) and SPICE – off by default, on with one click
- The resolution follows the window; an interrupted setup continues where it stopped
- Updates with one click – for the app itself (signed and verified) and for the Agent PCs
- **Templates:** save a fully set-up Agent PC as a template – new Agent PCs from it are ready in seconds; pass them
  on as a single `.bonys` file (checked for secrets beforehand)
- **Course packages** (`.bonyspaket`): ready-made learning content with lessons, a guide next to the Agent PC, check
  tasks, quiz, starting states to reset and a handout – on your own (self-study mode) or in a course; open library
  [bonys-agents-kurspakete](https://github.com/zappotex/bonys-agents-kurspakete) (the bundled packages are German
  for now)
- **Courses:** over the internet via the **Bony Network** (course room with screen sharing, sound, cameras, chat,
  and "Help" with the participant's consent) or in your own network (share a template, present, help desk) – the
  trainer edition has the tools for running courses
- **[Bony's VPN](https://github.com/zappotex/bonys-vpn)** (a separate project): your own WireGuard tunnels in the
  Agent PC and on your own Linux computer, with kill switch
- Optional: **Obsidian**, **Mission Control** ([separate project](https://github.com/zappotex/bonys-agents-mission-control)),
  **n8n**, **Tor Browser**, **Software Center** (Flathub) and **Kali Linux** as the base system (x86_64, Xfce) for
  security courses

## Installation – no terminal needed

### Which edition do I need?

| You want to … | Edition |
|---|---|
| use your own Agent PCs **or take part in a course** | **Bony's Agents** |
| **run courses** yourself | **Bony's Agents Trainer** (files with "Kursleiter" in their name) |

Participants only need the normal edition. The trainer edition contains everything from the normal one. You can
switch at any time in both directions – just install the other edition; Agent PCs, templates and settings are kept.

Download the file for your system from the **[releases page](https://github.com/zappotex/BonysAgents/releases/latest)**:

| System | File | How |
|---|---|---|
| **Windows 10/11** | `BonysAgents-Setup-<version>.exe` | Double-click → "Next" → "Install". If Windows warns ("Windows protected your PC"): "More info" → "Run anyway". The installer also sets up QEMU and hardware acceleration. Restart once if asked. |
| **Debian, Ubuntu, Linux Mint** | `bonys-agents_<version>_amd64.deb` (ARM: `_arm64.deb`) | Double-click → the package installer opens → "Install". QEMU is installed along with it. Updates then come through your system's Update Manager. |
| **Mac with Apple chip** (M1, M2, M3 …) | `BonysAgents-<version>-macos-applesilicon.dmg` | Open, drag "Bony's Agents" onto "Applications". First start: see below. |
| **Mac with Intel processor** | `BonysAgents-<version>-macos-intel.dmg` | as above |

**macOS:** requires macOS 14 (Sonoma) or later. Bony's Agents isn't notarized by Apple, so macOS asks once on the
very first start: open the app → "Done" → Apple menu → System Settings → Privacy & Security → "Open Anyway" → open
the app again → "Open Anyway". On macOS 14: right-click the app → "Open" → "Open". If macOS says the app "is
damaged": `xattr -cr "/Applications/Bony's Agents.app"` in the Terminal.

**Is the file genuine?** The releases page has `SHA256SUMS` (signed with `SHA256SUMS.minisig`). On Windows,
`Get-FileHash .\BonysAgents-Setup-<version>.exe` in PowerShell shows the checksum – it must be listed there.

On the first start, **"Prepare computer"** sets up whatever is missing (QEMU, access to acceleration) with one
click; on the command line: `bonys-agents setup`. Only if virtualization is turned off in the **BIOS/UEFI** (Intel
VT-x or AMD-V/SVM) do you have to change that yourself.

<details>
<summary>For advanced users: installing from source</summary>

**Linux:** `./install.sh` (asks for your password once) · **Windows:** double-click `install.cmd` ·
**Development:** `pip install -e ".[dev]"`

</details>

## Usage

### Desktop app

Start `bonys-agents` (or `bonys-agents gui`) → **"+ New Agent PC"** → choose name, password, resources, language
and programs → **"Create and start"**.

The first time, the official Debian 13 cloud image (about 450 MB) is downloaded. Then the Agent PC sets itself up
invisibly in the background; you see the progress live in the app. Depending on your computer and internet this
takes 15–60 minutes. Afterwards it turns off briefly and opens in a window with the finished desktop.

### Setting up Hermes

In the Agent PC, open the **Hermes Agent** icon on the desktop and run once:

```bash
hermes setup     # choose a model or API key, optionally connect a Telegram bot
hermes doctor    # check the installation
```

Speaking instead of typing: open **Hermes Agent (Voice)**, press **Ctrl+B**, speak, press **Ctrl+B** again – Hermes
also answers with a voice (recognition locally with Whisper, voice locally with Piper, in the Agent PC's language).

### Command line

```bash
bonys-agents setup                         # set up QEMU & acceleration automatically
bonys-agents selftest                      # check whether QEMU starts on this computer
bonys-agents create my-agent               # create and start (asks for a password)
bonys-agents create my-agent --wait        # … and wait until everything is set up
bonys-agents create my-agent --sprache en  # Agent PC in English (de|en; default: the app's language)
bonys-agents create my-agent --agents hermes,claude-code   # choose AI tools (or: none)
bonys-agents apps                          # all programs and AI tools
bonys-agents install my-agent openclaw mission-control     # install later (Agent PC running)
bonys-agents remote my-agent on            # remote access on until shutdown (off = off, --permanent)
bonys-agents list                          # all Agent PCs
bonys-agents status my-agent               # details, progress, SSH command
bonys-agents stop my-agent                 # shut down cleanly (--force = power off now)
bonys-agents start my-agent                # start again – with a window (--headless = without)
bonys-agents upgrade my-agent              # update the Agent PC (--all = all running ones)
bonys-agents update                        # update Bony's Agents itself (asks first)
bonys-agents delete my-agent               # delete
```

`bonys-agents --help` and `bonys-agents COMMAND --help` show all commands and options. The command line uses the
same language as the app; `BONYS_AGENTS_SPRACHE=en` forces English.

## Privacy

Bony's Agents has **no telemetry** and no account. Only this leaves your computer:

| When | Where to | What |
|---|---|---|
| Update check (once a day, only if you agreed on the first start; can be turned off) | api.github.com | the question about the latest version – like any web request, with your IP address and the installed version |
| Installing an update (only after your consent) | github.com or the package source zappotex.github.io | the package download |
| Setting up a new Agent PC | cloud.debian.org, deb.debian.org and the official sources of the chosen programs | downloads – the Agent PC fetches the programs itself |
| QEMU missing (Windows/macOS) | winget (Microsoft) or Homebrew | installing QEMU |
| Bony Network (only if turned on) | the chosen Bony Network server | instance (no name or e-mail), names and network addresses of your Agent PCs; for courses the course name and display names |
| Training in your own network | only the trainer's computer | your computer name or the name you enter |
| Course packages "From the internet …" (only on click) | raw.githubusercontent.com | the list or the package |

What happens inside the Agent PCs (browser, AI agents, Telegram …) is up to you. App errors are only logged locally
(`fehler.log` in the data folder) and sent nowhere.

## Where is the data?

| System | Folder |
|---|---|
| Linux | `~/.local/share/bonys-agents/` |
| macOS | `~/Library/Application Support/bonys-agents/` |
| Windows | `%LOCALAPPDATA%\bonys-agents\` |

## More documentation

The German [README](README.md) goes into more detail (desktops, screen, templates, training, remote access, VPN,
Mission Control, updates, code structure). Developer documentation in `docs/` is in German.

## Contributing

Contributions are welcome – see [CONTRIBUTING.md](CONTRIBUTING.md). They are only accepted with agreement to the
[Contributor License Agreement (CLA)](CLA.md).

## License

Copyright © 2026 Bony

**Program code:** Bony's Agents is free software under the **GNU General Public License, version 3 or (at your
option) any later version** (GPL-3.0-or-later) – see [LICENSE](LICENSE). You may use, study, modify and share the
program; modified versions must also be under the GPL and disclose their source code. Bony's Agents is provided
without any warranty.

**Commercial license:** if you want to build Bony's Agents into a closed product without meeting the terms of the
GPL, a commercial license is available on request – contact via
[youtube.com/@BonysAgents](https://www.youtube.com/@BonysAgents).

**Name and logo:** "Bony's Agents" and the logo are excluded from the license. They must not be used for modified
versions – anyone who passes on a modified program must use a different name and logo.

**Other software:** the ready-made packages contain Python, Qt/PySide6 and some other libraries under their own
licenses – see [THIRD-PARTY-LICENSES](THIRD-PARTY-LICENSES). QEMU, Debian, the desktops, Brave, Telegram, Hermes
Agent and the other AI tools are **not** included; they are downloaded at runtime from their official sources and
are under their own licenses.
