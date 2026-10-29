- Deleting in the file manager (Nemo) moves the file to the trash – only "Empty trash" really removes it. If you like
  working in the terminal: `shred -u ~/Downloads/*.conf`.
- The check only looks for file names `*.conf` in the Downloads folders and whether a tunnel is imported in Bony's
  VPN – it opens no file.
- Final round: "Where will you use the VPN first?" – and the rule of thumb once more: more private, not anonymous.
- Templates: a "fresh" template (without personal data) resets Bony's VPN completely, and when passing it on
  (`.bonys`) Bony's Agents warns about any WireGuard configurations it finds. A template **with** personal data
  (clone) contains the tunnel including the key – never pass that on.
