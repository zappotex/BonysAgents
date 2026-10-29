---
title: Course "Bony's VPN: safer and more private online"
subtitle: Schedule for the trainer – 90 minutes, 3–10 participants without prior knowledge
lang: en
---

# Profile

| | |
|---|---|
| **Title** | Bony's VPN: safer and more private online |
| **Duration** | 90 minutes without a break |
| **Group** | 3–10 people, no prior knowledge needed |
| **Format** | Course over the internet with the course room of Bony's Agents (works just the same on site) |
| **Participants need** | Bony's Agents 0.23.0 or later, an Agent PC with Bony's VPN and Brave, an e-mail address for Proton VPN (or access to their own FRITZ!Box), a headset |
| **You need** | Bony's Agents Trainer, a presentation Agent PC with Bony's VPN, your own free Proton account |
| **Cost** | none |
| **Material** | Course package "Bony's VPN" (schedule, handout, lessons with quiz and check tasks), video "Bony's VPN" at youtube.com/@BonysAgents |

By the end, everyone has a connected WireGuard tunnel in their Agent PC with a kill switch and automatic connection,
has tried test pages for DNS and trackers and has deleted the `.conf` from Downloads. Stay honest: **more private,
not anonymous.**

# Learning goals

By the end of the course, participants can …

1. explain what a **VPN** is and who sees what with and without a VPN;
2. name **benefits and limits** – a VPN makes you more private, not anonymous;
3. get a **WireGuard configuration** (`.conf`) from the provider and treat it like a password;
4. import it into **Bony's VPN**, **connect** and **check** the public address;
5. turn on and test the **kill switch** and **connecting automatically**;
6. browse more privately with **test pages**, a **private window with Tor** and a **throwaway PC**.

# Principles for you

- **Never show your own `.conf`** and never the tunnel card (address, DNS, endpoint) longer than necessary.
  Participants get their own configuration – never one from the trainer.
- **Kill switch on before you disconnect.** Otherwise Brave shows your connection's real address while screen sharing.
- Only share the **presentation Agent PC's** window – not your own computer, where your own tunnels may be running.
- Proton VPN is an **example**, not an ad. Anyone with another WireGuard provider uses that.

# Preparation

## One week before

- [ ] Create the course, choose "Bony's VPN" under **"Course package"**.
- [ ] Send the invitation with the course code and the **handout**. Important: an Agent PC **with Bony's VPN** (tick
  "WireGuard VPN (Bony's VPN)" under "Programs" when creating it), ideally create the Proton account **beforehand**
  (confirm the e-mail).
- [ ] Work through the course once yourself (self-study mode).

## One or two days before

- [ ] Create a Proton configuration in the presentation Agent PC and import it – test whether the free server
  answers. Then delete the `.conf` from Downloads.
- [ ] In the course view: has everyone joined? Is everyone's Agent PC running?

## 30 minutes before

- [ ] Start the presentation Agent PC, open Bony's VPN. Tunnel **disconnected**, kill switch **off** – you demo both.
- [ ] Brave with an empty tab, zoom to 125 %.
- [ ] **"Start course"**, **"Open course room"**, share the Agent PC's window.

# Timetable

| Minute | Duration | Block | Content |
|---:|---:|---|---|
| 0 | 5 | 1 Getting started | Welcome, flow, "Where are you on someone else's Wi-Fi?" |
| 5 | 15 | 2 What is a VPN? | without/with a VPN, benefits and limits; quiz |
| 20 | 15 | 3 Getting the configuration | Proton Free (or FRITZ!Box), `.conf` in Downloads (check) |
| 35 | 15 | 4 Importing and connecting | Import → Connect → Public IP, ipinfo.io (check) |
| 50 | 15 | 5 Kill switch | connect automatically, kill switch, disconnect test (check) |
| 65 | 15 | 6 Browsing more privately | dnsleaktest, EFF test, private window with Tor, throwaway PC; quiz |
| 80 | 10 | 7 Cleaning up and wrap-up | delete the `.conf` (check), security, outlook, quiz |

Blocks 1–7 correspond to lessons 1–7 in the course package. If time gets short, shorten block 6 – not blocks 4 and 5.

# Step by step

## Block 1 – Getting started (0–5)

**You show:** the course room, the shared Agent PC, the "Bony's VPN" icon. The flow. **Opening:** "Where are you with
your laptop on someone else's Wi-Fi – café, hotel, train?"

## Block 2 – What is a VPN? (5–20)

**You tell:** without a VPN everything goes via the internet provider or café Wi-Fi, the website sees your address.
With a VPN, an encrypted tunnel to the VPN server, the website sees its address. Then the table "does – doesn't", with
the focus on **not anonymous**. If you like: the video "Bony's VPN", chapters 1–2 (about 1 minute).

