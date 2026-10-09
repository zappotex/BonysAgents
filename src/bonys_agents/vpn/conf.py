# SPDX-License-Identifier: GPL-3.0-or-later
"""WireGuard-Konfiguration (.conf) prüfen – streng, ohne je einen Schlüssel auszugeben.

Fehlermeldungen nennen nur Zeilennummer und Feldname, nie den Wert: In der Datei stehen
private Schlüssel, und Meldungen landen in Oberflächen und Protokollen.
"""

from __future__ import annotations

import base64
import binascii
import ipaddress
import re
from dataclasses import dataclass, field

# Wie wg-quick: höchstens 15 Zeichen (Länge eines Linux-Netzwerkgeräts)
NAME_RE = re.compile(r"[a-zA-Z0-9_=+.-]{1,15}")
MAX_SIZE = 64 * 1024
MARKER = "# Verwaltet von Bony's VPN"
HIDDEN = "(verborgen)"

HOOK_KEYS = ("PreUp", "PostUp", "PreDown", "PostDown")
INTERFACE_KEYS = ("PrivateKey", "Address", "DNS", "MTU", "Table", "ListenPort", "FwMark", "SaveConfig", *HOOK_KEYS)
PEER_KEYS = ("PublicKey", "PresharedKey", "AllowedIPs", "Endpoint", "PersistentKeepalive")
SECRET_KEYS = ("PrivateKey", "PresharedKey")
# Diese Felder dürfen mehrfach vorkommen – wg-quick hängt sie aneinander.
REPEATABLE = ("Address", "DNS", "AllowedIPs", *HOOK_KEYS)

_HOSTNAME_RE = re.compile(r"(?=.{1,253}\.?$)([A-Za-z0-9_]([A-Za-z0-9_-]{0,61}[A-Za-z0-9_])?\.)*"
                          r"[A-Za-z0-9_]([A-Za-z0-9_-]{0,61}[A-Za-z0-9_])?\.?")
_LINE_RE = re.compile(r"([A-Za-z]+)\s*=\s*(.*)")
_KEYNAME_RE = re.compile(r"[A-Za-z]{1,32}")


class ConfError(ValueError):
    """Ungültige Konfiguration oder ungültiger Tunnelname (Meldung auf Deutsch, ohne Schlüssel)."""


@dataclass
class Peer:
    public_key: str
    allowed_ips: list[str] = field(default_factory=list)
    endpoint: tuple[str, int] | None = None  # (Host oder IP, Port)


@dataclass
class TunnelConf:
    addresses: list[str] = field(default_factory=list)
    dns: list[str] = field(default_factory=list)
    mtu: int | None = None
    peers: list[Peer] = field(default_factory=list)
    hooks: list[str] = field(default_factory=list)  # Namen der Hook-Felder, z. B. ["PostUp"]

    def summary(self) -> dict:
        """Nicht geheime Angaben für Status und Oberfläche (ohne Private/Preshared Key)."""
        return {
            "addresses": self.addresses,
            "dns": self.dns,
            "mtu": self.mtu,
            "peers": [{"public_key": p.public_key, "allowed_ips": p.allowed_ips,
                       "endpoint": format_endpoint(p.endpoint) if p.endpoint else None} for p in self.peers],
            "hooks": self.hooks,
        }


def check_name(name: str) -> str:
    """Tunnelnamen prüfen: nur ``[a-zA-Z0-9_=+.-]{1,15}``, keine Pfade, nichts, was wie eine Option aussieht."""
    if not isinstance(name, str) or not NAME_RE.fullmatch(name) or name in (".", "..") or name.startswith("-"):
        raise ConfError("Ungültiger Tunnelname. Erlaubt sind 1–15 Zeichen aus A–Z, a–z, 0–9 und _ = + . - "
                        "(nicht mit „-“ am Anfang).")
    return name


def check_key(value: str) -> str:
    """WireGuard-Schlüssel: 44 Zeichen Base64, ergibt genau 32 Byte."""
    if len(value) != 44 or not value.endswith("="):
        raise ValueError
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError from None
    if len(raw) != 32:
        raise ValueError
    return value


