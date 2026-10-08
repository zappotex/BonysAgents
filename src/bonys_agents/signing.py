# SPDX-License-Identifier: GPL-3.0-or-later
"""Signaturen der Updates prüfen – minisign-Format, Ed25519, ohne zusätzliche Abhängigkeiten.

Die Release-Pipeline signiert die Datei SHA256SUMS mit minisign; der öffentliche Schlüssel
steckt fest im Programm (``bonys_agents.UPDATE_PUBLIC_KEY``). Ed25519 ist hier nach der
Referenz-Implementierung aus RFC 8032 (Abschnitt 6) nachgebaut: langsam, aber für eine kleine
Datei je Update völlig ausreichend – und unter Windows, macOS und Linux gleich.

Format (https://jedisct1.github.io/minisign/):
  öffentlicher Schlüssel  base64( "Ed" | key_id[8] | pk[32] )
  Signaturdatei           untrusted comment: …
                          base64( "ED" | key_id[8] | sig[64] )     sig über BLAKE2b-512(Datei)
                          trusted comment: …                        („Ed“ = über die Datei selbst)
                          base64( global_sig[64] )                  über sig | trusted comment
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass


class SignatureError(ValueError):
    """Signatur fehlt, passt nicht zum Schlüssel oder ist ungültig."""


# ---------------------------------------------------------------- Ed25519 (RFC 8032)
_P = 2**255 - 19
_Q = 2**252 + 27742317777372353535851937790883648493


def _inv(x: int) -> int:
    return pow(x, _P - 2, _P)


_D = -121665 * _inv(121666) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)


def _sha512_modq(data: bytes) -> int:
    return int.from_bytes(hashlib.sha512(data).digest(), "little") % _Q


def _add(p1, p2):
    a = (p1[1] - p1[0]) * (p2[1] - p2[0]) % _P
    b = (p1[1] + p1[0]) * (p2[1] + p2[0]) % _P
    c = 2 * p1[3] * p2[3] * _D % _P
    d = 2 * p1[2] * p2[2] % _P
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f, g * h, f * g, e * h)


def _mul(s: int, p):
    q = (0, 1, 1, 0)  # neutrales Element
    while s > 0:
        if s & 1:
            q = _add(q, p)
        p = _add(p, p)
        s >>= 1
    return q


def _equal(p1, p2) -> bool:
    return ((p1[0] * p2[2] - p2[0] * p1[2]) % _P == 0
            and (p1[1] * p2[2] - p2[1] * p1[2]) % _P == 0)


def _recover_x(y: int, sign: int) -> int | None:
    if y >= _P:
        return None
    x2 = (y * y - 1) * _inv(_D * y * y + 1)
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _SQRT_M1 % _P
    if (x * x - x2) % _P != 0:
        return None
    if (x & 1) != sign:
        x = _P - x
    return x


_GY = 4 * _inv(5) % _P
_GX = _recover_x(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % _P)


def _compress(p) -> bytes:
    zinv = _inv(p[2])
    x, y = p[0] * zinv % _P, p[1] * zinv % _P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _decompress(s: bytes):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    return None if x is None else (x, y, 1, x * y % _P)


def _expand(secret: bytes) -> tuple[int, bytes]:
    if len(secret) != 32:
        raise ValueError("Ed25519-Geheimschlüssel muss 32 Bytes lang sein")
    h = hashlib.sha512(secret).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def ed25519_public_key(secret: bytes) -> bytes:
    return _compress(_mul(_expand(secret)[0], _G))


def ed25519_sign(secret: bytes, msg: bytes) -> bytes:
    a, prefix = _expand(secret)
    pub = _compress(_mul(a, _G))
    r = _sha512_modq(prefix + msg)
    rs = _compress(_mul(r, _G))
    h = _sha512_modq(rs + pub + msg)
    return rs + int.to_bytes((r + h * a) % _Q, 32, "little")


def ed25519_verify(public: bytes, msg: bytes, signature: bytes) -> bool:
    if len(public) != 32 or len(signature) != 64:
        return False
    a = _decompress(public)
    r = _decompress(signature[:32])
    if a is None or r is None:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= _Q:
        return False
    h = _sha512_modq(signature[:32] + public + msg)
    return _equal(_mul(s, _G), _add(r, _mul(h, a)))


# ---------------------------------------------------------------- minisign
@dataclass(frozen=True)
class PublicKey:
    key_id: bytes
    key: bytes

    @classmethod
    def parse(cls, text: str) -> PublicKey:
        """Öffentlicher Schlüssel als Zeile „RW…“ oder ganze .pub-Datei (mit Kommentarzeile)."""
        lines = [line.strip() for line in text.strip().splitlines()
                 if line.strip() and not line.startswith("untrusted comment:")]
        if not lines:
            raise SignatureError("Kein öffentlicher Schlüssel für Updates hinterlegt.")
        try:
            raw = base64.b64decode(lines[-1], validate=True)
        except ValueError:
            raise SignatureError("Öffentlicher Schlüssel ist kein gültiges base64.") from None
        if len(raw) != 42 or raw[:2] != b"Ed":
            raise SignatureError("Öffentlicher Schlüssel hat nicht das minisign-Format (Ed25519).")
        return cls(raw[2:10], raw[10:])

    def text(self) -> str:
        return base64.b64encode(b"Ed" + self.key_id + self.key).decode()


def verify(data: bytes, signature_file: str, public_key: str | PublicKey) -> str:
    """Prüft eine minisign-Signatur. Gibt den vertrauenswürdigen Kommentar zurück, sonst SignatureError."""
    pk = public_key if isinstance(public_key, PublicKey) else PublicKey.parse(public_key)
    lines = [line.rstrip("\r") for line in signature_file.strip().splitlines()]
    if len(lines) < 4 or not lines[2].startswith("trusted comment: "):
        raise SignatureError("Signaturdatei ist unvollständig oder beschädigt.")
    try:
        sig_raw = base64.b64decode(lines[1], validate=True)
        global_sig = base64.b64decode(lines[3], validate=True)
    except ValueError:
        raise SignatureError("Signaturdatei ist beschädigt (kein base64).") from None
    if len(sig_raw) != 74 or len(global_sig) != 64:
        raise SignatureError("Signaturdatei hat nicht das minisign-Format.")
    algo, key_id, sig = sig_raw[:2], sig_raw[2:10], sig_raw[10:]
    if key_id != pk.key_id:
        raise SignatureError("Die Signatur stammt nicht vom offiziellen Schlüssel von Bony's Agents.")
    if algo == b"ED":
        message = hashlib.blake2b(data, digest_size=64).digest()
    elif algo == b"Ed":
        message = data
    else:
        raise SignatureError("Unbekanntes Signaturverfahren.")
    if not ed25519_verify(pk.key, message, sig):
        raise SignatureError("Signatur ungültig – die Datei wurde verändert oder ist beschädigt.")
    trusted = lines[2][len("trusted comment: "):]
    if not ed25519_verify(pk.key, sig + trusted.encode("utf-8"), global_sig):
        raise SignatureError("Signatur ungültig (vertrauenswürdiger Kommentar wurde verändert).")
    return trusted


def sign(data: bytes, secret: bytes, key_id: bytes, trusted_comment: str,
         untrusted_comment: str = "signature from Bony's Agents") -> str:
    """minisign-Signatur („ED“, vorgehasht) erzeugen – für Tests und eigene Werkzeuge."""
    sig = ed25519_sign(secret, hashlib.blake2b(data, digest_size=64).digest())
    global_sig = ed25519_sign(secret, sig + trusted_comment.encode("utf-8"))
    return "\n".join([
        f"untrusted comment: {untrusted_comment}",
        base64.b64encode(b"ED" + key_id + sig).decode(),
        f"trusted comment: {trusted_comment}",
        base64.b64encode(global_sig).decode(),
    ]) + "\n"