**Participants do:** listen, ask questions, **quiz**.

## Block 3 – Getting the configuration (20–35)

**You show** in Brave: account.protonvpn.com → **Downloads** → **WireGuard configuration** → name, **GNU/Linux** →
free server → **"Create"**. **Stop here** – do the download without a shared screen.

**Participants do:** account (if they don't have one yet), create the configuration, download, **"Check"**.

**Follow up:** "What's in the file?" – the private key. "How do you treat it?" – like a password.

## Block 4 – Importing and connecting (35–50)

**You show:** Bony's VPN → **"Import …"** → Downloads → file → **"Open"** → the tunnel appears → **"Connect"** →
"connected", handshake, amount of data → **"Public IP" – "Check"** → Brave: ipinfo.io shows the VPN server.

**Participants do:** the same, **"Check"**.

**Follow up:** raise ✋ as soon as ipinfo.io shows another country or the VPN provider.

## Block 5 – Kill switch and connecting automatically (50–65)

**You show:** **"Connect automatically"** on → **"Kill switch"** on (wait for the message) → Brave with ipinfo.io →
**"Disconnect"** → F5: "This site can't be reached" → **"Connect"** → F5: works again.

**Participants do:** the same, leave it **connected** at the end, **"Check"**.

**Follow up:** "What would have happened without the kill switch?" – carry on browsing unnoticed without the tunnel.
If there's time: Bony's Agents → running Agent PC → **"VPN"** tab – the same from outside.

## Block 6 – Exercise: browsing more privately (65–80)

See the exercise below.

## Block 7 – Cleaning up and wrap-up (80–90)

**You show:** file manager → Downloads → delete the `.conf` → empty the trash. Then the four points "security in
brief" and the outlook: VPN right when creating, the "VPN" tab, the "VPN" button for your own computer.

**Participants do:** clean up, **"Check"**, **quiz**.

**Wrap-up:** "Where will you use the VPN first?" Once more: **more private, not anonymous.** End the course.

# Exercise with solution (block 6)

**Task:** points 1 (DNS) and 2 (trackers) for everyone, plus at least one of 3–5.

**Solution / expectation:**

- **dnsleaktest.com → "Standard test":** only the VPN provider's servers (with Proton: "Proton AG" or similar), none
  of your own internet provider's.
- **coveryourtracks.eff.org → "TEST YOUR BROWSER":** trackers blocked (Brave), but usually a "unique fingerprint".
  Exactly the limit from block 2.
- **Private window with Tor:** Brave menu → "New private window with Tor" (Alt + Shift + N); connects after a few
  seconds, slower, sometimes captchas.
- **Throwaway PC / Tor Browser:** only show or explain – installing takes too long for the course.

**For fast learners:** look at menu → **"Kill switch exceptions …"**: which networks stay reachable without the
tunnel – and why is the Agent PC's network always included?

# Common pitfalls

| Problem | How you notice | What helps |
|---|---|---|
| No "Bony's VPN" icon | desktop | detail view → "Add programs …" → "WireGuard VPN (Bony's VPN)" |
| Proton confirmation e-mail doesn't arrive | e-mail | spam folder; otherwise plan B |
| File landed on your own computer | Downloads in the Agent PC is empty | create the configuration again in the **Agent PC's** Brave – don't send it by e-mail |
| No handshake / "Server not responding" | Bony's VPN | choose another free server, create it again, "Delete …" the old tunnel |
| Free account already in use | doesn't connect or disconnects right away | disconnect Proton on the phone (one device at a time) |
| Warning "Commands in the configuration" | when importing | don't take it over – not to be expected with Proton/FRITZ!Box |
| No internet after the test | Brave "can't be reached" | that's correct – kill switch; "Connect" again in Bony's VPN |
| DNS test shows your own internet provider | dnsleaktest | configuration without a `DNS =` line → create it again at Proton |
| Check "cleaned up" fails | lesson 7 | the file is still in Downloads (ZIP extracted?) or only in the trash – empty the trash |

# Plan B

**No Proton account possible** (no e-mail, confirmation doesn't arrive): anyone with a **FRITZ!Box** at home who is
sitting there takes way B. Otherwise they watch with you and catch up on lessons 3–5 in self-study mode. **Never pass
on your own configuration** – not even "just for today".

**Proton is down:** show import, kill switch and test pages with your prepared tunnel; participants get the
configuration later.

**Agent PC without internet after block 5:** kill switch on, tunnel disconnected → "Connect". If that doesn't help,
turn off the kill switch, reconnect the tunnel, turn the kill switch back on.
