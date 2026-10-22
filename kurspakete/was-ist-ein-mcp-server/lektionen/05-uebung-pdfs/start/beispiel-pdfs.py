#!/usr/bin/env python3
# Startzustand: Beispiel-PDFs in ~/Agent-Dateien/pdf (wiederholbar, überschreibt nur diese drei Dateien).
# Erfundener Verein, keine echten Personen. Schreibt die PDFs selbst – ohne Zusatzprogramme im Agent-PC.
import pathlib

ORDNER = pathlib.Path.home() / "Agent-Dateien" / "pdf"

RECHNUNG_MAERZ = [
    ["Gartenverein Sonnenwiese e. V. (Beispiel)", "", "Rechnung Nr. 2026-031", "Datum: 31.03.2026", "",
     "Rasenmäher-Wartung           38,00 EUR", "Ersatzteile                  10,50 EUR", "",
     "Summe                        48,50 EUR", "", "Zahlbar innerhalb von 14 Tagen."],
]
RECHNUNG_APRIL = [
    ["Gartenverein Sonnenwiese e. V. (Beispiel)", "", "Rechnung Nr. 2026-042", "Datum: 30.04.2026", "",
     "Heckenschere schärfen        22,00 EUR", "Gartenschlauch 20 m          19,90 EUR", "",
     "Summe                        41,90 EUR", "", "Zahlbar innerhalb von 14 Tagen."],
]
PROTOKOLL = [
    ["Protokoll der Mitgliederversammlung", "Gartenverein Sonnenwiese e. V. (Beispiel)", "12. März 2026, Vereinsheim",
     "", "Tagesordnung", "1. Begrüßung durch den Vorstand", "2. Bericht der Kasse", "3. Beschlüsse",
     "4. Sonstiges", "", "Anwesend: 23 Mitglieder. Die Versammlung ist beschlussfähig."],
    ["3. Beschlüsse", "", "Beschluss 1: Der Mitgliedsbeitrag bleibt bei 36 EUR im Jahr.",
     "Beschluss 2: Das Sommerfest findet am 4. Juli statt.",
     "Beschluss 3: Für den Gemeinschaftsgarten wird eine Regentonne gekauft.", "",
     "Alle Beschlüsse einstimmig."],
    ["4. Sonstiges", "", "Die Wasseruhren werden im April abgelesen.",
     "Die nächste Versammlung ist im März 2027.", "", "Ende der Versammlung: 21:15 Uhr."],
]


def _text(s: str) -> bytes:
    return s.encode("cp1252").replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def pdf(seiten: list[list[str]], quer: tuple[int, ...] = ()) -> bytes:
    """Einfaches PDF mit Text in Helvetica; Seiten in ``quer`` (ab 1) stehen um 90° gedreht."""
    n = len(seiten)
    objekte: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [" + b" ".join(b"%d 0 R" % (4 + 2 * i) for i in range(n)) + b"] /Count %d >>" % n,
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    for nr, zeilen in enumerate(seiten, start=1):
        inhalt = b"BT /F1 13 Tf 17 TL 60 780 Td " + b" ".join(b"(" + _text(z) + b") Tj T*" for z in zeilen) + b" ET"
        drehen = b" /Rotate 90" if nr in quer else b""
        objekte.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >>"
                       b" /Contents %d 0 R" % (5 + 2 * (nr - 1)) + drehen + b" >>")
        objekte.append(b"<< /Length %d >>\nstream\n" % len(inhalt) + inhalt + b"\nendstream")
    daten = bytearray(b"%PDF-1.4\n")
    stellen = []
    for i, obj in enumerate(objekte, start=1):
        stellen.append(len(daten))
        daten += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(daten)
    daten += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objekte) + 1)
    daten += b"".join(b"%010d 00000 n \n" % s for s in stellen)
    daten += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objekte) + 1, xref)
    return bytes(daten)


ORDNER.mkdir(parents=True, exist_ok=True)
(ORDNER / "rechnung-maerz.pdf").write_bytes(pdf(RECHNUNG_MAERZ))
(ORDNER / "rechnung-april.pdf").write_bytes(pdf(RECHNUNG_APRIL))
(ORDNER / "protokoll.pdf").write_bytes(pdf(PROTOKOLL, quer=(2,)))
