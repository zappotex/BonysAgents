# SPDX-License-Identifier: GPL-3.0-or-later
"""Lädt das offizielle Cloud-Image (Debian oder Kali) herunter und prüft die Prüfsumme.

Kali liefert ein ``tar.xz`` mit einer Rohdatei (``disk.raw``): Sie wird nach der Prüfung entpackt und in
qcow2 umgewandelt. Im Cache liegt dann nur das qcow2, daneben eine ``.sha256``-Datei mit der Prüfsumme des
geprüften Archivs und der des qcow2 – so erkennt die App ein vorhandenes Abbild wieder.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import tarfile
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from bonys_agents import __version__
from bonys_agents.procutil import clean_env, no_window_flags

ProgressFn = Callable[[int, int], None]  # (geladene Bytes, Gesamtbytes oder 0)

DEBIAN_BASE = "https://cloud.debian.org/images/cloud/trixie/latest"
# Kali veröffentlicht für die Cloud-Abbilder nur Prüfsummen (keine Signatur) – Vertrauen über HTTPS zu kali.download
KALI_BASE = "https://kali.download/cloud-images/current"
USER_AGENT = f"bonys-agents/{__version__}"


@dataclass(frozen=True)
class BaseImage:
    name: str
    url: str
    sums_url: str
    filename: str
    hash_algo: str = "sha512"
    # Archiv (tar.xz) mit dieser Rohdatei darin – wird entpackt und nach qcow2 umgewandelt
    member: str = ""

    @property
    def cache_name(self) -> str:
        """Dateiname im Cache (bei einem Archiv das umgewandelte qcow2)."""
        return re.sub(r"\.tar\.xz$", ".qcow2", self.filename) if self.member else self.filename


def debian_image(arch: str) -> BaseImage:
    """Debian 13 „Trixie“, Variante *generic* (voller Kernel inkl. Grafiktreibern für den Desktop)."""
    deb_arch = {"x86_64": "amd64", "aarch64": "arm64"}[arch]
    filename = f"debian-13-generic-{deb_arch}.qcow2"
    return BaseImage(
        name=f"Debian 13 Trixie ({deb_arch})",
        url=f"{DEBIAN_BASE}/{filename}",
        sums_url=f"{DEBIAN_BASE}/SHA512SUMS",
        filename=filename,
    )


def kali_image(arch: str, sums_text: str | None = None) -> BaseImage:
    """Kali Linux, aktuelles Cloud-Abbild *genericcloud*. Der Dateiname enthält die Version und steht in SHA256SUMS."""
    kali_arch = {"x86_64": "amd64", "aarch64": "arm64"}[arch]
    sums_url = f"{KALI_BASE}/SHA256SUMS"
    if sums_text is None:
        with _open(sums_url) as r:
            sums_text = r.read().decode()
    pattern = re.compile(rf"^kali-linux-(\d{{4}}\.\d+[a-z]?)-cloud-genericcloud-{kali_arch}\.tar\.xz$")
    found = sorted((_version_key(m.group(1)), m.group(1), name) for name in _sum_names(sums_text)
                    if (m := pattern.match(name)))
    if not found:
        raise RuntimeError(f"Kein Kali-Cloud-Abbild für {kali_arch} auf kali.download gefunden")
    _, version, filename = found[-1]
    return BaseImage(
        name=f"Kali Linux {version} ({kali_arch})",
        url=f"{KALI_BASE}/{filename}",
        sums_url=sums_url,
        filename=filename,
        hash_algo="sha256",
        member="disk.raw",
    )


def base_image(distro: str, arch: str) -> BaseImage:
    from bonys_agents import distros

    return kali_image(arch) if distro == distros.KALI else debian_image(arch)


def _version_key(version: str) -> tuple[int, int, str]:
    """„2026.10“ nach „2026.2“; ein Buchstabe dahinter (Nachbesserung, z. B. „2026.2a“) nach der Version ohne."""
    year, rest = version.split(".", 1)
    num = re.match(r"\d+", rest).group(0)
    return int(year), int(num), rest[len(num):]


def _sum_names(text: str) -> list[str]:
    return [parts[1].lstrip("*") for line in text.splitlines() if len(parts := line.split()) == 2]


def _open(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(req, timeout=60)


def parse_sums(text: str, filename: str) -> str:
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == filename:
            return parts[0].lower()
    raise RuntimeError(f"Keine Prüfsumme für {filename} gefunden")


def expected_hash(image: BaseImage) -> str:
    with _open(image.sums_url) as r:
        return parse_sums(r.read().decode(), image.filename)


def hash_of(path: Path, algo: str) -> str:
    h = hashlib.new(algo)
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_image(
    image: BaseImage,
    cache_dir: Path,
    progress: ProgressFn | None = None,
    reuse_from: list[Path] | None = None,
    qemu_img: Path | None = None,
) -> Path:
    """Gibt den Pfad zum geprüften Image zurück; lädt es bei Bedarf herunter.

    ``reuse_from``: andere Cache-Ordner – liegt dort schon ein passendes Image, wird es
    kopiert statt erneut heruntergeladen. ``qemu_img``: nur für Archive (Umwandlung nach qcow2).
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / image.cache_name
    want = expected_hash(image)

    if _cached_ok(image, target, want):
        return target

    for other in reuse_from or []:
        cand = Path(other) / image.cache_name
        try:
            if cand.is_file() and _cached_ok(image, cand, want):
                tmp = target.with_suffix(".part")
                shutil.copyfile(cand, tmp)
                shutil.move(str(tmp), str(target))
                if image.member:
                    shutil.copyfile(_marker(cand), _marker(target))
                return target
        except OSError:
            continue

    download = cache_dir / image.filename if image.member else target
    tmp = download.with_suffix(download.suffix + ".part") if image.member else target.with_suffix(".part")
    h = hashlib.new(image.hash_algo)
    with _open(image.url) as r, tmp.open("wb") as out:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while chunk := r.read(1024 * 1024):
            out.write(chunk)
            h.update(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)

    if h.hexdigest() != want:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("Prüfsumme des Images stimmt nicht – Download beschädigt, bitte erneut versuchen")
    if not image.member:
        shutil.move(str(tmp), str(target))
        return target
    if qemu_img is None:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("qemu-img fehlt – das Abbild kann nicht umgewandelt werden")
    raw = cache_dir / (image.cache_name + ".raw")
    try:
        extract_member(tmp, image.member, raw)
        part = target.with_suffix(".part")
        subprocess.run([str(qemu_img), "convert", "-f", "raw", "-O", "qcow2", str(raw), str(part)],
                       check=True, capture_output=True, timeout=1800, creationflags=no_window_flags(),
                       env=clean_env())
        shutil.move(str(part), str(target))
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Abbild konnte nicht umgewandelt werden: {e.stderr.decode(errors='replace')[-300:]}") \
            from None
    finally:
        tmp.unlink(missing_ok=True)
        raw.unlink(missing_ok=True)
        target.with_suffix(".part").unlink(missing_ok=True)
    _marker(target).write_text(f"{want} {hash_of(target, 'sha256')}\n")
    return target


