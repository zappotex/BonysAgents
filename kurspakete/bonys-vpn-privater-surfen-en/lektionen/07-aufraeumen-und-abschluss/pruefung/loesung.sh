#!/bin/bash
# Solution – only runs with "Check course package" in the editor (test Agent PC, as root), never for participants:
# imports a made-up configuration (random keys, server vpn.example.net) and deletes .conf files from the Downloads
umask 077
schluessel() { head -c 32 /dev/urandom | base64; }
if ! bonys-vpn status --json | grep -q '"name"'; then
  printf '[Interface]\nPrivateKey = %s\nAddress = 10.8.0.2/32\n\n[Peer]\nPublicKey = %s\nAllowedIPs = 0.0.0.0/0\nEndpoint = vpn.example.net:51820\n' \
    "$(schluessel)" "$(schluessel)" | bonys-vpn import - --name demo-nl --json >/dev/null
fi
for d in /home/*/Downloads; do
  find "$d" -maxdepth 1 -type f -iname '*.conf' -exec shred -u {} + 2>/dev/null || true
done
