# SPDX-License-Identifier: GPL-3.0-or-later
"""X.509-Zertifikate ohne Fremdbibliothek: Ed25519 und ECDSA P-256.

- ``make_certificate``: selbstsigniertes Zertifikat für Freigabe und Vorführung (Kursleiter).
- ``make_control_tls``: kleine Zertifizierungsstelle je Start eines Agent-PCs – Server-Zertifikat für QEMU und
  Client-Zertifikat für Bony's Agents. Damit sind QEMU-Steuerung und Gast-Agent dort, wo es keine Unix-Sockets
  gibt (Windows), nur mit diesem Client-Zertifikat erreichbar – nicht aus dem Agent-PC über 10.0.2.2.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import ipaddress
import os
import re
import secrets
import ssl
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bonys_agents import signing

_ED25519 = bytes.fromhex("06032b6570")


def _der(tag: int, content: bytes) -> bytes:
    n = len(content)
    if n < 0x80:
        length = bytes([n])
    else:
        raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
        length = bytes([0x80 | len(raw)]) + raw
    return bytes([tag]) + length + content


def _seq(*parts: bytes) -> bytes:
    return _der(0x30, b"".join(parts))


def _time(t: datetime) -> bytes:
    return _der(0x17, t.strftime("%y%m%d%H%M%SZ").encode())


def _oid(dotted: str) -> bytes:
    parts = [int(x) for x in dotted.split(".")]
    out = bytes([40 * parts[0] + parts[1]])
    for n in parts[2:]:
        chunk = [n & 0x7F]
        while n > 0x7F:
            n >>= 7
            chunk.append(0x80 | (n & 0x7F))
        out += bytes(reversed(chunk))
    return _der(0x06, out)


def _int(n: int) -> bytes:
    return _der(0x02, n.to_bytes(n.bit_length() // 8 + 1, "big"))


# NIST P-256 (secp256r1) – Browser können kein Ed25519 im TLS-Zertifikat, deshalb ECDSA für die Seiten im Browser
_P = 2**256 - 2**224 + 2**192 + 2**96 - 1
_N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
_G = (0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
      0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5)


def _ec_add(a, b):
    if a is None:
        return b
    if b is None:
        return a
    if a[0] == b[0] and (a[1] + b[1]) % _P == 0:
        return None
    if a == b:
        m = (3 * a[0] * a[0] - 3) * pow(2 * a[1], -1, _P) % _P
    else:
        m = (b[1] - a[1]) * pow(b[0] - a[0], -1, _P) % _P
    x = (m * m - a[0] - b[0]) % _P
    return x, (m * (a[0] - x) - a[1]) % _P


def _ec_mul(k: int, point=_G):
    out = None
    while k:
        if k & 1:
            out = _ec_add(out, point)
        point = _ec_add(point, point)
        k >>= 1
    return out


def _ecdsa_sign(d: int, data: bytes) -> bytes:
    h = int.from_bytes(hashlib.sha256(data).digest(), "big")
    while True:
        k = secrets.randbelow(_N - 1) + 1
        r = _ec_mul(k)[0] % _N
        sig = pow(k, -1, _N) * (h + r * d) % _N
        if r and sig:
            return _seq(_int(r), _int(sig))


def make_certificate(common_name: str = "Bony's Agents Freigabe", days: int = 2, *, kind: str = "ed25519",
                     addresses: list[str] | tuple[str, ...] = (), names: list[str] | tuple[str, ...] = (),
                     ) -> tuple[bytes, bytes]:
    """Selbstsigniertes X.509-Zertifikat → (Zertifikat DER, privater Schlüssel PKCS#8 DER).

    ``kind``: „ed25519“ (Freigabe, Gegenstelle ist Bony's Agents) oder „ec“ (ECDSA P-256 – für Seiten, die im
    Browser geöffnet werden). ``addresses``/``names`` landen als subjectAltName im Zertifikat.
    """
    if kind == "ec":
        d = secrets.randbelow(_N - 1) + 1
        x, y = _ec_mul(d)
        point = b"\4" + x.to_bytes(32, "big") + y.to_bytes(32, "big")
        spki = _seq(_seq(_oid("1.2.840.10045.2.1"), _oid("1.2.840.10045.3.1.7")), _der(0x03, b"\0" + point))
        alg = _seq(_oid("1.2.840.10045.4.3.2"))

        def sign(data: bytes) -> bytes:
            return _ecdsa_sign(d, data)
        key = _seq(_der(0x02, b"\0"), _seq(_oid("1.2.840.10045.2.1"), _oid("1.2.840.10045.3.1.7")),
                   _der(0x04, _seq(_der(0x02, b"\1"), _der(0x04, d.to_bytes(32, "big")),
                                   _der(0xA1, _der(0x03, b"\0" + point)))))
    else:
        seed = secrets.token_bytes(32)
        alg = _seq(_ED25519)
        spki = _seq(alg, _der(0x03, b"\0" + signing.ed25519_public_key(seed)))

        def sign(data: bytes) -> bytes:
            return signing.ed25519_sign(seed, data)
        key = _seq(_der(0x02, b"\0"), alg, _der(0x04, _der(0x04, seed)))
    name = _seq(_der(0x31, _seq(_der(0x06, bytes.fromhex("550403")), _der(0x0C, common_name.encode()))))
    now = datetime.now(timezone.utc)
    serial = int.from_bytes(secrets.token_bytes(16), "big") >> 1 or 1
    alt = b""
    for a in addresses:
        with contextlib.suppress(ValueError):
            alt += _der(0x87, ipaddress.ip_address(a).packed)
    for n in names:
        if re.fullmatch(r"[A-Za-z0-9.-]{1,253}", n):
            alt += _der(0x82, n.encode())
    exts = _seq(_oid("2.5.29.37"), _der(0x04, _seq(_oid("1.3.6.1.5.5.7.3.1"))))  # nur Server-Authentifizierung
    if alt:
        exts += _seq(_oid("2.5.29.17"), _der(0x04, _seq(alt)))
    tbs = _seq(
        _der(0xA0, _der(0x02, b"\x02")),                                  # Version 3
        _der(0x02, serial.to_bytes((serial.bit_length() + 8) // 8, "big")),
        alg, name,
        _seq(_time(now - timedelta(hours=1)), _time(now + timedelta(days=days))),
        name,
        spki,
        _der(0xA3, _seq(exts)),
    )
    return _seq(tbs, alg, _der(0x03, b"\0" + sign(tbs))), key


def pem(label: str, der: bytes) -> str:
    b64 = base64.b64encode(der).decode()
    return f"-----BEGIN {label}-----\n" + "\n".join(b64[i:i + 64] for i in range(0, len(b64), 64)) \
        + f"\n-----END {label}-----\n"


def server_context(cert: bytes, key: bytes) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    with tempfile.TemporaryDirectory(prefix="bonys-share-") as d:
        cf, kf = Path(d) / "c.pem", Path(d) / "k.pem"
        fd = os.open(kf, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(pem("PRIVATE KEY", key))
        cf.write_text(pem("CERTIFICATE", cert))
        ctx.load_cert_chain(str(cf), str(kf))
    return ctx


# ---------------------------------------------------------------- Steuerkanäle eines Agent-PCs (QEMU, TLS)
CONTROL_FILES = ("ca-cert.pem", "server-cert.pem", "server-key.pem", "client-cert.pem", "client-key.pem",
                 "dh-params.pem")
# Öffentliche Standardgruppe ffdhe2048 (RFC 7919). Ohne diese Datei erzeugt QEMU beim Start eigene DH-Parameter –
# das dauert bis zu Sekunden, in denen die Steuerung noch nicht erreichbar ist.
FFDHE2048_PEM = """-----BEGIN DH PARAMETERS-----
MIIBCAKCAQEA//////////+t+FRYortKmq/cViAnPTzx2LnFg84tNpWp4TZBFGQz
+8yTnc4kmz75fS/jY2MMddj2gbICrsRhetPfHtXV/WVhJDP1H18GbtCFY2VVPe0a
87VXE15/V8k1mE8McODmi3fipona8+/och3xWKE2rec1MKzKT0g6eXq8CrGCsyT7
YdEIqUuyyOP7uWrat2DX9GgdT0Kj3jlN9K5W7edjcrsZCwenyO4KbXCeAvzhzffi
7MA0BM0oNC9hkXL+nOmFg/+OTxIy7vKBg8P+OxtMb61zO7X8vC7CIAXFjvGDfRaD
ssbzSibBsu/6iGtCOGEoXJf//////////wIBAg==
-----END DH PARAMETERS-----
"""
_BOOL_TRUE = b"\x01\x01\xff"


def _ec_key() -> tuple[int, bytes, bytes]:
    """Neuer P-256-Schlüssel → (geheime Zahl, SubjectPublicKeyInfo DER, privater Schlüssel PKCS#8 DER)."""
    d = secrets.randbelow(_N - 1) + 1
    x, y = _ec_mul(d)
    point = b"\4" + x.to_bytes(32, "big") + y.to_bytes(32, "big")
    alg = _seq(_oid("1.2.840.10045.2.1"), _oid("1.2.840.10045.3.1.7"))
    key = _seq(_der(0x02, b"\0"), alg, _der(0x04, _seq(_der(0x02, b"\1"), _der(0x04, d.to_bytes(32, "big")),
                                                       _der(0xA1, _der(0x03, b"\0" + point)))))
    return d, _seq(alg, _der(0x03, b"\0" + point)), key


def _ext(oid: str, value: bytes, critical: bool = False) -> bytes:
    return _seq(_oid(oid), *([_BOOL_TRUE] if critical else []), _der(0x04, value))


def _name(cn: str) -> bytes:
    return _seq(_der(0x31, _seq(_der(0x06, bytes.fromhex("550403")), _der(0x0C, cn.encode()))))


def _signed_cert(subject: str, spki: bytes, issuer: str, issuer_key: int, exts: list[bytes], days: int) -> bytes:
    alg = _seq(_oid("1.2.840.10045.4.3.2"))  # ecdsa-with-SHA256
    now = datetime.now(timezone.utc)
    serial = int.from_bytes(secrets.token_bytes(16), "big") >> 1 or 1
    tbs = _seq(
        _der(0xA0, _der(0x02, b"\x02")),
        _der(0x02, serial.to_bytes((serial.bit_length() + 8) // 8, "big")),
        alg, _name(issuer),
        _seq(_time(now - timedelta(hours=1)), _time(now + timedelta(days=days))),
        _name(subject), spki,
        _der(0xA3, _seq(*exts)),
    )
    return _seq(tbs, alg, _der(0x03, b"\0" + _ecdsa_sign(issuer_key, tbs)))


def _write_private(path: Path, text: str) -> None:
    path.unlink(missing_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as f:
        f.write(text)


def make_control_tls(folder: Path, days: int = 3650) -> None:
    """Neue Zertifizierungsstelle mit Server- und Client-Zertifikat in ``folder`` (Dateien: CONTROL_FILES).

    QEMU lädt ca-cert.pem, server-cert.pem und server-key.pem (``tls-creds-x509``, ``verify-peer=on``) und lässt
    nur Gegenstellen mit einem Zertifikat dieser Stelle herein. Der Schlüssel der Stelle wird nie gespeichert –
    es kann also niemand weitere Zertifikate ausstellen. Bei jedem Start neu.
    """
    folder.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        folder.chmod(0o700)
    ca_d, ca_spki, _ca_key = _ec_key()
    ca_name = f"Bony's Agents Steuerung {secrets.token_hex(4)}"
    ca = _signed_cert(ca_name, ca_spki, ca_name, ca_d, [
        _ext("2.5.29.19", _seq(_BOOL_TRUE), critical=True),       # basicConstraints: CA
        _ext("2.5.29.15", b"\x03\x02\x01\x06", critical=True),    # keyUsage: keyCertSign, cRLSign
    ], days)
    leaf_usage = _ext("2.5.29.15", b"\x03\x02\x05\xa0")           # keyUsage: digitalSignature, keyEncipherment
    s_d, s_spki, s_key = _ec_key()
    server = _signed_cert("QEMU", s_spki, ca_name, ca_d, [
        _ext("2.5.29.19", _seq(), critical=True), leaf_usage,
        _ext("2.5.29.37", _seq(_oid("1.3.6.1.5.5.7.3.1"))),       # serverAuth
        _ext("2.5.29.17", _seq(_der(0x87, bytes([127, 0, 0, 1])))),  # subjectAltName: 127.0.0.1
    ], days)
    c_d, c_spki, c_key = _ec_key()
    client = _signed_cert("Bony's Agents", c_spki, ca_name, ca_d, [
        _ext("2.5.29.19", _seq(), critical=True), leaf_usage,
        _ext("2.5.29.37", _seq(_oid("1.3.6.1.5.5.7.3.2"))),       # clientAuth
    ], days)
    for name, label, der in (("ca-cert.pem", "CERTIFICATE", ca), ("server-cert.pem", "CERTIFICATE", server),
                             ("server-key.pem", "PRIVATE KEY", s_key), ("client-cert.pem", "CERTIFICATE", client),
                             ("client-key.pem", "PRIVATE KEY", c_key)):
        _write_private(folder / name, pem(label, der))
    _write_private(folder / "dh-params.pem", FFDHE2048_PEM)


def control_client_context(folder: Path) -> ssl.SSLContext:
    """TLS-Kontext für Bony's Agents: prüft QEMU gegen die Stelle in ``folder`` und weist sich selbst aus."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_verify_locations(cafile=str(folder / "ca-cert.pem"))
    ctx.load_cert_chain(str(folder / "client-cert.pem"), str(folder / "client-key.pem"))
    return ctx
