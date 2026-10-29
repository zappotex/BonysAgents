#!/bin/bash
# Solution – only runs with "Check course package" in the editor, never for participants.
# The same commands as in the "Agent Apps" list (entry PdfCraft), then the registration with Hermes.
set -e
mkdir -p ~/Downloads/pdfcraft && cd ~/Downloads/pdfcraft
wget -q -N https://github.com/storytold/pdfcraft/releases/latest/download/SHA256SUMS.txt
DATEI=$(grep -o "pdfcraft-cli-[0-9.]*-linux-$(uname -m)\.tar\.gz" SHA256SUMS.txt | head -n1)
wget -q -N "https://github.com/storytold/pdfcraft/releases/latest/download/$DATEI"
sha256sum --check --ignore-missing --quiet SHA256SUMS.txt
mkdir -p ~/.local/bin && tar -xzf "$DATEI" -C ~/.local/bin --strip-components=1
mkdir -p ~/Agent-Files/pdf
printf 'Y\n' | ~/.local/bin/hermes mcp add pdfcraft --command "$HOME/.local/bin/pdfcraft-cli" \
  --args mcp --compact --root "$HOME/Agent-Files/pdf" >/dev/null
