#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Signiert „Bony's Agents.app“.
#
#   packaging/macos/sign.sh "dist/Bony's Agents.app"
#
# Mit Apple-Developer-ID, wenn APPLE_CERT_P12 (Zertifikat als .p12, base64) und APPLE_CERT_PASSWORD gesetzt
# sind: Hardened Runtime, Zeitstempel, von innen nach außen – Voraussetzung für die Notarisierung.
# Sonst ad-hoc („-“): kostet nichts, Gatekeeper fragt beim ersten Start aber nach (siehe README).
# Gibt die verwendete Identität aus („-“ für ad-hoc).
set -euo pipefail

APP="$1"
HERE="$(cd "$(dirname "$0")" && pwd)"

if [ -z "${APPLE_CERT_P12:-}" ]; then
  codesign --force --deep --sign - "$APP" >&2
  codesign --verify --deep --strict "$APP" >&2
  echo "-"
  exit 0
fi

: "${APPLE_CERT_PASSWORD:?APPLE_CERT_PASSWORD fehlt}"
TMP="${RUNNER_TEMP:-$(mktemp -d)}"
KEYCHAIN="$TMP/bonys-signing.keychain-db"
KC_PASS="$(uuidgen)"
security create-keychain -p "$KC_PASS" "$KEYCHAIN"
security set-keychain-settings -lut 21600 "$KEYCHAIN"
security unlock-keychain -p "$KC_PASS" "$KEYCHAIN"
(umask 077; printf '%s' "$APPLE_CERT_P12" | base64 --decode > "$TMP/cert.p12")
security import "$TMP/cert.p12" -k "$KEYCHAIN" -P "$APPLE_CERT_PASSWORD" -T /usr/bin/codesign >&2
rm -f "$TMP/cert.p12"
security set-key-partition-list -S apple-tool:,apple: -s -k "$KC_PASS" "$KEYCHAIN" >/dev/null
# shellcheck disable=SC2046
security list-keychains -d user -s "$KEYCHAIN" $(security list-keychains -d user | tr -d '"')
IDENTITY="${APPLE_SIGN_IDENTITY:-$(security find-identity -v -p codesigning "$KEYCHAIN" \
  | awk -F'"' '/Developer ID Application/ {print $2; exit}')}"
[ -n "$IDENTITY" ] || { echo "Keine „Developer ID Application“-Identität im Zertifikat gefunden." >&2; exit 1; }
echo "Signiere mit: $IDENTITY" >&2

sign() {
  codesign --force --timestamp --options runtime --entitlements "$HERE/entitlements.plist" \
    --keychain "$KEYCHAIN" --sign "$IDENTITY" "$@" >&2
}
# Von innen nach außen: erst jede Bibliothek, dann Frameworks, zuletzt die Programme und das Bundle.
while IFS= read -r -d '' f; do
  if [[ "$(file -b "$f")" == *Mach-O* ]]; then sign "$f"; fi
done < <(find "$APP/Contents/Frameworks" "$APP/Contents/Resources" -type f -print0)
while IFS= read -r -d '' fw; do sign "$fw"; done < <(find "$APP/Contents" -type d -name "*.framework" -print0)
for exe in "$APP/Contents/MacOS/"*; do sign "$exe"; done
sign "$APP"
codesign --verify --deep --strict --verbose=2 "$APP" >&2
echo "$IDENTITY"
