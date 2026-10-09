# SPDX-License-Identifier: GPL-3.0-or-later
"""Logik der Oberfläche von Bony's VPN – ohne GTK, damit sie sich testen lässt.

- Sprache (Deutsch, sonst Englisch) und Formatierung (Datenmenge, Alter des Handshakes)
- ``Status``: Antwort von ``bonys-vpn-helper status`` als Modell, Live-Werte aus /sys
- ``Watch``: erkennt Verbindungsabbrüche (Tunnel weg, Server antwortet nicht mehr)
- Editor: Prüfung mit verborgenen Schlüsseln, Schlüssel anzeigen/verbergen
- Import: Namensvorschlag aus dem Dateinamen
- öffentliche IP abfragen, Export mit Rechten 600

Nur Standardbibliothek, nur relative Importe (wird wie der Rest von ``vpn`` einzeln kopiert).
"""

from __future__ import annotations

import contextlib
import ipaddress
import json
import os
import re
import tempfile
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from . import conf as wgconf

SYS_NET = Path("/sys/class/net")
# Öffentliche IP: nur auf Knopfdruck, die Oberfläche nennt den Dienst.
IP_SERVICE = "https://api.ipify.org?format=json"
IP_SERVICE_NAME = "api.ipify.org"
# WireGuard verwirft eine Sitzung nach 180 s ohne neuen Handshake (REJECT_AFTER_TIME). Einen neuen
# Handshake gibt es aber nur, wenn gesendet wird: Ab 120 s nach dem letzten (REKEY_AFTER_TIME) löst
# jedes gesendete Paket einen aus. Ein untätiger Tunnel hat deshalb einfach einen alten Handshake.
STALE_AFTER = 180
REKEY_AFTER = 120
REKEY_GRACE = 15  # so lange darf der neue Handshake nach dem Senden dauern
# Platzhalter-Schlüssel (32 Nullbytes) – nur, um eine Konfiguration mit „(verborgen)“ lokal zu prüfen.
_DUMMY_KEY = "A" * 43 + "="

