**Ablauf:** 5 Minuten vorführen (geteilter Bildschirm), 15 Minuten selbst machen, 5 Minuten Puffer.

- Einfügen im Terminal ist **Strg + Umschalt + V** – das ist die häufigste Stolperstelle.
- Die Befehle holen immer die **neueste** Version (`releases/latest`) und lesen den Dateinamen aus `SHA256SUMS.txt`.
  Es muss keine Versionsnummer ersetzt werden.
- `sha256sum --check` muss für die heruntergeladene Datei **OK** melden. Bei **FEHLSCHLAG**: Datei löschen, Block
  noch einmal ausführen; bleibt es so, nicht weitermachen.
- `hermes mcp test pdfcraft` zeigt die Werkzeuge – damit siehst du schnell, ob die Anmeldung geklappt hat.
- `hermes mcp add` fragt nach „Enable all …“ → **Y**. Danach **Saved 'pdfcraft'**.
- Neue MCP-Server lädt Hermes beim Start; `/reload-mcp` lädt sie im laufenden Hermes neu.
- Die Prüfung schaut nur, ob `~/.local/bin/pdfcraft-cli` da ist und ob unter `mcp_servers` in
  `~/.hermes/config.yaml` ein Eintrag `pdfcraft` steht – sie liest keine Schlüssel.
- `hermes: command not found` → Agent-PC ohne Hermes → „Programme hinzufügen …“ → Hermes Agent.
