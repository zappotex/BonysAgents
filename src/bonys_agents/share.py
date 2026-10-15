# SPDX-License-Identifier: GPL-3.0-or-later
"""Schulungen – gemeinsame Teile beider Editionen und der Teilnehmer: Kurs beitreten, Vorlage laden.

Den Server (Freigabe einer Vorlage im Netz) gibt es nur in „Bony's Agents Kursleiter“
(``bonys_agents.trainer.share_server``). Hier steht, was beide Seiten brauchen:

- **Protokoll**: Pfade, Kopfzeilen, Kurs-Protokoll-Version (``PROTOCOL``) und ihre Prüfung
  (``check_protocol``) – passen Kursleiter und Teilnehmer nicht zusammen, gibt es eine verständliche Meldung.
- **Code und Fingerabdruck**: Code vereinheitlichen, Fingerabdruck anzeigen und beim Verbinden prüfen
  (selbstsigniertes Zertifikat pro Freigabe, Teilnehmer brechen ab, wenn der Fingerabdruck nicht passt).
- **Teilnehmer**: ``fetch_info`` (Fingerabdruck und Manifest, vor dem Download) und ``download`` (mit Fortschritt,
  Fortsetzen per HTTP-Range nach einem Abbruch, Prüfsumme der ganzen Datei), danach Import wie bei einer Datei.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import http.client
import ipaddress
import json
import os
import re
import shutil
import socket
import ssl
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

from bonys_agents import __version__, bonysfile, mdns, storage

DEFAULT_PORT = 47110
DEFAULT_TIMEOUT_MIN = 120
DEFAULT_MAX_DOWNLOADS = 4
MAX_FAILS_PER_ADDR = 5
LOCK_SECONDS = 60
MAX_FAILS_TOTAL = 100
API = "/bonys/v1"
CODE_HEADER = "X-Bonys-Code"
CLIENT_HEADER = "X-Bonys-Client"
PROTOCOL_HEADER = "X-Bonys-Protocol"
VERSION_HEADER = "X-Bonys-Version"
CODE_LETTERS = "ABCDEFGHJKLMNPRSTUVWXYZ"  # ohne I, O, Q – gut vorlesbar
CHUNK = 1024 * 1024
WAITING_STALE = 30  # Sekunden ohne Nachfrage → nicht mehr in der Schlange

# Kurs-Protokoll zwischen Kursleiter und Teilnehmern (Freigabe, Vorführung, Hilfe-Modus). Nur erhöhen, wenn alte
# Gegenstellen nicht mehr mitkommen – dann melden beide Seiten verständlich, wer aktualisieren muss.
# Version 1: Bony's Agents 0.17 bis heute (fehlt die Angabe, ist es 1).
PROTOCOL = 1


class ShareError(RuntimeError):
    pass


class ProtocolMismatch(ShareError):
    """Kursleiter und Teilnehmer sprechen verschiedene Kurs-Protokolle (zu unterschiedliche Versionen)."""


def remote_protocol(value) -> int:
    """Protokoll-Angabe der Gegenstelle als Zahl – fehlt sie (ältere Version), ist es 1; Unsinn → 0."""
    if value in (None, ""):
        return 1
    try:
        return int(str(value).strip())
    except ValueError:
        return 0


def check_protocol(value, remote_version: str = "", *, we_are: str = "Teilnehmer", ours: int | None = None) -> None:
    """Passt das Kurs-Protokoll der Gegenstelle? Sonst ``ProtocolMismatch`` mit Hinweis, wer aktualisieren soll."""
    ours = PROTOCOL if ours is None else ours
    theirs = remote_protocol(value)
    if theirs == ours:
        return
    other = "Kursleiter" if we_are == "Teilnehmer" else "Teilnehmer"
    who = f"{other} (Bony's Agents {remote_version})" if remote_version else other
    newer = "Der " + (we_are if theirs > ours else other) + " sollte Bony's Agents aktualisieren."
    raise ProtocolMismatch(f"Kurs-Protokoll passt nicht: {who} nutzt Version {theirs or '?'}, dieses Programm "
                           f"(Bony's Agents {__version__}) Version {ours}. {newer} Danach erneut verbinden.")


def protocol_headers() -> dict:
    return {PROTOCOL_HEADER: str(PROTOCOL), VERSION_HEADER: __version__}


class WrongCode(ShareError):
    pass


class FingerprintMismatch(ShareError):
    pass


class IsPresentation(ShareError):
    """Unter der Adresse läuft keine Freigabe, sondern eine Live-Vorführung – im Browser öffnen."""

    def __init__(self, target: Target, title: str, fingerprint: str):
        super().__init__(f"Unter {target.netloc} läuft die Vorführung „{title}“ – sie öffnet sich im Browser.")
        self.target = target
        self.title = title
        self.fingerprint = fingerprint

    def url(self, name: str = "") -> str:
        frag = f"code={quote(self.target.code)}" + (f"&name={quote(name)}" if name else "")
        return f"https://{self.target.netloc}/#{frag}"


# ---------------------------------------------------------------- Code, Adresse, Fingerabdruck

def normalize_code(code: str) -> str:
    """Getippten Code vereinheitlichen: Groß-/Kleinschreibung, Leerzeichen und Bindestrich egal,
    „O“ im Zahlenteil ist eine Null, „0“ im Buchstabenteil ein O."""
    raw = re.sub(r"[^0-9A-Za-z]", "", code or "").upper()
    if len(raw) != 8:
        return raw
    return f"{raw[:4].replace('O', '0')}-{raw[4:].replace('0', 'O')}"


def format_fingerprint(fp: str) -> str:
    fp = re.sub(r"[^0-9A-Fa-f]", "", fp).upper()
    return ":".join(fp[i:i + 2] for i in range(0, len(fp), 2))


def short_fingerprint(fp: str) -> str:
    """Zum Vergleichen auf dem Bildschirm: die ersten 8 Bytes, in Vierergruppen."""
    fp = re.sub(r"[^0-9A-Fa-f]", "", fp).upper()[:16]
    return " ".join(fp[i:i + 4] for i in range(0, len(fp), 4))


@dataclass
class Target:
    host: str
    port: int = DEFAULT_PORT
    code: str = ""
    fingerprint: str = ""   # Hex ohne Trennzeichen, kleingeschrieben

    @property
    def netloc(self) -> str:
        return f"[{self.host}]:{self.port}" if ":" in self.host else f"{self.host}:{self.port}"


def parse_target(text: str, code: str = "", fingerprint: str = "") -> Target:
    """„192.168.1.5“, „pc.local:47110“, „[fd00::1]:47110“ oder ein Link bonys://ADRESSE:PORT?code=…&fp=…"""
    text = (text or "").strip()
    if not text:
        raise ValueError("Bitte die Adresse des Kursleiter-Rechners angeben.")
    if "://" not in text:
        text = "bonys://" + text
    u = urlsplit(text)
    if u.scheme not in ("bonys", "https") or not u.hostname:
        raise ValueError("Adresse nicht verstanden – z. B. 192.168.1.5:47110 oder bonys://…")
    q = parse_qs(u.query)
    try:
        port = u.port or DEFAULT_PORT
    except ValueError as e:
        raise ValueError("Ungültiger Port.") from e
    fp = re.sub(r"[^0-9A-Fa-f]", "", fingerprint or (q.get("fp") or [""])[0]).lower()
    if fp and len(fp) != 64:
        raise ValueError("Der Fingerabdruck muss 64 Hex-Zeichen haben (SHA-256).")
    return Target(host=u.hostname, port=port, code=normalize_code(code or (q.get("code") or [""])[0]),
                  fingerprint=fp)


