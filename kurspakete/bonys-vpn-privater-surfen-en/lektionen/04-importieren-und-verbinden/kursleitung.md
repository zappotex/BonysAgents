- When presenting, don't show the **tunnel card** (address, DNS, endpoint) for long – make the window smaller or click
  on after the import. Bony's VPN never shows the key anyway.
- "Server not responding" / no handshake: server overloaded or switched off → get a new configuration with another
  free server at Proton, remove the old tunnel in Bony's VPN via "Delete …".
- Free account already connected on the phone → disconnect there (one device at a time).
- Warning **"Commands in the configuration"**: not to be expected with Proton and FRITZ!Box. If it does appear, don't
  take over the file – such commands run as root.
- The check only asks `bonys-vpn status --json` (connected tunnel with handshake) – it contains no keys.
