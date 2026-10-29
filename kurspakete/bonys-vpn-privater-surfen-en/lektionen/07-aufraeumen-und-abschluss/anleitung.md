# Cleaning up and wrap-up

## 1. Delete the .conf from Downloads

Bony's VPN **stored** the configuration **safely** when importing – you no longer need the file in Downloads. There,
any program you start can read it.

Open the file manager → **Downloads** → **delete** the `.conf` (or the `.zip`) and **empty the trash**.

::: hinweis
If you need the configuration somewhere else later, simply create a new one at the provider – or export it in Bony's
VPN via **"Export …"**.
:::

Done? Click **"Check"**.

## 2. Security in brief

- Only a small **helper** has administrator rights – and may only carry out fixed actions.
- **Keys** are only in `/etc/wireguard`, only readable by root – in no display.
- Bony's VPN only takes over **commands in a .conf** (PostUp …) after a clear warning.
- The **kill switch** also applies after a restart – until you turn it off.

## 3. What you learned today

- Without a VPN, internet providers and websites see a lot – with a VPN, the **VPN provider** sees your destination.
- The `.conf` is a **password**: get it, import it, delete it from Downloads.
- **Import → connect → check**, plus **kill switch** and **connecting automatically**.
- **More private, not anonymous:** check DNS, block trackers, keep sign-ins apart, throwaway PC, Tor.

## How to continue

- **Right when creating:** the "New Agent PC" window has a **VPN** section – choose the `.conf` there and tick
  "Connect automatically" and "Kill switch". The new Agent PC starts with the tunnel right away.
- **Controlling it from outside:** Bony's Agents → running Agent PC → **"VPN"** tab.
- **On your own Linux computer:** the **"VPN"** button in the main window installs Bony's VPN there – then the VPN
  applies to all programs (with the administrator password). For Windows and Mac there's the official WireGuard app.
- **Video** "Bony's VPN": youtube.com/@BonysAgents

Finally: the **quiz**.