# ---------------------------------------------------------------- Sprache
EN = {
    "Bony's VPN": "Bony's VPN",
    "WireGuard-Tunnel verwalten": "Manage WireGuard tunnels",
    "verbunden": "connected",
    "getrennt": "disconnected",
    "verbindet …": "connecting …",
    "trennt …": "disconnecting …",
    "Verbinden": "Connect",
    "Trennen": "Disconnect",
    "Importieren …": "Import …",
    "Bearbeiten …": "Edit …",
    "Umbenennen …": "Rename …",
    "Exportieren …": "Export …",
    "Löschen …": "Delete …",
    "Neu laden": "Reload",
    "Adresse": "Address",
    "DNS": "DNS",
    "Endpunkt": "Endpoint",
    "Letzter Handshake": "Latest handshake",
    "Empfangen": "Received",
    "Gesendet": "Sent",
    "Öffentliche IP": "Public IP",
    "Prüfen": "Check",
    "fragt {service}": "asks {service}",
    "wird abgefragt …": "checking …",
    "nicht erreichbar": "not reachable",
    "noch keiner": "none yet",
    "vor {n} s": "{n} s ago",
    "vor {n} min": "{n} min ago",
    "vor {h} h {m} min": "{h} h {m} min ago",
    "Automatisch verbinden": "Connect automatically",
    "Verbindet diesen Tunnel beim Hochfahren des Rechners (immer nur ein Tunnel).":
        "Connects this tunnel when the computer starts (only one tunnel at a time).",
    "Kill-Switch": "Kill switch",
    "Ohne verbundenen Tunnel kommt kein Programm ins Internet – auch nicht, wenn der Tunnel abbricht "
    "oder nach einem Neustart.":
        "Without a connected tunnel no program can reach the internet – not even if the tunnel drops "
        "or after a restart.",
    "Immer erreichbar: {nets}": "Always reachable: {nets}",
    "Noch keine Tunnel": "No tunnels yet",
    "WireGuard-Konfiguration (.conf oder .zip) hierher ziehen oder „Importieren …“ wählen.":
        "Drag a WireGuard configuration (.conf or .zip) here or choose “Import …”.",
    "Kein Tunnel verbunden": "No tunnel connected",
    "Verbunden mit {name}": "Connected to {name}",
    "Internet gesperrt (Kill-Switch)": "Internet blocked (kill switch)",
    "Server antwortet nicht": "Server not responding",
    "nicht von Bony's VPN angelegt – nur verbinden und trennen":
        "not created by Bony's VPN – connect and disconnect only",
    "Achtung: führt beim Verbinden Befehle als root aus ({hooks}).":
        "Warning: runs commands as root when connecting ({hooks}).",
    "Fehler in der Konfiguration: {error}": "Error in the configuration: {error}",
    "Fenster öffnen": "Open window",
    "Beenden": "Quit",
    "Alle trennen": "Disconnect all",
    "Verbindung abgebrochen": "Connection lost",
    "Der Tunnel „{name}“ ist nicht mehr verbunden.": "The tunnel “{name}” is no longer connected.",
    "Der Server von „{name}“ antwortet seit über 3 Minuten nicht.":
        "The server of “{name}” has not responded for more than 3 minutes.",
    "Verbindung wieder da": "Connection restored",
    "„{name}“ antwortet wieder.": "“{name}” is responding again.",
    "Konfigurationen importieren": "Import configurations",
    "WireGuard-Konfigurationen": "WireGuard configurations",
    "Abbrechen": "Cancel",
    "Öffnen": "Open",
    "Speichern": "Save",
    "Name des Tunnels": "Tunnel name",
    "1–15 Zeichen: A–Z, a–z, 0–9 und _ = + . -": "1–15 characters: A–Z, a–z, 0–9 and _ = + . -",
    "Den Tunnel „{name}“ gibt es schon.": "The tunnel “{name}” already exists.",
    "Ersetzen": "Replace",
    "Anderer Name": "Other name",
    "Überspringen": "Skip",
    "Befehle in der Konfiguration": "Commands in the configuration",
    "„{name}“ enthält {hooks}. Diese Zeilen sind Shell-Befehle, die beim Verbinden und Trennen "
    "als root laufen. Eine fremde Datei kann damit den ganzen Rechner übernehmen.\n\n"
    "Nur übernehmen, wenn du der Datei vertraust.":
        "“{name}” contains {hooks}. These lines are shell commands that run as root when connecting "
        "and disconnecting. A foreign file can take over the whole computer with them.\n\n"
        "Only accept if you trust the file.",
    "Trotzdem übernehmen": "Accept anyway",
    "„{name}“ importiert.": "“{name}” imported.",
    "„{name}“ löschen?": "Delete “{name}”?",
    "Die Konfiguration mit dem privaten Schlüssel wird gelöscht. Das lässt sich nicht rückgängig machen.":
        "The configuration including the private key will be deleted. This cannot be undone.",
    "Löschen": "Delete",
    "„{name}“ umbenennen": "Rename “{name}”",
    "Umbenennen": "Rename",
    "„{name}“ exportieren": "Export “{name}”",
    "Exportiert nach {path} (nur für dich lesbar – enthält den privaten Schlüssel).":
        "Exported to {path} (readable only by you – contains the private key).",
    "„{name}“ bearbeiten": "Edit “{name}”",
    "Schlüssel anzeigen": "Show keys",
    "Private Schlüssel sind verborgen. Unverändert gelassenes „(verborgen)“ behält den gespeicherten Schlüssel.":
        "Private keys are hidden. An unchanged “(hidden)” keeps the stored key.",
    "Die Konfiguration ist in Ordnung.": "The configuration is valid.",
    "Gespeichert.": "Saved.",
    "Nur ansehen – der Tunnel wurde nicht mit Bony's VPN angelegt.":
        "View only – the tunnel was not created with Bony's VPN.",
    "Schließen": "Close",
    "Tunnel": "Tunnel",
    "Fehler": "Error",
    "Bitte zuerst trennen.": "Please disconnect first.",
    "Kill-Switch an: Ohne Tunnel ist das Internet jetzt gesperrt.":
        "Kill switch on: without a tunnel the internet is now blocked.",
    "Kill-Switch aus.": "Kill switch off.",
    "Der Helfer ist nicht installiert.": "The helper is not installed.",
    "Kein Symbol in der Leiste – dieser Desktop zeigt keine Statussymbole.":
        "No tray icon – this desktop does not show status icons.",
}

_lang: str | None = None


def language(env=None) -> str:
    """„de“ für deutsche Systeme, sonst „en“ (wie gettext: LANGUAGE, LC_ALL, LC_MESSAGES, LANG)."""
    env = os.environ if env is None else env
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = env.get(var, "")
        if value and value not in ("C", "POSIX", "C.UTF-8"):
            return "de" if value.split(":")[0].lower().startswith("de") else "en"
    return "en"


