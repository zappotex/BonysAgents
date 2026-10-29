#!/usr/bin/env python3
# Starting state: sample PDFs in ~/Agent-Files/pdf (repeatable, only overwrites these three files).
# Made-up club, no real people. Writes the PDFs itself – without extra programs in the Agent PC.
import pathlib

ORDNER = pathlib.Path.home() / "Agent-Files" / "pdf"

RECHNUNG_MAERZ = [
    ["Sunny Meadow Garden Club (sample)", "", "Invoice no. 2026-031", "Date: 2026-03-31", "",
     "Lawn mower service            38.00 EUR", "Spare parts                   10.50 EUR", "",
     "Total                         48.50 EUR", "", "Payable within 14 days."],
]
RECHNUNG_APRIL = [
    ["Sunny Meadow Garden Club (sample)", "", "Invoice no. 2026-042", "Date: 2026-04-30", "",
     "Hedge trimmer sharpening      22.00 EUR", "Garden hose 20 m              19.90 EUR", "",
     "Total                         41.90 EUR", "", "Payable within 14 days."],
]
PROTOKOLL = [
    ["Minutes of the general meeting", "Sunny Meadow Garden Club (sample)", "12 March 2026, clubhouse",
     "", "Agenda", "1. Welcome by the board", "2. Treasurer's report", "3. Resolutions",
     "4. Any other business", "", "Present: 23 members. The meeting has a quorum."],
    ["3. Resolutions", "", "Resolution 1: The membership fee stays at 36 EUR a year.",
     "Resolution 2: The summer party takes place on 4 July.",
     "Resolution 3: A rain barrel will be bought for the community garden.", "",
     "All resolutions unanimous."],
    ["4. Any other business", "", "The water meters will be read in April.",
     "The next meeting is in March 2027.", "", "End of the meeting: 9:15 pm."],
]


def _text(s: str) -> bytes:
    return s.encode("cp1252").replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def pdf(seiten: list[list[str]], quer: tuple[int, ...] = ()) -> bytes:
    """Simple PDF with text in Helvetica; pages in ``quer`` (from 1) are rotated by 90°."""
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
(ORDNER / "invoice-march.pdf").write_bytes(pdf(RECHNUNG_MAERZ))
(ORDNER / "invoice-april.pdf").write_bytes(pdf(RECHNUNG_APRIL))
(ORDNER / "minutes.pdf").write_bytes(pdf(PROTOKOLL, quer=(2,)))
