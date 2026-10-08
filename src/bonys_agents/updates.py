# SPDX-License-Identifier: GPL-3.0-or-later
"""Nach neuen Versionen suchen und Updates sicher installieren.

- Quelle: GitHub-Releases von ``bonys_agents.UPDATE_REPO`` (API ohne Token, mit Zeitlimit).
  Ist das Repository nicht erreichbar, gibt es still „keine Updates“ – nie einen Absturz.
- Sicherheit: nur HTTPS und nur Dateien aus dem offiziellen Release. Die Pipeline legt jedem
  Release die Datei SHA256SUMS samt minisign-Signatur bei; vor jeder Installation werden
  Signatur (fest eingebauter öffentlicher Schlüssel) und Prüfsumme geprüft.
- Installiert wird nie ohne Zustimmung: die Aufrufer (App, Kommandozeile) fragen vorher.
- Linux: Updates kommen über die eigene APT-Paketquelle (Aktualisierungsverwaltung) – oder,
  solange sie fehlt, als geprüftes .deb. Windows: geprüfte Setup.exe. macOS: geprüfte .dmg passend
  zum Chip (Apple-Chip oder Intel) – sie öffnet sich im Finder, die App zieht man dann in „Programme“.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from bonys_agents import UPDATE_PUBLIC_KEY, UPDATE_REPO, __version__, procutil, signing, storage
from bonys_agents.procutil import clean_env, no_window_flags

API_URL = "https://api.github.com"
TIMEOUT = 10                 # Sekunden für die Versionsabfrage
CHECK_INTERVAL = 24 * 3600   # automatische Suche höchstens einmal pro Tag
USER_AGENT = f"bonys-agents/{__version__}"
SUMS_NAME = "SHA256SUMS"
SIG_NAME = "SHA256SUMS.minisig"
APT_SOURCES_FILE = Path("/etc/apt/sources.list.d/bonys-agents.sources")
APT_KEYRING = "/usr/share/keyrings/bonys-agents.gpg"
PACKAGE = "bonys-agents"
_REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9._-]+$")

Opener = Callable[..., object]  # wie urllib.request.urlopen (für Tests austauschbar)


class UpdateError(RuntimeError):
    """Update nicht möglich – mit verständlicher Meldung (z. B. Signatur oder Prüfsumme falsch)."""


# ---------------------------------------------------------------- Versionen (Semantic Versioning)
_SEMVER = re.compile(r"^[vV]?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$")


@dataclass(frozen=True)
class Version:
    major: int
    minor: int
    patch: int
    pre: tuple[str, ...] = ()

    @classmethod
    def parse(cls, text: str) -> Version | None:
        m = _SEMVER.match(text.strip())
        if not m:
            return None
        pre = tuple(m.group(4).split(".")) if m.group(4) else ()
        return cls(int(m.group(1)), int(m.group(2)), int(m.group(3)), pre)

    @property
    def prerelease(self) -> bool:
        return bool(self.pre)

    def key(self) -> tuple:
        # Vorversion < Version; Bezeichner: Zahlen numerisch und vor Text; kürzere Liste zuerst.
        pre_key = tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in self.pre)
        return (self.major, self.minor, self.patch, 0 if self.pre else 1, pre_key)

    def __lt__(self, other: Version) -> bool:
        return self.key() < other.key()

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}" + (f"-{'.'.join(self.pre)}" if self.pre else "")


def is_newer(candidate: str, current: str) -> bool:
    a, b = Version.parse(candidate), Version.parse(current)
    return bool(a and b and b < a)


# ---------------------------------------------------------------- Release-Daten
@dataclass(frozen=True)
class Asset:
    name: str
    url: str
    size: int = 0


@dataclass
class UpdateInfo:
    version: str
    tag: str
    title: str = ""
    notes: str = ""
    html_url: str = ""
    prerelease: bool = False
    assets: dict[str, Asset] = field(default_factory=dict)


def _request(url: str, accept: str = "application/vnd.github+json") -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})


def _get_json(url: str, timeout: float, opener: Opener):
    with opener(_request(url), timeout=timeout) as r:
        return json.loads(r.read(4 * 1024 * 1024).decode("utf-8"))


def _release(data: dict) -> UpdateInfo | None:
    if not isinstance(data, dict) or data.get("draft"):
        return None
    tag = str(data.get("tag_name") or "")
    version = Version.parse(tag)
    if version is None:
        return None
    assets = {}
    for a in data.get("assets") or []:
        if isinstance(a, dict) and a.get("name") and a.get("browser_download_url"):
            assets[a["name"]] = Asset(a["name"], a["browser_download_url"], int(a.get("size") or 0))
    return UpdateInfo(
        version=str(version), tag=tag, title=str(data.get("name") or tag), notes=str(data.get("body") or ""),
        html_url=str(data.get("html_url") or ""), prerelease=bool(data.get("prerelease")) or version.prerelease,
        assets=assets,
    )


def fetch_latest(repo: str = UPDATE_REPO, prereleases: bool = False, timeout: float = TIMEOUT,
                 opener: Opener | None = None) -> UpdateInfo | None:
    """Neueste Version laut GitHub. Wirft Netzwerk-/Formatfehler weiter (siehe ``check``)."""
    if not _REPO_RE.match(repo):
        return None
    opener = opener or urllib.request.urlopen
    if not prereleases:
        return _release(_get_json(f"{API_URL}/repos/{repo}/releases/latest", timeout, opener))
    releases = [_release(d) for d in _get_json(f"{API_URL}/repos/{repo}/releases?per_page=30", timeout, opener)]
    releases = [r for r in releases if r is not None]
    return max(releases, key=lambda r: Version.parse(r.version).key(), default=None)


def check(current: str = __version__, repo: str = UPDATE_REPO, prereleases: bool = False,
          skip_version: str | None = None, timeout: float = TIMEOUT, opener: Opener | None = None) -> UpdateInfo | None:
    """Gibt es eine neuere Version? None = keine (auch wenn GitHub nicht erreichbar ist)."""
    try:
        info = fetch_latest(repo, prereleases, timeout, opener)
    except Exception:  # noqa: BLE001 – Update-Suche darf nie stören: still „keine Updates“
        return None
    if info is None or not is_newer(info.version, current):
        return None
    if info.prerelease and not prereleases:
        return None
    if skip_version and info.version == skip_version:
        return None
    return info


def release_page(repo: str = UPDATE_REPO) -> str:
    return f"https://github.com/{repo}/releases/latest"


# ---------------------------------------------------------------- Einstellungen
def settings() -> dict:
    s = storage.load_settings()
    return {
        "auto": bool(s.get("update_auto_check", True)),
        "prereleases": bool(s.get("update_prereleases", False)),
        "skip": s.get("update_skip_version") or None,
        "last": float(s.get("update_last_check") or 0),
    }


def set_setting(key: str, value) -> None:
    names = {"auto": "update_auto_check", "prereleases": "update_prereleases", "skip": "update_skip_version",
             "last": "update_last_check"}
    s = storage.load_settings()
    s[names[key]] = value
    storage.save_settings(s)


def auto_check_due(now: float | None = None) -> bool:
    """Automatische Suche eingeschaltet und die letzte länger als einen Tag her?"""
    st = settings()
    now = time.time() if now is None else now
    return st["auto"] and not 0 <= now - st["last"] < CHECK_INTERVAL


def check_now(manual: bool = False, opener: Opener | None = None) -> UpdateInfo | None:
    """Suche mit den Einstellungen des Nutzers und Zeitpunkt merken. ``manual``: „überspringen“ ignorieren."""
    st = settings()
    info = check(prereleases=st["prereleases"], skip_version=None if manual else st["skip"], opener=opener)
    set_setting("last", time.time())
    return info


# ---------------------------------------------------------------- Herunterladen und prüfen
def _official(url: str, repo: str) -> bool:
    return url.lower().startswith(f"https://github.com/{repo.lower()}/releases/download/")


def _open_https(url: str, timeout: float, opener: Opener):
    r = opener(_request(url, accept="application/octet-stream"), timeout=timeout)
    final = r.geturl() if hasattr(r, "geturl") else url
    if not str(final).startswith("https://"):
        r.close()
        raise UpdateError("Download nicht über HTTPS – abgebrochen.")
    return r


def _fetch_small(url: str, opener: Opener, limit: int = 1024 * 1024) -> bytes:
    with _open_https(url, 30, opener) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise UpdateError("Unerwartet große Prüfsummen-Datei – abgebrochen.")
    return data


def parse_sums(text: str, filename: str) -> str:
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == filename and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            return parts[0].lower()
    raise UpdateError(f"{filename} steht nicht in der signierten Prüfsummen-Liste – abgebrochen.")


def download_verified(info: UpdateInfo, asset_name: str, dest_dir: Path, *, repo: str = UPDATE_REPO,
                      public_key: str = UPDATE_PUBLIC_KEY, opener: Opener | None = None,
                      progress: Callable[[int, int], None] | None = None) -> Path:
    """Datei aus dem Release laden – nur mit gültiger Signatur und passender Prüfsumme."""
    opener = opener or urllib.request.urlopen
    if not public_key.strip():
        raise UpdateError("In dieser Version ist kein Signaturschlüssel für Updates hinterlegt – "
                          f"bitte die neue Version selbst von {release_page(repo)} laden.")
    asset = info.assets.get(asset_name)
    if asset is None:
        raise UpdateError(f"Das Release {info.tag} enthält keine Datei {asset_name}.")
    sums, sig = info.assets.get(SUMS_NAME), info.assets.get(SIG_NAME)
    if sums is None or sig is None:
        raise UpdateError(f"Das Release {info.tag} ist nicht signiert ({SUMS_NAME}/{SIG_NAME} fehlen) – "
                          "aus Sicherheitsgründen wird nichts installiert.")
    for a in (asset, sums, sig):
        if not _official(a.url, repo):
            raise UpdateError(f"{a.name} stammt nicht aus dem offiziellen Release – abgebrochen.")
    try:
        sums_data = _fetch_small(sums.url, opener)
        sig_text = _fetch_small(sig.url, opener).decode("utf-8", errors="replace")
    except (OSError, urllib.error.URLError) as e:
        raise UpdateError(f"Download fehlgeschlagen: {e}") from None
    try:
        trusted = signing.verify(sums_data, sig_text, public_key)
    except signing.SignatureError as e:
        raise UpdateError(f"Signaturprüfung fehlgeschlagen: {e} Das Update wird nicht installiert.") from None
    # Schutz vor echten, aber alten Dateien: die Signatur muss genau diese Version nennen.
    if not {info.tag, info.version, f"v{info.version}"} & set(trusted.split()):
        raise UpdateError(f"Die Signatur gehört zu einer anderen Version („{trusted}“) – abgebrochen.")
    want = parse_sums(sums_data.decode("utf-8", errors="replace"), asset_name)

    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / asset_name
    part = dest_dir / (asset_name + ".part")
    h = hashlib.sha256()
    try:
        with _open_https(asset.url, 60, opener) as r, part.open("wb") as out:
            total = int(getattr(r, "headers", {}).get("Content-Length") or asset.size or 0)
            done = 0
            while chunk := r.read(1024 * 1024):
                out.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    except (OSError, urllib.error.URLError) as e:
        part.unlink(missing_ok=True)
        raise UpdateError(f"Download fehlgeschlagen: {e}") from None
    if h.hexdigest() != want:
        part.unlink(missing_ok=True)
        raise UpdateError(f"Prüfsumme von {asset_name} stimmt nicht – Datei beschädigt oder verändert. "
                          "Das Update wird nicht installiert.")
    os.replace(part, target)
    target.chmod(0o644)  # apt liest lokale .deb als Benutzer _apt
    return target


# ---------------------------------------------------------------- je Betriebssystem
# Namensteil der macOS-Pakete je Chip (siehe .github/workflows/release.yml)
MAC_DMG_FLAVOR = {"aarch64": "applesilicon", "x86_64": "intel"}


def asset_for(version: str, host_os: str, arch: str) -> str | None:
    """Name der passenden Datei im Release – None, wenn es für dieses System keine gibt."""
    if host_os == "linux":
        return f"{PACKAGE}_{version}_{'arm64' if arch == 'aarch64' else 'amd64'}.deb"
    if host_os == "windows":
        return f"BonysAgents-Setup-{version}.exe"
    if host_os == "macos":
        return f"BonysAgents-{version}-macos-{MAC_DMG_FLAVOR[arch]}.dmg"
    return None


def pages_url(repo: str = UPDATE_REPO) -> str:
    """Adresse der APT-Paketquelle auf GitHub Pages des Repositorys."""
    owner, name = repo.split("/", 1)
    return f"https://{owner.lower()}.github.io/{name}/apt/"


def apt_sources_text(repo: str = UPDATE_REPO, keyring: str = APT_KEYRING) -> str:
    """Paketquelle im deb822-Format für /etc/apt/sources.list.d/bonys-agents.sources."""
    return "\n".join([
        "# Bony's Agents – Updates über die Aktualisierungsverwaltung (Mint, Ubuntu, Debian).",
        "# Angelegt vom Paket bonys-agents, entfernt bei „apt purge bonys-agents“.",
        "# Abschalten: die Zeile „Enabled: no“ ergänzen – sie bleibt bei Updates erhalten.",
        "Types: deb",
        f"URIs: {pages_url(repo)}",
        "Suites: stable",
        "Components: main",
        f"Signed-By: {keyring}",
        "",
    ])


def apt_source_configured(path: Path = APT_SOURCES_FILE) -> bool:
    try:
        text = path.read_text("utf-8")
    except OSError:
        return False
    return "URIs:" in text and not re.search(r"^\s*Enabled:\s*no\b", text, re.M | re.I)


def apt_upgrade_script() -> str:
    return "\n".join([
        "set -e",
        "export DEBIAN_FRONTEND=noninteractive",
        'apt-get update || echo "Warnung: Nicht alle Paketquellen ließen sich aktualisieren."',
        f"apt-get install -y --only-upgrade {PACKAGE}",
        "",
    ])


def deb_install_script(deb: Path) -> str:
    return f"set -e\nexport DEBIAN_FRONTEND=noninteractive\napt-get install -y {shlex.quote(str(deb))}\n"


def installed_deb_version() -> str | None:
    try:
        r = subprocess.run(["dpkg-query", "-W", "-f=${Version}", PACKAGE], capture_output=True, text=True,
                           timeout=15, env=clean_env())
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def can_self_update(host_os: str) -> bool:
    """Automatisch aktualisieren geht nur im fertigen Programm (.deb, Setup.exe bzw. .app)."""
    if host_os == "linux":
        return procutil.is_frozen() and installed_deb_version() is not None
    return host_os in ("windows", "macos") and procutil.is_frozen()


def download_dir() -> Path:
    d = Path(tempfile.mkdtemp(prefix="bonys-agents-update-"))
    d.chmod(0o755)  # apt (Benutzer _apt) muss die Datei lesen können
    return d


def install_linux(info: UpdateInfo, arch: str, gui: bool, log: Callable[[str], None],
                  opener: Opener | None = None) -> None:
    """Über die Paketquelle aktualisieren – ohne Paketquelle (oder wenn sie nichts bringt) per .deb."""
    from bonys_agents import deps

    if apt_source_configured():
        log("Aktualisiere über die Paketquelle von Bony's Agents (fragt nach deinem Passwort) …")
        if deps._run(deps._elevate_linux(apt_upgrade_script(), gui), log) == 0:
            now = installed_deb_version()
            if now and not is_newer(info.version, now.split("-")[0]):
                return
            log(f"Die Paketquelle bietet {info.version} noch nicht an – lade das Paket direkt aus dem Release.")
        else:
            log("Aktualisierung über die Paketquelle nicht möglich – lade das Paket direkt aus dem Release.")
    name = asset_for(info.version, "linux", arch)
    log(f"Lade {name} und prüfe Signatur und Prüfsumme …")
    deb = download_verified(info, name, download_dir(), opener=opener)
    log("Signatur und Prüfsumme in Ordnung. Installiere (fragt nach deinem Passwort) …")
    rc = deps._run(deps._elevate_linux(deb_install_script(deb), gui), log)
    if rc != 0:
        raise UpdateError(f"Installation abgebrochen oder fehlgeschlagen (Code {rc}).")


def install_windows(info: UpdateInfo, log: Callable[[str], None], opener: Opener | None = None) -> None:
    """Setup.exe laden, prüfen und still starten. Danach muss sich die App sofort beenden."""
    name = asset_for(info.version, "windows", "x86_64")
    log(f"Lade {name} und prüfe Signatur und Prüfsumme …")
    setup = download_verified(info, name, Path(tempfile.mkdtemp(prefix="bonys-agents-update-")), opener=opener)
    log("Signatur und Prüfsumme in Ordnung. Starte die Installation …")
    # /RELAUNCH=1: der Installer startet die App danach wieder (siehe bonys-agents.iss)
    subprocess.Popen([str(setup), "/SILENT", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS", "/RELAUNCH=1"],
                     env=clean_env(), creationflags=0x00000008 | no_window_flags())  # DETACHED_PROCESS


def install_macos(info: UpdateInfo, arch: str, log: Callable[[str], None], opener: Opener | None = None,
                  dest_dir: Path | None = None, open_dmg: bool = True) -> Path:
    """Die .dmg für diesen Chip laden, prüfen und im Finder öffnen.

    Die App ersetzt man dann selbst: Bony's Agents beenden und aus dem Fenster in „Programme“ ziehen.
    Selbst geladene Dateien bekommen keine Quarantäne-Markierung – Gatekeeper fragt also nicht erneut.
    """
    name = asset_for(info.version, "macos", arch)
    downloads = Path.home() / "Downloads"
    dest = dest_dir or (downloads if downloads.is_dir() else Path(tempfile.mkdtemp(prefix="bonys-agents-update-")))
    log(f"Lade {name} und prüfe Signatur und Prüfsumme …")
    dmg = download_verified(info, name, dest, opener=opener)
    log(f"Signatur und Prüfsumme in Ordnung: {dmg}")
    if open_dmg:
        subprocess.Popen(["open", str(dmg)], env=clean_env(), stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log("Das Fenster mit der neuen Version öffnet sich im Finder.")
    return dmg


def restart_command() -> list[str]:
    """Befehl, der die Desktop-App neu startet (nach einem Update)."""
    if procutil.is_frozen():
        exe = Path(sys.executable)
        gui = exe.with_name("BonysAgents" + exe.suffix)
        return [str(gui if gui.exists() else exe)]
    return [sys.executable, "-m", "bonys_agents.gui.app"]
