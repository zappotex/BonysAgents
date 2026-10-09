# SPDX-License-Identifier: GPL-3.0-or-later
"""Bony's VPN – WireGuard-Tunnel verwalten, im Agent-PC und auf dem Linux-Host.

Dieses Paket hängt bewusst nicht vom Rest von Bony's Agents ab: Es wird einzeln in den
Agent-PC kopiert (Debian 13, nur python3, wireguard-tools, nftables, polkit).
Nur relative Importe, nur die Standardbibliothek.

- ``conf``       – .conf prüfen, Tunnelnamen, Schlüssel verbergen
- ``killswitch`` – nftables-Regelwerk des Kill-Switch (als Text)
- ``helper``     – ``bonys-vpn-helper``, läuft als root über pkexec
- ``cli``        – ``bonys-vpn``, die Kommandozeile für den Benutzer
- ``install``    – Helfer, polkit-Dateien und systemd-Unit an ihren Platz legen
"""
