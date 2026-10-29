# SPDX-License-Identifier: GPL-3.0-or-later
"""VNC-Passwörter (RFB „VNC Authentication“) ohne fremde Bibliothek – nur Standardbibliothek.

Die Hilfe-Funktion über das Bony-Netz (``bonys_agents.hilfe``) braucht das an zwei Stellen:

- ``passwortdatei``: Datei im Format von ``vncpasswd`` für TigerVNC ``vncviewer -PasswordFile`` (Rückfall, wo der
  eingebettete Betrachter fehlt). So steht das Passwort nie auf der Kommandozeile.
- ``antwort``: Antwort auf die 16-Byte-Herausforderung des Servers – für Tests mit einem eigenen VNC-Server.

Beides ist DES mit der VNC-Eigenheit, dass die Bits jedes Schlüsselbytes umgedreht werden. DES ist hier keine
Sicherheitsgrenze (VNC benutzt es so, das Passwort gilt nur für eine Sitzung und die Verbindung läuft verschlüsselt
über das Bony-Netz).
"""

from __future__ import annotations

from bonys_agents.i18n import tr

FESTER_SCHLUESSEL = bytes([23, 82, 107, 6, 35, 78, 88, 7])   # vncpasswd/d3des, Werte wie in TigerVNC
LAENGE = 8   # VNC benutzt höchstens 8 Zeichen des Passworts

# ---------------------------------------------------------------- DES (FIPS 46-3), nur Verschlüsseln eines Blocks
_PC1 = (57, 49, 41, 33, 25, 17, 9, 1, 58, 50, 42, 34, 26, 18, 10, 2, 59, 51, 43, 35, 27, 19, 11, 3, 60, 52, 44, 36,
        63, 55, 47, 39, 31, 23, 15, 7, 62, 54, 46, 38, 30, 22, 14, 6, 61, 53, 45, 37, 29, 21, 13, 5, 28, 20, 12, 4)
_PC2 = (14, 17, 11, 24, 1, 5, 3, 28, 15, 6, 21, 10, 23, 19, 12, 4, 26, 8, 16, 7, 27, 20, 13, 2,
        41, 52, 31, 37, 47, 55, 30, 40, 51, 45, 33, 48, 44, 49, 39, 56, 34, 53, 46, 42, 50, 36, 29, 32)
_SHIFTS = (1, 1, 2, 2, 2, 2, 2, 2, 1, 2, 2, 2, 2, 2, 2, 1)
_IP = (58, 50, 42, 34, 26, 18, 10, 2, 60, 52, 44, 36, 28, 20, 12, 4, 62, 54, 46, 38, 30, 22, 14, 6,
       64, 56, 48, 40, 32, 24, 16, 8, 57, 49, 41, 33, 25, 17, 9, 1, 59, 51, 43, 35, 27, 19, 11, 3,
       61, 53, 45, 37, 29, 21, 13, 5, 63, 55, 47, 39, 31, 23, 15, 7)
_FP = (40, 8, 48, 16, 56, 24, 64, 32, 39, 7, 47, 15, 55, 23, 63, 31, 38, 6, 46, 14, 54, 22, 62, 30,
       37, 5, 45, 13, 53, 21, 61, 29, 36, 4, 44, 12, 52, 20, 60, 28, 35, 3, 43, 11, 51, 19, 59, 27,
       34, 2, 42, 10, 50, 18, 58, 26, 33, 1, 41, 9, 49, 17, 57, 25)
_E = (32, 1, 2, 3, 4, 5, 4, 5, 6, 7, 8, 9, 8, 9, 10, 11, 12, 13, 12, 13, 14, 15, 16, 17,
      16, 17, 18, 19, 20, 21, 20, 21, 22, 23, 24, 25, 24, 25, 26, 27, 28, 29, 28, 29, 30, 31, 32, 1)
_P = (16, 7, 20, 21, 29, 12, 28, 17, 1, 15, 23, 26, 5, 18, 31, 10, 2, 8, 24, 14, 32, 27, 3, 9,
      19, 13, 30, 6, 22, 11, 4, 25)
