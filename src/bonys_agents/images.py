# SPDX-License-Identifier: GPL-3.0-or-later
"""Lädt das offizielle Debian-Cloud-Image herunter und prüft die SHA512-Prüfsumme."""

from __future__ import annotations

import hashlib
import shutil
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from bonys_agents import __version__

ProgressFn = Callable[[int, int], None]  # (geladene Bytes, Gesamtbytes oder 0)

DEBIAN_BASE = "https://cloud.debian.org/images/cloud/trixie/latest"
USER_AGENT = f"bonys-agents/{__version__}"


@dataclass(frozen=True)
class BaseImage:
    name: str
    url: str
    sums_url: str
    filename: str
    hash_algo: str = "sha512"


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
) -> Path:
    """Gibt den Pfad zum geprüften Image zurück; lädt es bei Bedarf herunter.

    ``reuse_from``: andere Cache-Ordner – liegt dort schon ein passendes Image, wird es
    kopiert statt erneut heruntergeladen.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / image.filename
    want = expected_hash(image)

    if target.exists() and hash_of(target, image.hash_algo) == want:
        return target

    for other in reuse_from or []:
        cand = Path(other) / image.filename
        try:
            if cand.is_file() and hash_of(cand, image.hash_algo) == want:
                tmp = target.with_suffix(".part")
                shutil.copyfile(cand, tmp)
                shutil.move(str(tmp), str(target))
                return target
        except OSError:
            continue

    tmp = target.with_suffix(".part")
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
    shutil.move(str(tmp), str(target))
    return target