def set_language(lang: str | None) -> None:
    global _lang
    _lang = lang


def tr(text: str, **kw) -> str:
    """Deutscher Text → in der Sprache der Oberfläche (Englisch, wenn das System nicht deutsch ist)."""
    lang = _lang or language()
    out = text if lang == "de" else EN.get(text, text)
    return out.format(**kw) if kw else out


# ---------------------------------------------------------------- Formatierung
def fmt_bytes(n: int | None, lang: str | None = None) -> str:
    lang = lang or _lang or language()
    value = float(n or 0)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            if unit == "B":
                return f"{value:.0f} B"
            text = f"{value:.1f} {unit}"
            return text.replace(".", ",") if lang == "de" else text
        value /= 1024
    return ""


def fmt_age(ts: int | None, now: float | None = None) -> str:
    if not ts:
        return tr("noch keiner")
    s = max(0, int((now if now is not None else time.time()) - ts))
    if s < 60:
        return tr("vor {n} s", n=s)
    if s < 3600:
        return tr("vor {n} min", n=s // 60)
    return tr("vor {h} h {m} min", h=s // 3600, m=s % 3600 // 60)


def join(items) -> str:
    return ", ".join(i for i in items if i) or "–"


# ---------------------------------------------------------------- Status
@dataclass
class Tunnel:
    name: str
    active: bool = False
    autostart: bool = False
    managed: bool = True
    addresses: list[str] = field(default_factory=list)
    dns: list[str] = field(default_factory=list)
    endpoints: list[str] = field(default_factory=list)
    hooks: list[str] = field(default_factory=list)
    handshake: int | None = None
    rx: int = 0
    tx: int = 0
    error: str = ""
    sent_at: float | None = None  # wann zuletzt Daten hinausgingen (aus /sys, siehe Activity)

    @classmethod
    def from_status(cls, d: dict) -> Tunnel:
        return cls(
            name=str(d.get("name", "")),
            active=bool(d.get("active")),
            autostart=bool(d.get("autostart")),
            managed=bool(d.get("managed", True)),
            addresses=list(d.get("addresses") or []),
            dns=list(d.get("dns") or []),
            endpoints=[p["endpoint"] for p in d.get("peers") or [] if p.get("endpoint")],
            hooks=list(d.get("hooks") or []),
            handshake=d.get("handshake") or None,
            rx=int(d.get("rx") or 0),
            tx=int(d.get("tx") or 0),
            error=str(d.get("error") or ""),
        )

    def stale(self, now: float | None = None) -> bool:
        """Server antwortet nicht: Handshake älter als 3 Minuten, obwohl nach Ablauf der 120 s gesendet
        wurde – dann hätte WireGuard längst einen neuen ausgehandelt. Ein bloß untätiger Tunnel
        (nichts gesendet) gilt nicht als abgebrochen."""
        if not self.active or not self.handshake or self.sent_at is None:
            return False
        now = now if now is not None else time.time()
        return (now - self.handshake > STALE_AFTER
                and self.sent_at - self.handshake > REKEY_AFTER + REKEY_GRACE)

    def detail_rows(self, now: float | None = None) -> list[tuple[str, str]]:
        rows = [(tr("Adresse"), join(self.addresses)), (tr("DNS"), join(self.dns)),
                (tr("Endpunkt"), join(self.endpoints))]
        if self.active:
            rows += [(tr("Letzter Handshake"), fmt_age(self.handshake, now)),
                     (tr("Empfangen"), fmt_bytes(self.rx)), (tr("Gesendet"), fmt_bytes(self.tx))]
        return rows


@dataclass
class Status:
    tunnels: list[Tunnel] = field(default_factory=list)
    killswitch_enabled: bool = False
    killswitch_active: bool = False
    exceptions: list[str] = field(default_factory=list)

    @classmethod
    def from_helper(cls, data: dict) -> Status:
        ks = data.get("killswitch") or {}
        return cls(tunnels=[Tunnel.from_status(t) for t in data.get("tunnels") or [] if t.get("name")],
                   killswitch_enabled=bool(ks.get("enabled")), killswitch_active=bool(ks.get("active")),
                   exceptions=list(ks.get("exceptions") or []))

    @property
    def active(self) -> Tunnel | None:
        return next((t for t in self.tunnels if t.active), None)

    def get(self, name: str | None) -> Tunnel | None:
        return next((t for t in self.tunnels if t.name == name), None)

    def names(self) -> list[str]:
        return [t.name for t in self.tunnels]

    def apply_live(self, live: dict[str, tuple[int, int]]) -> bool:
        """Live-Werte aus /sys übernehmen (aktive Geräte → (rx, tx)). Gibt True zurück, wenn sich
        der Verbindungszustand eines bekannten Tunnels geändert hat – dann den Helfer neu fragen."""
        changed = False
        for t in self.tunnels:
            now_active = t.name in live
            if now_active != t.active:
                changed = True
            if now_active:
                t.rx, t.tx = live[t.name]
        return changed

    def state(self, now: float | None = None) -> str:
        """Gesamtzustand für Tray-Symbol und Kopfzeile: connected, warning, blocked, disconnected."""
        a = self.active
        if a:
            return "warning" if a.stale(now) else "connected"
        if self.killswitch_enabled and self.killswitch_active:
            return "blocked"
        return "disconnected"

    def summary(self, now: float | None = None) -> str:
        a = self.active
        if a:
            return tr("Server antwortet nicht") if a.stale(now) else tr("Verbunden mit {name}", name=a.name)
        if self.killswitch_enabled and self.killswitch_active:
            return tr("Internet gesperrt (Kill-Switch)")
        return tr("Kein Tunnel verbunden")


def read_live(sys_net: Path = SYS_NET) -> dict[str, tuple[int, int]]:
    """Aktive WireGuard-Geräte mit (rx, tx) – ohne root, direkt aus /sys (kein pkexec bei jeder Abfrage)."""
    out: dict[str, tuple[int, int]] = {}
    try:
        entries = list(sys_net.iterdir())
    except OSError:
        return out
    for dev in entries:
        try:
            if "DEVTYPE=wireguard" not in (dev / "uevent").read_text().split("\n"):
                continue
            stats = dev / "statistics"
            out[dev.name] = (int((stats / "rx_bytes").read_text()), int((stats / "tx_bytes").read_text()))
        except (OSError, ValueError):
            continue
    return out


# ---------------------------------------------------------------- Abbrüche erkennen
@dataclass
class Event:
    kind: str   # "dropped", "stale", "restored"
    name: str

    def title(self) -> str:
        return tr("Verbindung wieder da") if self.kind == "restored" else tr("Verbindung abgebrochen")

    def body(self) -> str:
        if self.kind == "dropped":
            return tr("Der Tunnel „{name}“ ist nicht mehr verbunden.", name=self.name)
        if self.kind == "stale":
            return tr("Der Server von „{name}“ antwortet seit über 3 Minuten nicht.", name=self.name)
        return tr("„{name}“ antwortet wieder.", name=self.name)


class Watch:
    """Meldet Abbrüche genau einmal: Tunnel ohne eigenes Zutun weg, oder kein Handshake mehr.

    Eigene Aktionen (verbinden, trennen, löschen …) kündigt die Oberfläche mit ``expect()`` an –
    der dadurch verschwundene Tunnel ist dann kein Abbruch.
    """

    def __init__(self) -> None:
        self.last_active: str | None = None
        self.stale: set[str] = set()
        self.expected_until = 0.0
        self.initialized = False

    def expect(self, seconds: float = 30, now: float | None = None) -> None:
        self.expected_until = (now if now is not None else time.time()) + seconds

    def observe(self, status: Status, now: float | None = None) -> list[Event]:
        now = now if now is not None else time.time()
        a = status.active
        name = a.name if a else None
        events: list[Event] = []
        if not self.initialized:
            self.initialized = True
        elif self.last_active and name != self.last_active and now > self.expected_until \
                and self.last_active in status.names():
            events.append(Event("dropped", self.last_active))
        if a:
            if a.stale(now) and a.name not in self.stale:
                self.stale.add(a.name)
                events.append(Event("stale", a.name))
            elif not a.stale(now) and a.name in self.stale and a.handshake:
                self.stale.discard(a.name)
                events.append(Event("restored", a.name))
        self.stale &= {name} if name else set()
        self.last_active = name
        return events


class Activity:
    """Merkt sich aus den Live-Werten (/sys), wann ein Tunnel zuletzt gesendet hat – über die
    Neuabfragen beim Helfer hinweg, die jedes Mal ein frisches ``Status`` liefern."""

    def __init__(self) -> None:
        self.tx: dict[str, int] = {}
        self.sent_at: dict[str, float] = {}

    def update(self, live: dict[str, tuple[int, int]], now: float | None = None) -> None:
        now = now if now is not None else time.time()
        for name, (_rx, tx) in live.items():
            if name in self.tx and tx > self.tx[name]:
                self.sent_at[name] = now
            self.tx[name] = tx
        for name in list(self.tx):
            if name not in live:  # getrennt: beim nächsten Verbinden neu anfangen
                self.tx.pop(name, None)
                self.sent_at.pop(name, None)

    def apply(self, status: Status) -> None:
        for t in status.tunnels:
            t.sent_at = self.sent_at.get(t.name)


class RxWatch:
    """Hinweis aus /sys ohne root: Kommen 150 s lang keine Daten mehr herein, obwohl gesendet wird,
    lohnt sich eine Abfrage des Helfers (Handshake) – so muss der Hintergrund nicht ständig pkexec starten."""

    def __init__(self, quiet_after: float = 150) -> None:
        self.quiet_after = quiet_after
        self.last: tuple[str, int, int] | None = None
        self.rx_since = 0.0
        self.checked = False

    def suspicious(self, live: dict[str, tuple[int, int]], now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        if len(live) != 1:
            self.last = None
            return False
        name, (rx, tx) = next(iter(live.items()))
        if self.last is None or self.last[0] != name or rx != self.last[1]:
            self.last, self.rx_since, self.checked = (name, rx, tx), now, False
            return False
        sent = tx != self.last[2]
        self.last = (name, rx, tx)
        if sent and not self.checked and now - self.rx_since > self.quiet_after:
            self.checked = True
            return True
        return False


# ---------------------------------------------------------------- Import
def suggest_name(stem: str, existing=()) -> str:
    """Gültiger Tunnelname aus einem Dateinamen; vorhandene Namen bekommen „-2“, „-3“ …"""
    base = re.sub(r"[^a-zA-Z0-9_=+.-]", "_", stem).lstrip("-.")[:15] or "tunnel"
    if base in (".", ".."):
        base = "tunnel"
    name, n = base, 2
    while name in existing:
        suffix = f"-{n}"
        name = base[: 15 - len(suffix)] + suffix
        n += 1
    return name


def name_error(name: str) -> str:
    """Leer, wenn der Tunnelname gültig ist, sonst die Meldung."""
    try:
        wgconf.check_name(name)
    except wgconf.ConfError:
        return tr("1–15 Zeichen: A–Z, a–z, 0–9 und _ = + . -")
    return ""


def check_text(text: str) -> wgconf.TunnelConf:
    """Konfiguration aus dem Editor prüfen. „(verborgen)“ gilt als gültiger Schlüssel – der Helfer
    setzt beim Speichern den gespeicherten wieder ein. Fehler → ``conf.ConfError`` (ohne Werte)."""
    text = wgconf.decode(text.encode("utf-8"))
    return wgconf.parse(_HIDDEN_RE.sub(lambda m: m.group(1) + _DUMMY_KEY, text))


_HIDDEN_RE = re.compile(r"(?im)^(\s*(?:PrivateKey|PresharedKey)\s*=\s*)" + re.escape(wgconf.HIDDEN) + r"\s*$")


def reveal(masked: str, full: str) -> str:
    """Verborgene Schlüssel im Editor durch die echten ersetzen (Knopf „Schlüssel anzeigen“)."""
    return wgconf.unmask(masked, full)


def hide(text: str) -> str:
    return wgconf.mask(text)


# ---------------------------------------------------------------- Öffentliche IP, Export
def public_ip(timeout: float = 8, opener=urllib.request.urlopen) -> str:
    """Öffentliche IP über ``IP_SERVICE``. Fehler → OSError/ValueError."""
    req = urllib.request.Request(IP_SERVICE, headers={"User-Agent": "bonys-vpn"})
    with opener(req, timeout=timeout) as resp:
        data = json.loads(resp.read(256).decode("ascii", errors="replace"))
    return str(ipaddress.ip_address(str(data.get("ip", "")).strip()))


def write_private(path: Path, text: str) -> None:
    """Datei mit Rechten 600 atomar schreiben (für den Export mit privatem Schlüssel)."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