def _marker(path: Path) -> Path:
    return path.with_name(path.name + ".sha256")


def _cached_ok(image: BaseImage, path: Path, want: str) -> bool:
    """Liegt unter ``path`` schon das geprüfte Abbild? Bei Archiven über die Marker-Datei daneben."""
    if not path.is_file():
        return False
    if not image.member:
        return hash_of(path, image.hash_algo) == want
    try:
        archive_hash, qcow_hash = _marker(path).read_text().split()
    except (OSError, ValueError):
        return False
    return archive_hash == want and hash_of(path, "sha256") == qcow_hash


def extract_member(archive: Path, member: str, dest: Path) -> None:
    """Eine einzelne reguläre Datei aus einem tar.xz holen – Nullblöcke werden übersprungen (Datei bleibt dünn)."""
    with tarfile.open(archive, mode="r:xz") as tar:
        for info in tar:
            if info.name.lstrip("./") != member:
                continue
            if not info.isfile():
                raise RuntimeError(f"{member} im Archiv ist keine normale Datei")
            src = tar.extractfile(info)
            assert src is not None
            zero = bytes(1024 * 1024)
            with dest.open("wb") as out:
                while chunk := src.read(len(zero)):
                    if chunk == zero[:len(chunk)]:
                        out.seek(len(chunk), 1)
                    else:
                        out.write(chunk)
                out.truncate(info.size)
            return
    raise RuntimeError(f"{member} fehlt im Archiv {archive.name}")