def share_link(host: str, port: int, code: str, fingerprint: str) -> str:
    h = f"[{host}]" if ":" in host else host
    return f"bonys://{h}:{port}?code={quote(code)}&fp={fingerprint}"


# Virtuelle Netze dieses Rechners (Docker, VMs) – dort sitzt kein Teilnehmer
_VIRTUAL_IF = ("docker", "br-", "veth", "virbr", "vmnet", "vboxnet", "lxc", "lxd", "podman", "cni", "flannel")
_VPN_IF = ("wg", "tun", "tap", "tailscale", "utun", "zt", "ppp", "nordlynx", "proton", "mullvad", "bonys")
_vpn_addresses: set[str] = set()


def _is_tunnel(name: str, netmask: str | None) -> bool:
    """Tunnel-Schnittstelle (WireGuard, OpenVPN …) auch bei frei gewähltem Namen: Linux meldet sie ohne
    Hardware-Adresse (Typ 65534), WireGuard-Adressen haben meist die Maske /32."""
    if netmask == "255.255.255.255":
        return True
    try:
        return Path(f"/sys/class/net/{name}/type").read_text().strip() == "65534"
    except (OSError, ValueError):
        return False


def local_addresses() -> list[str]:
    """IPv4-Adressen dieses Rechners (ohne Loopback und Docker-/VM-Brücken), VPN-Adressen (z. B. WireGuard)
    eingeschlossen."""
    out: list[str] = []
    try:
        import psutil

        for name, addrs in psutil.net_if_addrs().items():
            low = name.lower()
            if low.startswith(_VIRTUAL_IF):
                continue
            for a in addrs:
                if a.family == socket.AF_INET and not a.address.startswith("127.") \
                        and not a.address.startswith("169.254."):
                    out.append(a.address)
                    if low.startswith(_VPN_IF) or "wireguard" in low or _is_tunnel(name, a.netmask):
                        _vpn_addresses.add(a.address)
    except Exception:  # noqa: BLE001 – dann wenigstens die Standard-Route
        pass
    if not out:
        with contextlib.suppress(OSError), socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))  # Testnetz – es wird nichts gesendet
            out.append(s.getsockname()[0])
    return list(dict.fromkeys(out))