def parse_endpoint(value: str) -> tuple[str, int]:
    """``host:port`` oder ``[IPv6]:port`` → (host, port). Host ist IP-Adresse oder DNS-Name."""
    if value.startswith("["):
        host, sep, port = value[1:].partition("]:")
        if not sep:
            raise ValueError
        ipaddress.IPv6Address(host)
    else:
        host, sep, port = value.rpartition(":")
        if not sep or not host:
            raise ValueError
        try:
            ipaddress.IPv4Address(host)
        except ValueError:
            if ":" in host or not _HOSTNAME_RE.fullmatch(host) or host.replace(".", "").isdigit():
                raise ValueError from None
    if not port.isdigit() or not 1 <= int(port) <= 65535:
        raise ValueError
    return host, int(port)


def format_endpoint(ep: tuple[str, int]) -> str:
    host, port = ep
    return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"


def _split(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def _int(value: str, lo: int, hi: int) -> int:
    n = int(value, 0) if value.lower().startswith("0x") else int(value)
    if not lo <= n <= hi:
        raise ValueError
    return n


def decode(data: bytes) -> str:
    """Rohdaten einer .conf → Text. Prüft Größe, UTF-8 und Steuerzeichen; entfernt BOM und \\r."""
    if len(data) > MAX_SIZE:
        raise ConfError("Die Datei ist zu groß für eine WireGuard-Konfiguration (höchstens 64 KiB).")
    if not data.strip():
        raise ConfError("Die Datei ist leer.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ConfError("Die Datei ist keine Textdatei (UTF-8).") from None
    text = text.replace("\r\n", "\n")
    if any(ord(c) < 32 and c not in "\n\t" or c == "\x7f" for c in text):
        raise ConfError("Die Datei enthält Steuerzeichen und ist keine WireGuard-Konfiguration.")
    return text


def parse(text: str) -> TunnelConf:
    """Konfiguration prüfen und die nicht geheimen Angaben zurückgeben. Fehler → ConfError."""
    conf = TunnelConf()
    section: str | None = None
    seen: set[str] = set()
    interfaces = 0
    peer: Peer | None = None
    has_private = False

    def fail(lineno: int, msg: str):
        raise ConfError(f"Zeile {lineno}: {msg}")

    def close_peer(lineno: int) -> None:
        if peer is None:
            return
        if not peer.public_key:
            fail(lineno, "Im Abschnitt [Peer] fehlt PublicKey.")
        if not peer.allowed_ips:
            fail(lineno, "Im Abschnitt [Peer] fehlt AllowedIPs.")
        conf.peers.append(peer)

    lines = text.split("\n")
    for lineno, raw in enumerate(lines, 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            name = line[1:-1].strip().lower()
            if name == "interface":
                close_peer(lineno)
                peer = None
                interfaces += 1
                if interfaces > 1:
                    fail(lineno, "Der Abschnitt [Interface] darf nur einmal vorkommen.")
                section = "Interface"
            elif name == "peer":
                close_peer(lineno)
                peer = Peer(public_key="")
                section = "Peer"
            else:
                fail(lineno, "Unbekannter Abschnitt – erlaubt sind nur [Interface] und [Peer].")
            seen = set()
            continue
        m = _LINE_RE.fullmatch(line)
        if not m:
            fail(lineno, "Die Zeile hat nicht die Form „Name = Wert“.")
        if section is None:
            fail(lineno, "Eintrag vor dem ersten Abschnitt [Interface].")
        key_raw, value = m.group(1), m.group(2).strip()
        allowed = INTERFACE_KEYS if section == "Interface" else PEER_KEYS
        key = next((k for k in allowed if k.lower() == key_raw.lower()), None)
        if key is None:
            shown = key_raw if _KEYNAME_RE.fullmatch(key_raw) else "?"
            fail(lineno, f"Unbekannter Eintrag „{shown}“ im Abschnitt [{section}].")
        if key in seen and key not in REPEATABLE:
            fail(lineno, f"{key} kommt im Abschnitt [{section}] doppelt vor.")
        seen.add(key)
        try:
            if key == "PrivateKey":
                check_key(value)
                has_private = True
            elif key == "Address":
                items = _split(value)
                for a in items:
                    ipaddress.ip_interface(a)
                if not items:
                    raise ValueError
                conf.addresses += items
            elif key == "DNS":
                items = _split(value)
                for d in items:
                    try:
                        ipaddress.ip_address(d)
                    except ValueError:
                        if not _HOSTNAME_RE.fullmatch(d):
                            raise
                if not items:
                    raise ValueError
                conf.dns += items
            elif key == "MTU":
                conf.mtu = _int(value, 576, 9200)
            elif key == "Table":
                if value.lower() not in ("off", "auto", "main"):
                    _int(value, 0, 2**32 - 1)
            elif key == "ListenPort":
                _int(value, 0, 65535)
            elif key == "FwMark":
                if value.lower() != "off":
                    _int(value, 0, 2**32 - 1)
            elif key == "SaveConfig":
                if value.lower() == "true":
                    fail(lineno, "SaveConfig = true wird nicht unterstützt (wg-quick würde die Datei "
                                 "beim Trennen überschreiben).")
                if value.lower() != "false":
                    raise ValueError
            elif key in HOOK_KEYS:
                if not value:
                    raise ValueError
                if key not in conf.hooks:
                    conf.hooks.append(key)
            elif key == "PublicKey":
                peer.public_key = check_key(value)
            elif key == "PresharedKey":
                check_key(value)
            elif key == "AllowedIPs":
                items = _split(value)
                for n in items:
                    ipaddress.ip_network(n, strict=False)
                peer.allowed_ips += items
            elif key == "Endpoint":
                peer.endpoint = parse_endpoint(value)
            elif key == "PersistentKeepalive":
                if value.lower() != "off":
                    _int(value, 0, 65535)
        except ConfError:
            raise
        except ValueError:
            fail(lineno, f"Ungültiger Wert für {key}.")
    close_peer(len(lines))
    if interfaces == 0:
        raise ConfError("Der Abschnitt [Interface] fehlt.")
    if not has_private:
        raise ConfError("Im Abschnitt [Interface] fehlt PrivateKey.")
    if not conf.peers:
        raise ConfError("Es gibt keinen Abschnitt [Peer].")
    if not conf.addresses:
        raise ConfError("Im Abschnitt [Interface] fehlt Address.")
    return conf


def mask(text: str) -> str:
    """Konfiguration mit verborgenen Schlüsseln (für Editor und Anzeige)."""
    out = []
    for line in text.split("\n"):
        m = _LINE_RE.fullmatch(line.split("#", 1)[0].strip())
        if m and m.group(1).lower() in (k.lower() for k in SECRET_KEYS):
            indent = line[: len(line) - len(line.lstrip())]
            line = f"{indent}{m.group(1)} = {HIDDEN}"
        out.append(line)
    return "\n".join(out)


def secrets_of(text: str) -> list[str]:
    """Alle Schlüsselwerte (PrivateKey, PresharedKey) – nur für Tests und das Zurückschreiben im Editor."""
    found = []
    for line in text.split("\n"):
        m = _LINE_RE.fullmatch(line.split("#", 1)[0].strip())
        if m and m.group(1).lower() in (k.lower() for k in SECRET_KEYS):
            found.append(m.group(2).strip())
    return found


def unmask(new_text: str, old_text: str) -> str:
    """Im Editor unverändert gelassene ``(verborgen)``-Schlüssel durch die gespeicherten ersetzen.

    Zuordnung der Reihe nach: der n-te verborgene Schlüssel einer Art ↔ der n-te gespeicherte derselben Art.
    """
    old: dict[str, list[str]] = {k.lower(): [] for k in SECRET_KEYS}
    for line in old_text.split("\n"):
        m = _LINE_RE.fullmatch(line.split("#", 1)[0].strip())
        if m and m.group(1).lower() in old:
            old[m.group(1).lower()].append(m.group(2).strip())
    counts = {k: 0 for k in old}
    out = []
    for line in new_text.split("\n"):
        m = _LINE_RE.fullmatch(line.split("#", 1)[0].strip())
        if m and m.group(1).lower() in old:
            k = m.group(1).lower()
            i = counts[k]
            counts[k] += 1
            if m.group(2).strip() == HIDDEN:
                if i >= len(old[k]):
                    raise ConfError(f"{m.group(1)} ist verborgen, aber es gibt keinen gespeicherten Schlüssel dafür.")
                indent = line[: len(line) - len(line.lstrip())]
                line = f"{indent}{m.group(1)} = {old[k][i]}"
        out.append(line)
    return "\n".join(out)


def with_marker(text: str) -> str:
    """Text, wie er in /etc/wireguard landet: Markierungszeile + Konfiguration, Zeilenende \\n."""
    body = "\n".join(line for line in text.split("\n") if line.strip() != MARKER).strip("\n")
    return f"{MARKER}\n{body}\n"


def is_managed(text: str) -> bool:
    return text.split("\n", 1)[0].strip() == MARKER