_S = (
    (14, 4, 13, 1, 2, 15, 11, 8, 3, 10, 6, 12, 5, 9, 0, 7, 0, 15, 7, 4, 14, 2, 13, 1, 10, 6, 12, 11, 9, 5, 3, 8,
     4, 1, 14, 8, 13, 6, 2, 11, 15, 12, 9, 7, 3, 10, 5, 0, 15, 12, 8, 2, 4, 9, 1, 7, 5, 11, 3, 14, 10, 0, 6, 13),
    (15, 1, 8, 14, 6, 11, 3, 4, 9, 7, 2, 13, 12, 0, 5, 10, 3, 13, 4, 7, 15, 2, 8, 14, 12, 0, 1, 10, 6, 9, 11, 5,
     0, 14, 7, 11, 10, 4, 13, 1, 5, 8, 12, 6, 9, 3, 2, 15, 13, 8, 10, 1, 3, 15, 4, 2, 11, 6, 7, 12, 0, 5, 14, 9),
    (10, 0, 9, 14, 6, 3, 15, 5, 1, 13, 12, 7, 11, 4, 2, 8, 13, 7, 0, 9, 3, 4, 6, 10, 2, 8, 5, 14, 12, 11, 15, 1,
     13, 6, 4, 9, 8, 15, 3, 0, 11, 1, 2, 12, 5, 10, 14, 7, 1, 10, 13, 0, 6, 9, 8, 7, 4, 15, 14, 3, 11, 5, 2, 12),
    (7, 13, 14, 3, 0, 6, 9, 10, 1, 2, 8, 5, 11, 12, 4, 15, 13, 8, 11, 5, 6, 15, 0, 3, 4, 7, 2, 12, 1, 10, 14, 9,
     10, 6, 9, 0, 12, 11, 7, 13, 15, 1, 3, 14, 5, 2, 8, 4, 3, 15, 0, 6, 10, 1, 13, 8, 9, 4, 5, 11, 12, 7, 2, 14),
    (2, 12, 4, 1, 7, 10, 11, 6, 8, 5, 3, 15, 13, 0, 14, 9, 14, 11, 2, 12, 4, 7, 13, 1, 5, 0, 15, 10, 3, 9, 8, 6,
     4, 2, 1, 11, 10, 13, 7, 8, 15, 9, 12, 5, 6, 3, 0, 14, 11, 8, 12, 7, 1, 14, 2, 13, 6, 15, 0, 9, 10, 4, 5, 3),
    (12, 1, 10, 15, 9, 2, 6, 8, 0, 13, 3, 4, 14, 7, 5, 11, 10, 15, 4, 2, 7, 12, 9, 5, 6, 1, 13, 14, 0, 11, 3, 8,
     9, 14, 15, 5, 2, 8, 12, 3, 7, 0, 4, 10, 1, 13, 11, 6, 4, 3, 2, 12, 9, 5, 15, 10, 11, 14, 1, 7, 6, 0, 8, 13),
    (4, 11, 2, 14, 15, 0, 8, 13, 3, 12, 9, 7, 5, 10, 6, 1, 13, 0, 11, 7, 4, 9, 1, 10, 14, 3, 5, 12, 2, 15, 8, 6,
     1, 4, 11, 13, 12, 3, 7, 14, 10, 15, 6, 8, 0, 5, 9, 2, 6, 11, 13, 8, 1, 4, 10, 7, 9, 5, 0, 15, 14, 2, 3, 12),
    (13, 2, 8, 4, 6, 15, 11, 1, 10, 9, 3, 14, 5, 0, 12, 7, 1, 15, 13, 8, 10, 3, 7, 4, 12, 5, 6, 11, 0, 14, 9, 2,
     7, 11, 4, 1, 9, 12, 14, 2, 0, 6, 10, 13, 15, 3, 5, 8, 2, 1, 14, 7, 4, 10, 8, 13, 15, 12, 9, 0, 3, 5, 6, 11),
)


def _bits(data: bytes) -> list[int]:
    return [(b >> (7 - i)) & 1 for b in data for i in range(8)]


def _bytes(bits: list[int]) -> bytes:
    return bytes(sum(bit << (7 - i) for i, bit in enumerate(bits[n:n + 8])) for n in range(0, len(bits), 8))


def _perm(bits: list[int], table: tuple[int, ...]) -> list[int]:
    return [bits[i - 1] for i in table]


def des_block(key: bytes, block: bytes) -> bytes:
    """Einen 8-Byte-Block mit DES verschlüsseln (Schlüssel 8 Byte, Paritätsbits zählen nicht)."""
    if len(key) != 8 or len(block) != 8:
        raise ValueError(tr("DES braucht 8 Byte Schlüssel und 8 Byte Daten"))
    cd = _perm(_bits(key), _PC1)
    c, d = cd[:28], cd[28:]
    teilschluessel = []
    for s in _SHIFTS:
        c, d = c[s:] + c[:s], d[s:] + d[:s]
        teilschluessel.append(_perm(c + d, _PC2))
    lr = _perm(_bits(block), _IP)
    left, right = lr[:32], lr[32:]
    for k in teilschluessel:
        x = [a ^ b for a, b in zip(_perm(right, _E), k, strict=True)]
        out: list[int] = []
        for n in range(8):
            six = x[n * 6:n * 6 + 6]
            zeile = (six[0] << 1) | six[5]
            spalte = (six[1] << 3) | (six[2] << 2) | (six[3] << 1) | six[4]
            wert = _S[n][zeile * 16 + spalte]
            out += [(wert >> (3 - i)) & 1 for i in range(4)]
        f = _perm(out, _P)
        left, right = right, [a ^ b for a, b in zip(left, f, strict=True)]
    return _bytes(_perm(right + left, _FP))


# ---------------------------------------------------------------- VNC
def _vnc_schluessel(schluessel: bytes) -> bytes:
    """VNC dreht die Bits jedes Schlüsselbytes um (Eigenheit von d3des)."""
    return bytes(int(f"{b:08b}"[::-1], 2) for b in schluessel)


def _passwort_bytes(passwort: str) -> bytes:
    return passwort.encode("latin-1", errors="replace")[:LAENGE].ljust(LAENGE, b"\0")


def antwort(passwort: str, herausforderung: bytes) -> bytes:
    """Antwort des Betrachters auf die 16-Byte-Herausforderung des Servers."""
    if len(herausforderung) != 16:
        raise ValueError(tr("Die Herausforderung ist 16 Byte lang"))
    k = _vnc_schluessel(_passwort_bytes(passwort))
    return des_block(k, herausforderung[:8]) + des_block(k, herausforderung[8:])


def passwortdatei(passwort: str) -> bytes:
    """Inhalt einer Passwortdatei wie von ``vncpasswd`` (8 Byte) – für ``vncviewer -PasswordFile``."""
    return des_block(_vnc_schluessel(FESTER_SCHLUESSEL), _passwort_bytes(passwort))
