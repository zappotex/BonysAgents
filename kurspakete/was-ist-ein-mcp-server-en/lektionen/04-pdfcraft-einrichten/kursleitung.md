**Flow:** 5 minutes demo (shared screen), 15 minutes doing it yourselves, 5 minutes buffer.

- Pasting in the terminal is **Ctrl + Shift + V** – that's the most common stumbling block.
- The commands always fetch the **latest** version (`releases/latest`) and read the file name from `SHA256SUMS.txt`.
  No version number has to be replaced.
- `sha256sum --check` must report **OK** for the downloaded file. With **FAILED**: delete the file, run the block
  again; if it stays that way, don't continue.
- `hermes mcp test pdfcraft` shows the tools – a quick way to see whether the registration worked.
- `hermes mcp add` asks "Enable all …" → **Y**. Then **Saved 'pdfcraft'**.
- Hermes loads new MCP servers at startup; `/reload-mcp` reloads them in a running Hermes.
- The check only looks whether `~/.local/bin/pdfcraft-cli` exists and whether there's an entry `pdfcraft` under
  `mcp_servers` in `~/.hermes/config.yaml` – it reads no keys.
- `hermes: command not found` → Agent PC without Hermes → "Add programs …" → Hermes Agent.