def address_kind(addr: str) -> str:
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return ""
    if addr in _vpn_addresses or ip in ipaddress.ip_network("100.64.0.0/10"):
        return "VPN"
    return "LAN" if ip.is_private else "öffentlich"


def client_context() -> ssl.SSLContext:
    """Kein CA-Check (selbstsigniert) – stattdessen wird der Fingerabdruck verglichen (``_connect``)."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx



# ---------------------------------------------------------------- Teilnehmer: Client
@dataclass
class RemoteInfo:
    target: Target
    fingerprint: str
    manifest: dict
    file_name: str
    size: int
    sha256: str
    ends_in: int = 0


def _client_name() -> str:
    with contextlib.suppress(OSError):
        return socket.gethostname()[:40]
    return ""


def _connect(target: Target, timeout: float = 15) -> tuple[http.client.HTTPSConnection, str]:
    conn = http.client.HTTPSConnection(target.host, target.port, timeout=timeout, context=client_context())
    try:
        conn.connect()
    except (OSError, ssl.SSLError) as e:
        conn.close()
        raise ShareError(f"Keine Verbindung zu {target.netloc}: {e}. Läuft die Freigabe noch? Gleiches Netz bzw. "
                         "VPN verbunden? Lässt die Firewall des Kursleiter-Rechners den Port zu?") from e
    der = conn.sock.getpeercert(binary_form=True) or b""
    fp = hashlib.sha256(der).hexdigest()
    if target.fingerprint and not hmac.compare_digest(fp, target.fingerprint):
        conn.close()
        raise FingerprintMismatch("Der Fingerabdruck des Zertifikats passt nicht zur Freigabe – Verbindung "
                                  "abgebrochen. Falsche Adresse, oder jemand im Netz gibt sich als Kursleiter aus.")
    return conn, fp


def _headers(target: Target, extra: dict | None = None) -> dict:
    h = {CODE_HEADER: target.code, CLIENT_HEADER: _client_name(), "User-Agent": f"BonysAgents/{__version__}",
         **protocol_headers()}
    h.update(extra or {})
    return h


def _error(resp: http.client.HTTPResponse) -> ShareError:
    try:
        data = json.loads(resp.read().decode("utf-8"))
        data = data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        data = {}
    msg = str(data.get("error", ""))
    if resp.status == 403:
        return WrongCode(msg or "Falscher Freigabe-Code.")
    if resp.status == 426:
        try:
            check_protocol(data.get("protocol", 0), str(data.get("version", ""))[:20])
        except ProtocolMismatch as e:
            return e
    return ShareError(msg or f"Antwort {resp.status} vom Kursleiter-Rechner.")


def fetch_info(target: Target) -> RemoteInfo:
    """Fingerabdruck prüfen (bzw. ermitteln) und Inhalt der Freigabe holen – vor dem Download anzeigen."""
    if not target.code:
        raise WrongCode("Bitte den Freigabe-Code eingeben (z. B. 4711-BONY).")
    conn, fp = _connect(target)
    try:
        conn.request("GET", f"{API}/info", headers=_headers(target))
        resp = conn.getresponse()
        if resp.status != 200:
            raise _error(resp)
        data = json.loads(resp.read(4 * 1024 * 1024).decode("utf-8"))
    except (OSError, ValueError, http.client.HTTPException) as e:
        raise ShareError(f"Antwort des Kursleiter-Rechners nicht verstanden: {e}") from e
    finally:
        conn.close()
    if not isinstance(data, dict):
        raise ShareError("Antwort des Kursleiter-Rechners nicht verstanden.")
    check_protocol(data.get("protocol"), str(data.get("version", ""))[:20])
    if data.get("kind") == "present":
        raise IsPresentation(target, str(data.get("title", ""))[:60], fp)
    m = bonysfile.validate_manifest(data.get("manifest"))
    f = data.get("file") or {}
    if not isinstance(f.get("size"), int) or not re.fullmatch(r"[0-9a-f]{64}", str(f.get("sha256", ""))):
        raise ShareError("Antwort des Kursleiter-Rechners unvollständig.")
    name = bonysfile.default_filename(m["name"], m.get("version") or "1")
    return RemoteInfo(target=target, fingerprint=fp, manifest=m, file_name=name, size=f["size"],
                      sha256=f["sha256"], ends_in=int(data.get("ends_in") or 0))


def download(info: RemoteInfo, dest_dir: Path, progress: Callable[[str, float, str], None] | None = None,
             cancel: threading.Event | None = None, retry_wait: float = 5.0) -> Path:
    """Datei laden – setzt nach einem Abbruch fort (HTTP-Range), wartet in der Schlange, prüft die Prüfsumme.

    ``progress(phase, 0..1, Text)``, phase: „queue“ | „download“ | „verify“. Gibt die fertige .bonys-Datei zurück.
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    final = dest_dir / info.file_name
    part = final.with_name(final.name + ".teil")
    meta = final.with_name(final.name + ".teil.json")
    target = Target(info.target.host, info.target.port, info.target.code, info.fingerprint)
    want = {"sha256": info.sha256, "size": info.size}
    try:
        if json.loads(meta.read_text("utf-8")) != want:
            part.unlink(missing_ok=True)
    except (OSError, ValueError):
        part.unlink(missing_ok=True)
    meta.write_text(json.dumps(want), "utf-8")
    if shutil.disk_usage(dest_dir).free < info.size - (part.stat().st_size if part.exists() else 0) + 256 * 2**20:
        raise ShareError(f"Zu wenig Platz in {dest_dir} ({info.size / storage.GB:.1f} GB nötig).")

    def report(phase: str, frac: float, msg: str) -> None:
        if cancel is not None and cancel.is_set():
            raise bonysfile.Cancelled("Download abgebrochen – „Beitreten“ setzt später fort.")
        if progress:
            progress(phase, frac, msg)

    errors = 0
    while True:
        have = part.stat().st_size if part.exists() else 0
        if have >= info.size:
            break
        report("download", have / info.size, "Verbinde …")
        try:
            conn, _fp = _connect(target)
        except FingerprintMismatch:
            raise
        except ShareError:
            errors += 1
            if errors > 5:
                raise
            _sleep(retry_wait, report, "download", have / info.size, "Verbindung unterbrochen – neuer Versuch …")
            continue
        try:
            conn.request("GET", f"{API}/download", headers=_headers(target, {"Range": f"bytes={have}-"} if have
                                                                       else None))
            resp = conn.getresponse()
            if resp.status == 503:
                pos = json.loads(resp.read().decode("utf-8") or "{}").get("queue", "?")
                wait = float(resp.getheader("Retry-After") or retry_wait)
                _sleep(min(wait, 30), report, "queue", have / info.size,
                       f"Warteschlange: Platz {pos} – es laden gerade andere Teilnehmer …")
                continue
            if resp.status not in (200, 206):
                raise _error(resp)
            if resp.status == 200 and have:
                have = 0  # Server kann nicht fortsetzen → von vorn
            if (resp.getheader("X-Bonys-Sha256") or info.sha256) != info.sha256:
                raise ShareError("Die Freigabe hat sich geändert – bitte neu beitreten.")
            t0, d0 = time.monotonic(), have
            with part.open("r+b" if have else "wb") as out:
                out.seek(have)
                out.truncate()
                while chunk := resp.read(CHUNK):
                    out.write(chunk)
                    have += len(chunk)
                    elapsed = time.monotonic() - t0
                    rate = (have - d0) / elapsed if elapsed > 0.5 else 0
                    eta = f" · noch {_fmt_eta((info.size - have) / rate)}" if rate > 0 else ""
                    report("download", have / info.size,
                           f"Lade … {have / storage.GB:.2f} / {info.size / storage.GB:.2f} GB"
                           + (f" · {rate / 2**20:.1f} MB/s" if rate else "") + eta)
            errors = 0
        except (OSError, http.client.HTTPException, ssl.SSLError) as e:
            errors += 1
            if errors > 5:
                raise ShareError(f"Download immer wieder unterbrochen: {e}") from e
            _sleep(retry_wait, report, "download", have / info.size, "Verbindung unterbrochen – setze fort …")
        finally:
            conn.close()
    report("verify", 0, "Prüfe die Prüfsumme (SHA-256) …")
    sha = bonysfile._hash_file(part, lambda f: report("verify", f, f"Prüfe die Prüfsumme … {f * 100:.0f} %"))
    if sha != info.sha256:
        part.unlink(missing_ok=True)
        meta.unlink(missing_ok=True)
        raise ShareError("Prüfsumme stimmt nicht – die Datei wurde beschädigt. Bitte erneut beitreten.")
    final.unlink(missing_ok=True)
    os.replace(part, final)
    meta.unlink(missing_ok=True)
    report("verify", 1, f"Geladen und geprüft: {final.name}")
    return final


def _sleep(seconds: float, report, phase: str, frac: float, msg: str) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        report(phase, frac, msg)
        time.sleep(min(0.5, max(0.0, end - time.monotonic())))


def _fmt_eta(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} s"
    if seconds < 3600:
        return f"{seconds // 60} min"
    return f"{seconds // 3600} h {seconds % 3600 // 60:02d} min"


def discover(timeout: float = 2.5) -> list[mdns.Found]:
    """Freigaben im gleichen Netz finden (mDNS). In VPN-Netzen leer – dann Adresse eintippen."""
    try:
        return mdns.browse(timeout, local_addresses())
    except OSError:
        return []


def downloads_dir() -> Path:
    d = storage.data_dir() / "schulung"
    d.mkdir(parents=True, exist_ok=True)
    return d
