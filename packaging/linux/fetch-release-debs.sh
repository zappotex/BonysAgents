#!/usr/bin/env bash
# Lädt die .deb aus dem neuesten Release eines Projekts und lässt nur geprüfte Pakete durch – für die APT-Paketquelle
# (.github/workflows/apt-repo.yml). Die Paketquelle wird danach mit GPG signiert; deshalb muss hier dieselbe
# Kette gelten wie beim Update in der App:
#
#   1. SHA256SUMS und SHA256SUMS.minisig müssen da sein (sonst Abbruch),
#   2. die Signatur muss vom Schlüssel stammen, der fest in Bony's Agents steckt (UPDATE_PUBLIC_KEY; Bony's VPN
#      signiert mit demselben), und ihr vertrauenswürdiger Kommentar muss genau „<Name> <Tag>“ lauten,
#   3. jede .deb muss in SHA256SUMS stehen und passen,
#   4. Paketname aus der erlaubten Liste DIESES Projekts, Version = Tag ohne „v“.
#
#   packaging/linux/fetch-release-debs.sh <owner/repo> "<Name>" <zielordner> <paket> [<paket> …]
#   z. B. … zappotex/bonys-vpn "Bony's VPN" debs bonys-vpn bonys-vpn-agentpc
#
# Gibt „<repo> <tag>“ aus. Braucht gh (angemeldet bzw. GH_TOKEN), python3 und dpkg-deb.
set -euo pipefail

repo="$1"; label="$2"; out="$3"; shift 3
allowed=" $* "
root="$(cd "$(dirname "$0")/../.." && pwd)"
fail() { echo "::error::$repo: $*" >&2; exit 1; }

tag="$(gh release view -R "$repo" --json tagName -q .tagName)"
[ -n "$tag" ] || fail "kein Release gefunden"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
gh release download "$tag" -R "$repo" --dir "$work" --pattern 'SHA256SUMS*' --pattern '*.deb'
[ -s "$work/SHA256SUMS" ] || fail "SHA256SUMS fehlt in $tag"
[ -s "$work/SHA256SUMS.minisig" ] || fail "SHA256SUMS.minisig fehlt in $tag"

# Mit demselben Prüfcode wie die App (bonys_agents.signing); -I: nichts aus dem Arbeitsordner laden
comment="$(python3 -I - "$root/src" "$work/SHA256SUMS" "$work/SHA256SUMS.minisig" <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from bonys_agents import UPDATE_PUBLIC_KEY, signing

data = Path(sys.argv[2]).read_bytes()
try:
    print(signing.verify(data, Path(sys.argv[3]).read_text("utf-8"), UPDATE_PUBLIC_KEY))
except signing.SignatureError as e:
    sys.exit(f"Signatur von SHA256SUMS: {e}")
PY
)" || fail "Signatur von SHA256SUMS ungültig"
[ "$comment" = "$label $tag" ] || fail "Signatur gilt für „$comment“, erwartet „$label $tag“"

shopt -s nullglob
debs=("$work"/*.deb)
[ "${#debs[@]}" -gt 0 ] || fail "keine .deb in $tag"
for deb in "${debs[@]}"; do
  name="$(basename "$deb")"
  sum="$(awk -v f="$name" '$2 == f || $2 == "*" f { print $1; exit }' "$work/SHA256SUMS")"
  [ -n "$sum" ] || fail "$name steht nicht in SHA256SUMS"
  [ "$(sha256sum "$deb" | cut -d' ' -f1)" = "$sum" ] || fail "Prüfsumme von $name stimmt nicht"
  pkg="$(dpkg-deb -f "$deb" Package)"
  [[ "$allowed" == *" $pkg "* ]] || fail "$name enthält das Paket „$pkg“ – erlaubt sind:$allowed"
  ver="$(dpkg-deb -f "$deb" Version)"
  [ "$ver" = "${tag#v}" ] || fail "$name hat Version $ver, das Release ist $tag"
  echo "geprüft: $name ($pkg $ver)" >&2
done
mkdir -p "$out"
cp "${debs[@]}" "$out/"   # erst, wenn alle geprüft sind
echo "$repo $tag"
