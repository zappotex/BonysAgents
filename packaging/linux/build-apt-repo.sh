#!/usr/bin/env bash
# Baut aus .deb-Dateien eine signierte APT-Paketquelle – gemeinsam für Bony's Agents (beide Editionen:
# bonys-agents und bonys-agents-kursleiter) und Bony's VPN.
# Der Workflow .github/workflows/apt-repo.yml veröffentlicht sie auf GitHub Pages
# (https://<besitzer>.github.io/<repository>/apt/).
#
#   packaging/linux/build-apt-repo.sh <ordner-mit-debs> <ziel>      z. B. … debs site/apt
#
# Zwei Suiten mit demselben Inhalt (alle Pakete): „stable“ trägt das Paket bonys-agents ein, „bonys-vpn“
# das Paket bonys-vpn. Zwei Einträge für dieselbe Suite mit verschiedenen „Signed-By“ lehnt apt ab
# („Conflicting values set for option Signed-By“) – so vertragen sich beide Pakete auf einem Rechner.
#
# Signiert wird mit GPG: Schlüssel APT_GPG_KEY_ID (sonst der Standardschlüssel im Schlüsselbund),
# Passphrase optional in APT_GPG_PASSPHRASE. Siehe docs/RELEASE.md.
set -euo pipefail

SRC="$(cd "$1" && pwd)"
OUT="$2"
SUITES="stable bonys-vpn"

rm -rf "$OUT"
mkdir -p "$OUT"
shopt -s nullglob
debs=("$SRC"/*.deb)
[ "${#debs[@]}" -gt 0 ] || { echo "Keine .deb in $SRC" >&2; exit 1; }
for deb in "${debs[@]}"; do
  pkg="$(dpkg-deb -f "$deb" Package)"
  case "$pkg" in bonys-agents|bonys-agents-kursleiter|bonys-vpn|bonys-vpn-agentpc) ;;
    *) echo "Fremdes Paket: $pkg" >&2; exit 1 ;; esac
  mkdir -p "$OUT/pool/main/b/$pkg"
  cp "$deb" "$OUT/pool/main/b/$pkg/"
done
cd "$OUT"

GPG=(gpg --batch --yes --pinentry-mode loopback --digest-algo SHA512)
if [ -n "${APT_GPG_PASSPHRASE:-}" ]; then GPG+=(--passphrase "$APT_GPG_PASSPHRASE"); fi
if [ -n "${APT_GPG_KEY_ID:-}" ]; then GPG+=(--local-user "$APT_GPG_KEY_ID"); fi
R="APT::FTPArchive::Release"
for suite in $SUITES; do
  for arch in amd64 arm64; do
    dir="dists/$suite/main/binary-$arch"
    mkdir -p "$dir"
    apt-ftparchive --arch "$arch" packages pool > "$dir/Packages"   # enthält auch „Architecture: all“
    gzip -9nkf "$dir/Packages"
  done
  apt-ftparchive \
    -o "$R::Origin=Bony's Agents" -o "$R::Label=Bony's Agents" \
    -o "$R::Suite=$suite" -o "$R::Codename=$suite" \
    -o "$R::Architectures=amd64 arm64" -o "$R::Components=main" \
    -o "$R::Description=Bony's Agents und Bony's VPN" \
    release "dists/$suite" > Release.tmp
  mv Release.tmp "dists/$suite/Release"
  "${GPG[@]}" --clearsign -o "dists/$suite/InRelease" "dists/$suite/Release"
  "${GPG[@]}" --armor --detach-sign -o "dists/$suite/Release.gpg" "dists/$suite/Release"
done

# Öffentlicher Schlüssel zum Nachprüfen und eine kleine Startseite
EXPORT=(gpg --batch --armor --export)
if [ -n "${APT_GPG_KEY_ID:-}" ]; then EXPORT+=("$APT_GPG_KEY_ID"); fi
"${EXPORT[@]}" > bonys-agents-archive-keyring.asc
cat > index.html <<'HTML'
<!doctype html>
<meta charset="utf-8">
<title>Bony's Agents und Bony's VPN – Paketquelle</title>
<p>Paketquelle für <b>Bony's Agents</b> und <b>Bony's VPN</b> (Debian, Ubuntu, Linux Mint).
Die .deb-Pakete richten sie bei der Installation selbst ein – Updates kommen dann über die Aktualisierungsverwaltung.</p>
HTML
echo "==> Paketquelle in $OUT:"
find . -type f | sort
