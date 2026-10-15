#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Baut die .dmg: die App, eine Verknüpfung zum Programme-Ordner und eine kurze Anleitung für den ersten Start.
#
#   packaging/macos/build-dmg.sh "dist/Bony's Agents.app" dist/BonysAgents-0.13.0-macos-applesilicon.dmg
#   packaging/macos/build-dmg.sh "dist/Bony's Agents.app" dist/BonysAgents-Kursleiter-….dmg "Bony's Agents Kursleiter"
#
# Die App heißt in beiden Editionen „Bony's Agents.app“ (gleiche Bundle-ID) – so ersetzt die eine beim Hineinziehen
# in „Programme“ die andere. Welche Edition es ist, zeigen der Name der .dmg und des Laufwerks.
set -euo pipefail

APP="$1"
OUT="$2"
DEFAULT_NAME="Bony's Agents"
VOLNAME="${3:-$DEFAULT_NAME}"
HERE="$(cd "$(dirname "$0")" && pwd)"
STAGE="$(mktemp -d)/$VOLNAME"
mkdir -p "$STAGE"
ditto "$APP" "$STAGE/$(basename "$APP")"
ln -s /Applications "$STAGE/Programme"
cp "$HERE/Erster-Start.txt" "$STAGE/Zuerst lesen – erster Start.txt"
rm -f "$OUT"
# hdiutil scheitert auf den GitHub-Runnern gelegentlich mit „Resource busy“ – dann noch einmal versuchen.
for attempt in 1 2 3 4 5; do
  if hdiutil create -volname "$VOLNAME" -srcfolder "$STAGE" -fs HFS+ -format UDZO \
      -imagekey zlib-level=9 -ov "$OUT"; then
    break
  fi
  [ "$attempt" -lt 5 ] || exit 1
  echo "hdiutil fehlgeschlagen – neuer Versuch in 10 s …" >&2
  sleep 10
done
rm -rf "$(dirname "$STAGE")"
hdiutil verify "$OUT"
