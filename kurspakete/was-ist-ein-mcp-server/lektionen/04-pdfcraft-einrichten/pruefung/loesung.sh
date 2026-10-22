#!/bin/bash
# Lösung – läuft nur bei „Kurspaket prüfen“ im Editor, nie bei Teilnehmern.
# Dieselben Befehle wie in der Liste „Agenten-Apps“ (Eintrag PdfCraft), dann die Anmeldung bei Hermes.
set -e
mkdir -p ~/Downloads/pdfcraft && cd ~/Downloads/pdfcraft
wget -q -N https://github.com/storytold/pdfcraft/releases/latest/download/SHA256SUMS.txt
DATEI=$(grep -o "pdfcraft-cli-[0-9.]*-linux-$(uname -m)\.tar\.gz" SHA256SUMS.txt | head -n1)
wget -q -N "https://github.com/storytold/pdfcraft/releases/latest/download/$DATEI"
sha256sum --check --ignore-missing --quiet SHA256SUMS.txt
mkdir -p ~/.local/bin && tar -xzf "$DATEI" -C ~/.local/bin --strip-components=1
mkdir -p ~/Agent-Dateien/pdf
printf 'Y\n' | ~/.local/bin/hermes mcp add pdfcraft --command "$HOME/.local/bin/pdfcraft-cli" \
  --args mcp --compact --root "$HOME/Agent-Dateien/pdf" >/dev/null
