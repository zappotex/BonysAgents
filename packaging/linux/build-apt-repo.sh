#!/usr/bin/env bash
# Baut aus .deb-Dateien eine signierte APT-Paketquelle – die Release-Pipeline veröffentlicht sie
# auf GitHub Pages (https://<besitzer>.github.io/<repository>/apt/).
#
#   packaging/linux/build-apt-repo.sh <ordner-mit-debs> <ziel>      z. B. … debs site/apt
#
# Signiert wird mit GPG: Schlüssel APT_GPG_KEY_ID (sonst der Standardschlüssel im Schlüsselbund),
# Passphrase optional in APT_GPG_PASSPHRASE. Siehe docs/RELEASE.md.
set -euo pipefail

SRC="$(cd "$1" && pwd)"
OUT="$2"
POOL="pool/main/b/bonys-agents"

rm -rf "$OUT"
mkdir -p "$OUT/$POOL"
cp "$SRC"/bonys-agents_*.deb "$OUT/$POOL/"
cd "$OUT"

for arch in amd64 arm64; do
  dir="dists/stable/main/binary-$arch"
  mkdir -p "$dir"
  apt-ftparchive --arch "$arch" packages pool > "$dir/Packages"
  gzip -9nkf "$dir/Packages"
done

R="APT::FTPArchive::Release"
apt-ftparchive \
  -o "$R::Origin=Bony's Agents" -o "$R::Label=Bony's Agents" \
  -o "$R::Suite=stable" -o "$R::Codename=stable" \
  -o "$R::Architectures=amd64 arm64" -o "$R::Components=main" \
  -o "$R::Description=Bony's Agents – virtuelle Agent-PCs" \
  release dists/stable > Release.tmp
mv Release.tmp dists/stable/Release

GPG=(gpg --batch --yes --pinentry-mode loopback --digest-algo SHA512)
if [ -n "${APT_GPG_PASSPHRASE:-}" ]; then GPG+=(--passphrase "$APT_GPG_PASSPHRASE"); fi
if [ -n "${APT_GPG_KEY_ID:-}" ]; then GPG+=(--local-user "$APT_GPG_KEY_ID"); fi
"${GPG[@]}" --clearsign -o dists/stable/InRelease dists/stable/Release
"${GPG[@]}" --armor --detach-sign -o dists/stable/Release.gpg dists/stable/Release

# Öffentlicher Schlüssel zum Nachprüfen und eine kleine Startseite
EXPORT=(gpg --batch --armor --export)
if [ -n "${APT_GPG_KEY_ID:-}" ]; then EXPORT+=("$APT_GPG_KEY_ID"); fi
"${EXPORT[@]}" > bonys-agents-archive-keyring.asc
cat > index.html <<'EOF'
<!doctype html>
<meta charset="utf-8">
<title>Bony's Agents – Paketquelle</title>
<p>Paketquelle für <b>Bony's Agents</b> (Debian, Ubuntu, Linux Mint).
Das .deb-Paket richtet sie bei der Installation selbst ein – Updates kommen dann über die Aktualisierungsverwaltung.</p>
EOF
echo "==> Paketquelle in $OUT:"
find . -type f | sort
