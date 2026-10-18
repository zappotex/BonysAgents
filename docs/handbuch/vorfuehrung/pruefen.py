# SPDX-License-Identifier: GPL-3.0-or-later
"""Prüft die Bildschirmfotos: Stehen Zugangsdaten oder persönliche Daten dieses Rechners darin?

    python docs/handbuch/vorfuehrung/pruefen.py docs/handbuch/bilder

Liest jedes Bild per Texterkennung (tesseract, Deutsch) und sucht

- nach Daten dieses Rechners: Rechnername, Benutzername, Home-Ordner, alle eigenen IP-Adressen, E-Mail aus der
  Git-Einstellung, Instanz-ID und Token der echten Bony-Netz-Anmeldung (``~/.config/bonys-netz/konto.json``) –
  diese Werte werden nie ausgegeben, nur „gefunden“;
- nach IPv4-Adressen außerhalb der Beispielbereiche und nach langen Zeichenketten, die wie Tokens aussehen.

Ohne tesseract (``sudo apt install tesseract-ocr tesseract-ocr-deu``) prüft es nur die Dateinamen und bricht mit
Hinweis ab. Rückgabe 1, wenn etwas gefunden wurde.
"""

from __future__ import annotations

import getpass
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

# Adressen der Beispieldaten (bildschirmfotos.py) und allgemein unbedenkliche
ERLAUBT = [ipaddress.ip_network(n) for n in (
    "192.168.178.0/24",   # Beispiel-Heimnetz
    "192.168.179.0/24",   # Adresse im Beispiel-VPN-Tunnel
    "100.64.0.0/24",      # Bony-Netz der Beispiele (die echte eigene Adresse wird unten trotzdem gesucht)
    "10.8.0.0/24",        # WireGuard der Kursleiterin
    "10.0.2.0/24",        # QEMU-Netz im Agent-PC
    "127.0.0.0/8", "203.0.113.0/24", "198.51.100.0/24", "192.0.2.0/24",
)]
ERLAUBTE_WOERTER = {
    # Fingerabdruck und Link der Beispiel-Freigabe, Beispiel-Token-Teile
    "3f9a2c7e" * 8, "3F9A2C7E" * 8,
}
TOKEN = re.compile(r"[A-Za-z0-9_\-+/]{32,}")
IPV4 = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])")


def geheimnisse() -> dict[str, str]:
    """Was in keinem Bild stehen darf: Art → Wert (Werte werden nie ausgegeben)."""
    werte: dict[str, str] = {}
    werte["Rechnername"] = socket.gethostname()
    werte["Benutzername"] = getpass.getuser()
    werte["Home-Ordner"] = str(Path.home())
    try:
        import psutil

        for name, adressen in psutil.net_if_addrs().items():
            for a in adressen:
                if a.family == socket.AF_INET and not a.address.startswith("127."):
                    werte[f"IP-Adresse ({name})"] = a.address
    except ImportError:
        pass
    try:
        mail = subprocess.run(["git", "config", "user.email"], capture_output=True, text=True, timeout=5).stdout
        if mail.strip():
            werte["E-Mail"] = mail.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    basis = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    konto = Path(basis) / "bonys-netz" / "konto.json"
    try:
        daten = json.loads(konto.read_text("utf-8"))
        for schluessel in ("instanz_id", "token"):
            if daten.get(schluessel):
                werte[f"Bony-Netz {schluessel}"] = str(daten[schluessel])
    except (OSError, ValueError):
        pass
    return {k: v for k, v in werte.items() if v and len(v) >= 4}


def lesen(bild: Path) -> str:
    """Text im Bild (Seitenaufteilung „verstreuter Text“ – Fenster haben viele kleine Textstellen)."""
    ergebnis = subprocess.run(["tesseract", str(bild), "-", "-l", "deu+eng", "--psm", "11"],
                              capture_output=True, text=True, timeout=120)
    return ergebnis.stdout


def ip_erlaubt(text: str) -> bool:
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return True   # keine echte Adresse (z. B. Versionsnummer 6.12.48.1)
    return any(ip in netz for netz in ERLAUBT)


def main() -> int:
    ordner = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "bilder")
    bilder = sorted(ordner.rglob("*.png"))
    if not bilder:
        print(f"Keine Bilder in {ordner}.", file=sys.stderr)
        return 1
    if shutil.which("tesseract") is None:
        print("tesseract fehlt – die Bilder können nicht geprüft werden "
              "(sudo apt install tesseract-ocr tesseract-ocr-deu).", file=sys.stderr)
        return 1
    geheim = geheimnisse()
    eigene_ips = {v for k, v in geheim.items() if k.startswith("IP-Adresse")}
    funde = 0
    print(f"== Prüfe {len(bilder)} Bilder auf Daten dieses Rechners ({len(geheim)} Merkmale) und Zugangsdaten")
    for bild in bilder:
        text = lesen(bild)
        flach = re.sub(r"\s+", "", text).lower()
        probleme = []
        for art, wert in geheim.items():
            if art == "Benutzername" and len(wert) < 5:
                continue   # zu kurz, wäre in jedem Wort
            if art.startswith("IP-Adresse"):
                if re.search(rf"(?<![\d.]){re.escape(wert)}(?![\d])", text):
                    probleme.append(f"{art} gefunden")
            elif re.sub(r"\s+", "", wert).lower() in flach:
                probleme.append(f"{art} gefunden")
        for ip in IPV4.findall(text):
            if ip in eigene_ips:
                continue   # schon oben gemeldet
            if not ip_erlaubt(ip):
                probleme.append(f"unbekannte IP-Adresse {ip}")
        for wort in TOKEN.findall(text):
            beispiel = sum(wort.lower().count(x) for x in ("2c7e", "3f9a", "9a2c", "cte", "c7e")) >= 4
            if wort in ERLAUBTE_WOERTER or beispiel:
                continue   # Fingerabdruck der Beispiel-Freigabe (auch wenn die Texterkennung „3f“ als „3/“ liest)
            if re.fullmatch(r"[a-z\-]+", wort):   # lange Wörter mit Bindestrichen, kein Token
                continue
            if "/" in wort and re.fullmatch(r"[a-z0-9_./\-]+", wort):   # Pfad wie /home/anna/.local/…
                continue
            probleme.append(f"Zeichenkette wie ein Token ({len(wort)} Zeichen, beginnt mit {wort[:4]}…)")
        if probleme:
            funde += len(probleme)
            print(f"  ✗ {bild.relative_to(ordner)}: " + "; ".join(sorted(set(probleme))))
    if funde:
        print(f"{funde} Funde – bitte die Bilder ansehen.", file=sys.stderr)
        return 1
    print("  ✓ nichts gefunden")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
