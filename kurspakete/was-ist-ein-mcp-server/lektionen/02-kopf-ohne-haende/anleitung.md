# Ein Kopf ohne Hände

Ein Sprachmodell ist ein **kluger Kopf**: Es versteht deine Bitte und weiß, was zu tun wäre. Damit es auch etwas
**tun** kann, braucht es **Werkzeuge** – Hände sozusagen.

## Was ist ein MCP-Server?

**MCP** heißt *Model Context Protocol*. Es ist eine gemeinsame Sprache, über die ein Agent Werkzeuge benutzen kann.
Ein **MCP-Server** ist ein kleines Programm, das einem Agenten einen **Werkzeugkasten** anbietet – zum Beispiel
„PDF öffnen“, „Seite drehen“, „PDFs zusammenfügen“.

- Hermes fragt den MCP-Server: *Welche Werkzeuge hast du?*
- Für deine Aufgabe wählt Hermes das passende Werkzeug und benutzt es.
- Der MCP-Server läuft im Agent-PC und darf nur, was du ihm erlaubst – zum Beispiel nur einen bestimmten Ordner.

## Ausprobieren: Hermes ohne PDF-Werkzeug

Das Kurspaket hat drei Beispiel-PDFs in `~/Agent-Dateien/pdf` gelegt: zwei Rechnungen und ein Protokoll eines
erfundenen Gartenvereins.

Bitte Hermes: *„Seite 2 von ~/Agent-Dateien/pdf/protokoll.pdf steht quer. Dreh sie gerade.“*

Schau zu, was passiert: Sucht Hermes sich einen Umweg im Terminal? Fragt er nach? Sagt er, dass er es nicht kann?
**Nicht bestätigen**, wenn er Programme installieren will – das machen wir gleich selbst und sauber.

::: tipp
Text aus einem PDF **lesen** schafft Hermes oft auch ohne Zusatz-Werkzeug, mit Programmen, die im Agent-PC schon da
sind. Seiten drehen, löschen oder PDFs zusammenfügen geht mit einem echten PDF-Werkzeug **zuverlässiger** – und du
siehst genau, was er benutzt.
:::

Zum Schluss: das **Quiz**.
