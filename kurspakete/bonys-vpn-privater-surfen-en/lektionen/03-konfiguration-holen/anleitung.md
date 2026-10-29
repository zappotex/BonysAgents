# Getting the configuration

Bony's VPN is the **program** for the tunnel. You bring the **server** yourself: as a small file ending in
**`.conf`** from a VPN provider – or from your own FRITZ!Box.

::: warnung
The `.conf` contains your **private key**. Treat it like a **password**: don't show it, don't send it, don't post it
in the course chat.
:::

Work in **your Agent PC's Brave** – then the file lands right in the correct **Downloads** folder.

## Way A: Proton VPN (free plan)

1. Open `https://account.protonvpn.com` and sign in – or create a free account (plan **"Free"**, confirm your e-mail
   address).
2. Choose **"Downloads"** on the left, then scroll down to **"WireGuard configuration"**.
3. Enter a **name** for the device (e.g. `agent-pc`), platform **"GNU/Linux"**.
4. Leave the **VPN options** as they are. Under **Server** choose a **free server** (Free) – or the recommended one –
   and click **"Create"**.
5. In the window click **"Download"** – the `.conf` is now in **Downloads**.

::: hinweis
Proton's pages change now and then – if buttons are named slightly differently, look for "WireGuard".
:::

## Way B: your FRITZ!Box

For getting into your **own home network** from on the go – only works if you're at home or can reach the FRITZ!Box
from outside.

1. In the FRITZ!Box: **Internet → Permit Access → VPN (WireGuard)**.
2. **"Add Connection"** → **"Connect a single device"** → enter a name, confirm.
3. **Download** the settings **as a file** (`.conf`) and put it in the Agent PC's **Downloads** folder.

Done? Click **"Check"**. The check only looks at the **file name** – it doesn't open the file.
