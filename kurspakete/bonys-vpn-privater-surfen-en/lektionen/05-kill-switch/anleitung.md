# Kill switch and connecting automatically

## 1. Connect automatically

Turn on the **"Connect automatically"** switch: from now on the tunnel is up at **every start** of the Agent PC. Only
one tunnel ever connects automatically.

## 2. Kill switch

Turn on the **"Kill switch"** switch. Bony's VPN reports: *"Kill switch on: without a tunnel the internet is now
blocked."*

Without a kill switch, your Agent PC would carry on browsing **unnoticed without the tunnel** if the connection
dropped – with your real address. With the kill switch, **nothing at all** gets out then. That also applies after a
restart – until you turn it off.

## 3. Test

1. Open `https://ipinfo.io` in Brave.
2. Click **"Disconnect"** in Bony's VPN.
3. Reload in Brave (**F5**): *"This site can't be reached"* – that's exactly how it should be.
4. Click **"Connect"** again in Bony's VPN, reload in Brave – everything works as before.

::: hinweis
The Agent PC's own network stays reachable with the kill switch, otherwise Bony's Agents couldn't control it. Further
exceptions (e.g. for the home network) are in the **menu** under **"Kill switch exceptions …"**.
:::

Done – and connected again? Click **"Check"**.
