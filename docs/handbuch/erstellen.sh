#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Handbücher von Bony's Agents: Bildschirmfotos neu aufnehmen und alle PDFs erzeugen.
#
#   docs/handbuch/erstellen.sh               Bildschirmfotos + PDFs
#   docs/handbuch/erstellen.sh --ohne-bilder nur PDFs (mit den Bildern, die in bilder/ liegen)
#   docs/handbuch/erstellen.sh --nur-bilder  nur Bildschirmfotos
#
# Braucht: pandoc und typst (getestet: 3.12.1 und 0.15.1, wie in .github/workflows/release.yml), für die
# Bildschirmfotos Python mit den Abhängigkeiten von Bony's Agents (PySide6, PySide6-WebEngine, psutil,
# platformdirs, qrcode – z. B. build/venv), die Seite des Kursraums (packaging/fetch-livekit.py) und tesseract.
# Siehe docs/handbuch/README.md.
#
# Die PDFs landen in docs/handbuch/pdf/ (nicht im Repository – sie hängen am Release).
set -euo pipefail

HANDBUCH="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HANDBUCH/../.." && pwd)"
BAU="$HANDBUCH/_bau"
AUSGABE="$HANDBUCH/pdf"

BILDER=1
PDFS=1
case "${1:-}" in
  --ohne-bilder) BILDER=0 ;;
  --nur-bilder) PDFS=0 ;;
  "") ;;
  *) echo "Unbekannte Option: $1 (erlaubt: --ohne-bilder, --nur-bilder)" >&2; exit 2 ;;
esac

fehlt() { echo "Fehlt: $1" >&2; echo "  $2" >&2; exit 1; }

VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$REPO/src/bonys_agents/__init__.py")"
[ -n "$VERSION" ] || fehlt "Version" "src/bonys_agents/__init__.py enthält kein __version__."
# Datum des letzten Commits – so ergibt derselbe Stand immer dasselbe PDF
DATUM="$(git -C "$REPO" log -1 --format=%cd --date=format:%d.%m.%Y 2>/dev/null || date +%d.%m.%Y)"

# ---------------------------------------------------------------- Bildschirmfotos
if [ "$BILDER" = 1 ]; then
  PYTHON="${PYTHON:-}"
  if [ -z "$PYTHON" ]; then
    if [ -x "$REPO/build/venv/bin/python" ]; then PYTHON="$REPO/build/venv/bin/python"; else PYTHON=python3; fi
  fi
  "$PYTHON" -c "import PySide6.QtWebEngineWidgets, psutil, platformdirs" 2>/dev/null \
    || fehlt "PySide6 mit WebEngine für $PYTHON" "python3 -m venv build/venv && build/venv/bin/pip install -e '.[dev]'"
  [ -f "$REPO/src/bonys_agents/resources/kursraum/vendor/livekit-client.umd.js" ] \
    || "$PYTHON" "$REPO/packaging/fetch-livekit.py"
  [ -d "$REPO/src/bonys_agents/trainer" ] || fehlt "src/bonys_agents/trainer" "Die Kursleiter-Bilder brauchen den vollständigen Quellcode."
  echo "== Bildschirmfotos (Version $VERSION)"
  # Nur die automatisch erzeugten Bilder ersetzen – selbst gemachte liegen in bilder/eigene/.
  # Deutsch in bilder/, Englisch (Oberfläche auf Englisch, für docs/handbuch/en/) in bilder/en/.
  for sprache in de en; do
    ziel="$HANDBUCH/bilder"; [ "$sprache" = de ] || ziel="$HANDBUCH/bilder/$sprache"
    mkdir -p "$ziel"
    find "$ziel" -maxdepth 1 -name '*.png' -delete
    for edition in anwender kursleiter; do
      "$PYTHON" "$HANDBUCH/vorfuehrung/bildschirmfotos.py" --edition "$edition" --sprache "$sprache" --ziel "$ziel" 2>&1 \
        | grep -v -E '^\[[0-9]+:|libva|Vulkan|GLX|GPUInfo|propagateSizeHints|plugin does not|QRhi|RHI for' || true
    done
    [ -f "$ziel/hauptfenster.png" ] && [ -f "$ziel/kl-kursansicht.png" ] \
      || { echo "Die Bildschirmfotos ($sprache) wurden nicht vollständig erzeugt." >&2; exit 1; }
    "$PYTHON" "$HANDBUCH/vorfuehrung/pruefen.py" "$ziel"
  done
fi

# ---------------------------------------------------------------- PDFs
if [ "$PDFS" = 1 ]; then
  command -v pandoc >/dev/null || fehlt pandoc "https://github.com/jgm/pandoc/releases (eine Datei nach ~/.local/bin)"
  command -v typst >/dev/null || fehlt typst "https://github.com/typst/typst/releases (eine Datei nach ~/.local/bin)"
  mkdir -p "$BAU" "$AUSGABE"
  cd "$HANDBUCH"
  bauen() {   # bauen QUELLE DATEINAME DOKUMENT [kurz|kompakt]   (SPRACHE=en für die englischen)
    local quelle="$1" name="$2" dokument="$3" art="${4:-}"
    local ziel="$AUSGABE/BonysAgents-$name-$VERSION.pdf"
    pandoc "$quelle" -f markdown-citations -t typst --template vorlage/pandoc.typ --lua-filter vorlage/filter.lua \
      -V version="$VERSION" -V datum="$DATUM" -V dokument="$dokument" ${art:+-V "$art=true"} \
      -M sprache="${SPRACHE:-de}" \
      -o "$BAU/$name.typ"
    typst compile --root "$REPO" --font-path vorlage/schriften "$BAU/$name.typ" "$ziel"
    echo "  $(basename "$ziel")"
  }
  echo "== PDFs (Version $VERSION, Stand $DATUM) → $AUSGABE"
  bauen benutzer.md Benutzerhandbuch "Benutzerhandbuch"
  bauen kursleiter.md Kursleiter-Handbuch "Kursleiter-Handbuch"
  # Der Beispielkurs ist das mitgelieferte Kurspaket „Einführung in Hermes Agent“ – nur dort gepflegt
  BEISPIEL="../../kurspakete/einfuehrung-hermes-agent"
  bauen "$BEISPIEL/ablaufplan.md" Beispielkurs-Hermes-Kursleitung "Beispielkurs „Einführung in Hermes Agent“ – Kursleitung" kompakt
  bauen "$BEISPIEL/handout.md" Beispielkurs-Hermes-Handout "Handout „Einführung in Hermes Agent“" kurz
  # Englisch (docs/handbuch/en/, Bilder aus bilder/en/); Datum im englischen Format
  DATUM="$(git -C "$REPO" log -1 --format=%cd --date=format:%Y-%m-%d 2>/dev/null || date +%Y-%m-%d)"
  SPRACHE=en bauen en/user-guide.md User-Guide "User Guide"
  SPRACHE=en bauen en/trainer-guide.md Trainer-Guide "Trainer Guide"
  BEISPIEL_EN="../../kurspakete/einfuehrung-hermes-agent-en"
  SPRACHE=en bauen "$BEISPIEL_EN/ablaufplan.md" Sample-Course-Hermes-Trainer "Sample course “Introduction to Hermes Agent” – trainer" kompakt
  SPRACHE=en bauen "$BEISPIEL_EN/handout.md" Sample-Course-Hermes-Handout "Handout “Introduction to Hermes Agent”" kurz
fi
