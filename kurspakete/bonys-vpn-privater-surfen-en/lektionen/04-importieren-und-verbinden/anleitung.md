# Importing and connecting

## 1. Open Bony's VPN

Double-click **"Bony's VPN"** on the desktop. It shows **"No tunnels yet"**.

::: hinweis
In the Agent PC, Bony's VPN asks for **no password** – the Agent PC belongs to you alone. On your own computer it asks
for the administrator password.
:::

## 2. Import

Click **"Import …"**, **"Downloads"** on the left, choose your `.conf`, **"Open"**. The tunnel appears with the
file's name.

Bony's VPN shows address, DNS and server – **never the key**. It's now stored safely in the system (`/etc/wireguard`,
only readable by root).

## 3. Connect

Click **"Connect"**. After a second or two it says **"connected"**, plus the latest contact with the server
(handshake) and the amount of data transferred.

## 4. Check

- In Bony's VPN, click **"Check"** next to **"Public IP"** – that's now the VPN server's address.
- To compare, open `https://ipinfo.io` in Brave: location and provider are the VPN server's (e.g. Netherlands).

::: datenschutz
The address you see now belongs to the **VPN provider** – anyone may see it. Your own address stays hidden.
:::

Done? Click **"Check"**.
