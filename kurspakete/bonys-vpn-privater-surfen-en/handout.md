---
title: Bony's VPN – safer and more private online
subtitle: Handout for participants
lang: en
---

## Your course

::: {.feld hoehe="1.3cm" text="Course code (you get it from the trainer)"}
:::

::: {.feld hoehe="1.3cm" text="Date and time"}
:::

## A – Before the course

1. **Bony's Agents version 0.23.0 or later** – update older versions (ⓘ → "Check for updates" or the Update Manager on
   Linux).
2. An **Agent PC with Bony's VPN**: the **"Bony's VPN"** icon is on the desktop – if it's missing: start the Agent PC,
   in the detail view next to "Programs" → **"Add programs …"** → "WireGuard VPN (Bony's VPN)".
3. A **free account at Proton VPN** (account.protonvpn.com, plan "Free", confirm the e-mail) – or access to your
   **FRITZ!Box**.
4. Join the course: **"Courses"** → course code → choose the Agent PC → **"Join"**.

## B – The essentials in brief

| Term | Meaning |
|---|---|
| **VPN** | an encrypted tunnel from your computer to a VPN server |
| **WireGuard** | the technology behind it – modern, fast, in the Linux kernel |
| **`.conf`** | file from the provider with the server and your **private key** |
| **Kill switch** | no tunnel, no internet – also after a restart |
| **DNS** | the question "what address does this site have?" – should go through the tunnel |

- The `.conf` is a **password**: don't show it, don't send it, delete it from Downloads after importing.
- With a VPN the website sees the VPN server's address – in return the **VPN provider** knows your destination.
- **More private, not anonymous:** sign-ins, cookies and the browser's fingerprint still give you away.

## C – Getting the configuration (Proton VPN)

1. account.protonvpn.com → **Downloads** → **WireGuard configuration**
2. Name (e.g. `agent-pc`), platform **GNU/Linux**, choose a **free server** → **"Create"**
3. **"Download"** – in the Agent PC's Brave, then it's in **Downloads**

Or **FRITZ!Box:** Internet → Permit Access → VPN (WireGuard) → "Add Connection" → "Connect a single device" → download
the file.

## D – In Bony's VPN

1. **"Import …"** → Downloads → file → **"Open"**
2. **"Connect"** – "connected", handshake, amount of data
3. **"Public IP" → "Check"** (or ipinfo.io in Brave)
4. Turn on **"Connect automatically"** and **"Kill switch"**
5. Test: "Disconnect" → site can't be reached → "Connect"
6. **Delete** the `.conf` from Downloads, empty the trash

## E – Test pages

| What | Page | Good is … |
|---|---|---|
| Address | `https://ipinfo.io` | location and provider of the VPN server |
| DNS | `https://www.dnsleaktest.com` | only the VPN provider's servers |
| Trackers | `https://coveryourtracks.eff.org` | trackers blocked (the fingerprint usually remains) |

## F – Browsing more privately

- **Private window with Tor** in Brave: Alt + Shift + N
- **A separate Agent PC** for everything where you sign in
- **A throwaway PC** from a template for unknown things – delete it afterwards
- **Tor Browser** as an app in Bony's Agents (Intel/AMD computers)

## Where I want to use the VPN

::: {.feld hoehe="2.2cm" text="e.g. café Wi-Fi, hotel, into the home network from on the go"}
:::

## How to continue

- **Right when creating:** "New Agent PC" window → **VPN** section → choose the `.conf`.
- **From outside:** Bony's Agents → running Agent PC → **"VPN"** tab.
- **Your own Linux computer:** the **"VPN"** button in the main window; Windows/Mac: the official WireGuard app.
- **Video** "Bony's VPN" and more: youtube.com/@BonysAgents
- Source code and docs: github.com/zappotex/bonys-vpn
