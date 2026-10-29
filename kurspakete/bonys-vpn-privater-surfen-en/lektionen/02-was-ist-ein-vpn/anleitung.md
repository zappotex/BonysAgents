# What is a VPN?

## Without a VPN

Your computer sends everything via your **internet provider** (or the café Wi-Fi) to the website.

- The internet provider or the Wi-Fi sees **which sites** you visit.
- The website sees your **real address** (IP) – and with it roughly your location.
- With `https://` the **contents** are encrypted – but not **who** you're talking to.

## With a VPN

A VPN builds an **encrypted tunnel** from your computer to a **VPN server**, for example in the Netherlands. Only
there does it go out into the open internet.

- Internet provider and Wi-Fi only see: encrypted data to a VPN server.
- The website sees the **VPN server's** address, not yours.
- In return, the **VPN provider** knows your destination – so choose it carefully.

Bony's VPN uses **WireGuard**: modern, fast and built directly into the Linux kernel.

## What a VPN does – and what it doesn't

| Does | Doesn't |
|---|---|
| Public Wi-Fi: nobody can read along | **Anonymity** – the VPN provider sees where you go |
| Your internet provider doesn't see your sites | Anyone who signs in is recognized – no matter via which address |
| Websites don't see your address | Cookies and trackers recognize you again |
| From on the go into your home network (FRITZ!Box) | The browser has a "fingerprint" |
| Kill switch: no tunnel, no internet | Protection against viruses or scam sites |

::: tipp
Rule of thumb: **A VPN makes you more private, not anonymous.** For more privacy, habits come on top – you practice
them in lesson 6.
:::

Finally: the **quiz**.
