#!/bin/bash
# Lösung – läuft nur bei „Kurspaket prüfen“ im Editor, nie bei Teilnehmern: eine erfundene Konfiguration
# (zufällige Schlüssel, Server vpn.example.net – verbindet sich nirgendwohin)
ordner=$(xdg-user-dir DOWNLOAD 2>/dev/null || true)
[ -n "$ordner" ] && [ "$ordner" != "$HOME" ] || ordner="$HOME/Downloads"   # ohne Eintrag nennt xdg HOME
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
