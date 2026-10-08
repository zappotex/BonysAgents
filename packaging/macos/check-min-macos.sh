#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Prüft jede Programmdatei im Bundle:
#   - Architektur: muss passen, sonst „Bad CPU type in executable“ (Fehler).
#   - Mindest-macOS (minos): neuer als LSMinimumSystemVersion gibt eine Warnung. dyld lehnt solche
#     Bibliotheken nicht grundsätzlich ab (PySide6 baut z. B. mit neuerem SDK, als das Wheel angibt) –
#     ob die App auf dem ältesten macOS wirklich startet, prüft der Job „macos-compat“ im Release-Workflow.
#
#   packaging/macos/check-min-macos.sh "dist/Bony's Agents.app" arm64
set -euo pipefail

APP="$1"
ARCH="$2"
MIN="$(plutil -extract LSMinimumSystemVersion raw "$APP/Contents/Info.plist")"
echo "LSMinimumSystemVersion: $MIN, Architektur: $ARCH"
newest="0"
bad=0
count=0
while IFS= read -r -d '' f; do
  [[ "$(file -b "$f")" == *Mach-O* ]] || continue
  count=$((count + 1))
  archs=" $(lipo -archs "$f") "
  if [[ "$archs" != *" $ARCH "* ]]; then
    echo "::error::falsche Architektur ($archs): ${f#"$APP"/}"
    bad=1
  fi
  minos="$(otool -l -arch "$ARCH" "$f" 2>/dev/null | awk '
    /LC_BUILD_VERSION/ {b = 1} b && $1 == "minos" {print $2; exit}
    /LC_VERSION_MIN_MACOSX/ {m = 1} m && $1 == "version" {print $2; exit}')"
  [ -n "$minos" ] || continue
  if [ "$(printf '%s\n%s\n' "$minos" "$MIN" | sort -V | tail -1)" != "$MIN" ]; then
    echo "::warning::minos $minos (> $MIN): ${f#"$APP"/}"
  fi
  [ "$(printf '%s\n%s\n' "$minos" "$newest" | sort -V | tail -1)" = "$minos" ] && newest="$minos"
done < <(find "$APP/Contents" -type f -print0)
echo "$count Programmdateien geprüft, höchstes verlangtes macOS: $newest"
exit "$bad"
