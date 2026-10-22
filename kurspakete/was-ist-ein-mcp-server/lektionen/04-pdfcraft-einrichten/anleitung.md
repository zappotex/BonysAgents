# PdfCraft einrichten

Jetzt bekommt Hermes seine Hände: Du installierst **PdfCraft** und meldest seinen MCP-Server bei Hermes an.

## 1. Den Eintrag öffnen

In der Liste **„Agenten-Apps“** beim Eintrag **PdfCraft** auf **„Installieren & mit Hermes verbinden“** klicken.

## 2. Installieren

Öffne im Agent-PC ein **Terminal**. Kopiere den ersten Block (**„Kopieren“**) und füge ihn im Terminal ein
(**Strg + Umschalt + V**), dann Eingabetaste.

Die Befehle laden die neueste Version von der offiziellen Seite, prüfen die **Prüfsumme** und legen das Programm
nach `~/.local/bin`. Achte auf diese Zeile:

```
pdfcraft-cli-…-linux-x86_64.tar.gz: OK
```

**OK** heißt: Die Datei ist unverändert. Steht dort **FEHLSCHLAG**, hör auf und hol dir Hilfe.

## 3. Bei Hermes anmelden

Kopiere den zweiten Block – er beginnt mit `hermes mcp add pdfcraft` – und füge ihn im Terminal ein. Hermes zeigt
die Werkzeuge von PdfCraft und fragt, ob er alle benutzen darf: mit **Y** bestätigen. Am Ende steht
**Saved 'pdfcraft'**.

::: hinweis
Im Befehl steht `--root …/Agent-Dateien/pdf`. Damit darf PdfCraft **nur** in diesem Ordner lesen und speichern.
:::

## 4. Testen und Hermes neu starten

Prüfe die Verbindung im Terminal:

```
hermes mcp test pdfcraft
```

Steht dort **✓ Connected** und darunter eine Liste von Werkzeugen (z. B. `doc_open`), ist alles bereit.

Hermes lädt neue MCP-Server beim Start: Beende ein laufendes Hermes mit `/exit` und starte es neu mit
`hermes --tui` – oder gib im laufenden Hermes `/reload-mcp` ein.

Frag dann: *„Welche Werkzeuge hast du jetzt für PDFs?“*

Fertig? Klick auf **„Prüfen“**.

::: tipp
**Es geht auch bequemer:** Du kannst Hermes selbst bitten: *„Installiere PdfCraft aus der Agenten-Liste und richte
den MCP-Server ein.“* Er zeigt dir vorher, was er tun will. Wie man diese Schritte prüft, bevor man „Ja“ sagt, ist
Thema eines eigenen Kurses – heute machen wir es einmal von Hand, damit du jeden Schritt kennst.
:::
