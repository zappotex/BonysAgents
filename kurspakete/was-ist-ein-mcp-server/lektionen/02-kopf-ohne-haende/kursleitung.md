**Live-Vorführung** in deinem Agent-PC (ohne PdfCraft): dieselbe Bitte wie in der Anleitung. Je nach Modell
versucht Hermes `pdftotext`, Python oder schlägt vor, etwas zu installieren. Gerade die Umwege sind lehrreich:
„Er weiß, was zu tun wäre – aber er hat kein passendes Werkzeug.“

- Bild: „Kluger Kopf ohne Hände“. MCP = die Steckdose, an die man Werkzeuge anschließt.
- Wichtig für später: Ein MCP-Server bekommt **nur einen Ordner** (`--root`). So kann der Agent nichts außerhalb
  bearbeiten.
- Das Startskript legt `rechnung-maerz.pdf`, `rechnung-april.pdf` und `protokoll.pdf` (Seite 2 quer) nach
  `~/Agent-Dateien/pdf`. Im Vorführ-Agent-PC vorher dieselben Dateien bereitlegen (Kurspaket selbst durcharbeiten
  oder Dateien kopieren).
