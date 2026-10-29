#!/bin/bash
# Solution – only runs with "Check course package" in the editor, never for participants: a made-up configuration
# (random keys, server vpn.example.net – doesn't connect anywhere)
ordner=$(xdg-user-dir DOWNLOAD 2>/dev/null || true)
[ -n "$ordner" ] && [ "$ordner" != "$HOME" ] || ordner="$HOME/Downloads"   # without an entry xdg names HOME
mkdir -p "$ordner"
umask 077
schluessel() { head -c 32 /dev/urandom | base64; }
cat > "$ordner/demo-nl.conf" <<CONF
[Interface]
PrivateKey = $(schluessel)
Address = 10.8.0.2/32
DNS = 10.8.0.1

[Peer]
PublicKey = $(schluessel)
AllowedIPs = 0.0.0.0/0, ::/0
Endpoint = vpn.example.net:51820
CONF
