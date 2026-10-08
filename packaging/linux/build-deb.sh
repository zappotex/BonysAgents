#!/usr/bin/env bash
# Baut das .deb-Paket von Bony's Agents.
#
#   packaging/linux/build-deb.sh            -> dist/bonys-agents_<version>_<arch>.deb
#
# Voraussetzung: Python 3.10+ mit venv, dpkg-deb. Das Paket enthält Python und Qt
# bereits (PyInstaller), braucht auf dem Zielsystem also kein Python.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' src/bonys_agents/__init__.py)"
HOMEPAGE="$(sed -n 's/^REPO_URL = "\(.*\)"/\1/p' src/bonys_agents/__init__.py)"
ARCH="$(dpkg --print-architecture)"
PKG="bonys-agents"
STAGE="build/deb/${PKG}_${VERSION}_${ARCH}"
OUT="dist/${PKG}_${VERSION}_${ARCH}.deb"

echo "==> Baue $PKG $VERSION für $ARCH"

# ---------- 1. Programm bündeln ----------
if [ ! -x dist/bonys-agents/BonysAgents ] || [ "${REBUILD:-1}" = "1" ]; then
  python3 -m venv build/venv
  build/venv/bin/pip install -q --upgrade pip
  build/venv/bin/pip install -q . pyinstaller
  build/venv/bin/pyinstaller --noconfirm --log-level WARN --distpath dist --workpath build/pyinstaller \
    packaging/bonys-agents.spec
fi

# ---------- 2. Paketstruktur ----------
rm -rf "$STAGE"
install -d "$STAGE/DEBIAN" "$STAGE/opt" "$STAGE/usr/bin" \
  "$STAGE/usr/share/applications" "$STAGE/usr/share/doc/$PKG" \
  "$STAGE/usr/share/icons/hicolor/256x256/apps" "$STAGE/usr/share/icons/hicolor/512x512/apps" \
  "$STAGE/usr/lib/udev/rules.d"

cp -a dist/bonys-agents "$STAGE/opt/$PKG"
ln -s "/opt/$PKG/bonys-agents" "$STAGE/usr/bin/bonys-agents"
ln -s "/opt/$PKG/BonysAgents" "$STAGE/usr/bin/bonys-agents-gui"

install -m644 src/bonys_agents/resources/icon.png "$STAGE/usr/share/icons/hicolor/256x256/apps/$PKG.png"
install -m644 src/bonys_agents/resources/logo.png "$STAGE/usr/share/icons/hicolor/512x512/apps/$PKG.png"
install -m644 packaging/linux/bonys-agents.desktop "$STAGE/usr/share/applications/$PKG.desktop"
install -m644 packaging/linux/70-bonys-agents-kvm.rules "$STAGE/usr/lib/udev/rules.d/"
{
  echo "Bony's Agents"
  echo "Copyright (C) 2026 Bony"
  echo "Lizenz: GPL-3.0-or-later (vollständiger Text unten)."
  echo "Mitgelieferte Komponenten und ihre Lizenzen: /usr/share/doc/$PKG/THIRD-PARTY-LICENSES"
  echo "Name und Logo „Bony's Agents“ sind von der Lizenz ausgenommen."
  echo
  cat LICENSE
} > "$STAGE/usr/share/doc/$PKG/copyright"
chmod 644 "$STAGE/usr/share/doc/$PKG/copyright"
install -m644 THIRD-PARTY-LICENSES "$STAGE/usr/share/doc/$PKG/THIRD-PARTY-LICENSES"
install -m644 README.md "$STAGE/usr/share/doc/$PKG/README.md"

# Eigene Paketquelle für Updates über die Aktualisierungsverwaltung – nur, wenn der öffentliche
# Signierschlüssel im Repository liegt (packaging/linux/bonys-agents-archive-keyring.asc, siehe docs/RELEASE.md).
# Die Vorlage legt postinst nach /etc/apt/sources.list.d/, purge entfernt sie wieder.
KEY_ASC="packaging/linux/bonys-agents-archive-keyring.asc"
if [ -s "$KEY_ASC" ]; then
  install -d "$STAGE/usr/share/keyrings" "$STAGE/usr/share/$PKG"
  gpg --dearmor < "$KEY_ASC" > "$STAGE/usr/share/keyrings/$PKG.gpg"
  chmod 644 "$STAGE/usr/share/keyrings/$PKG.gpg"
  PY=build/venv/bin/python; [ -x "$PY" ] || PY=python3
  PYTHONPATH=src "$PY" -c "from bonys_agents import updates; print(updates.apt_sources_text(), end='')" \
    > "$STAGE/usr/share/$PKG/$PKG.sources"
  chmod 644 "$STAGE/usr/share/$PKG/$PKG.sources"
  echo "==> Paketquelle: $(grep '^URIs:' "$STAGE/usr/share/$PKG/$PKG.sources")"
else
  echo "==> Hinweis: $KEY_ASC fehlt – das Paket richtet (noch) keine Paketquelle für Updates ein."
fi

# ---------- 3. Abhängigkeiten je Architektur ----------
case "$ARCH" in
  amd64) QEMU="qemu-system-x86" ;;
  arm64) QEMU="qemu-system-arm, qemu-efi-aarch64" ;;
  *) echo "Nicht unterstützte Architektur: $ARCH" >&2; exit 1 ;;
esac
SIZE_KB="$(du -sk "$STAGE" | cut -f1)"
GLIBC="$(getconf GNU_LIBC_VERSION | cut -d' ' -f2)"  # Bundle läuft ab dieser glibc-Version

cat > "$STAGE/DEBIAN/control" <<EOF
Package: $PKG
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Maintainer: Bony <bonys-agents@users.noreply.github.com>
Installed-Size: $SIZE_KB
Depends: $QEMU, qemu-utils, acl, libc6 (>= $GLIBC), libegl1, libgl1, libfontconfig1, libfreetype6,
 libxkbcommon0, libxkbcommon-x11-0, libxcb-cursor0, libxcb-icccm4, libxcb-keysyms1, libxcb-shape0,
 libxcb-randr0, libxcb-render-util0, libxcb-image0, libxcb-xinerama0, libdbus-1-3,
 libglib2.0-0t64 | libglib2.0-0, libgtk-3-0t64 | libgtk-3-0,
 libmount1, libblkid1, libuuid1, libselinux1, libpcre2-8-0, libudev1, libsystemd0, libcap2, libgcrypt20,
 libgpg-error0, liblz4-1, liblzma5, libzstd1, libbz2-1.0, zlib1g, libstdc++6, libgcc-s1, libffi8,
 libexpat1, libbrotli1, libharfbuzz0b, libfribidi0, libthai0, libdatrie1, libgraphite2-3, libpixman-1-0,
 libpng16-16t64 | libpng16-16, libx11-6, libx11-xcb1, libxau6, libxdmcp6, libbsd0, libmd0, libxcb1,
 libxcb-glx0, libxcb-render0, libxcb-shm0, libxcb-sync1, libxcb-xfixes0, libxcomposite1, libxcursor1,
 libxdamage1, libxext6, libxfixes3, libxi6, libxinerama1, libxrandr2, libxrender1
Recommends: qemu-system-gui, qemu-system-modules-spice, pkexec | policykit-1
Suggests: remmina, remmina-plugin-rdp, remmina-plugin-spice, virt-viewer
Homepage: $HOMEPAGE
Description: Virtuelle Agent-PCs mit Brave, Telegram und Hermes Agent
 Bony's Agents erstellt per Mausklick einen eigenen virtuellen Rechner
 (Debian 13 mit Cinnamon-Desktop), in dem Brave, Telegram und der
 KI-Agent Hermes fertig eingerichtet sind – sauber getrennt vom
 eigentlichen System. Speicherort frei wählbar, z. B. auf einer externen SSD.
EOF

cat > "$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
  # Angemeldete Benutzer bekommen automatisch Zugriff auf KVM (Regel 70-bonys-agents-kvm.rules)
  if command -v udevadm >/dev/null 2>&1; then
    udevadm control --reload-rules 2>/dev/null || true
    udevadm trigger --name-match=kvm 2>/dev/null || true
  fi
  command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q /usr/share/applications || true
  command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t /usr/share/icons/hicolor || true
  # Paketquelle für Updates (Aktualisierungsverwaltung). Hat der Nutzer sie mit „Enabled: no“
  # abgeschaltet, bleibt das so.
  SRC=/usr/share/bonys-agents/bonys-agents.sources
  DST=/etc/apt/sources.list.d/bonys-agents.sources
  if [ -f "$SRC" ] && [ -f /usr/share/keyrings/bonys-agents.gpg ]; then
    if [ -f "$DST" ] && grep -qiE '^[[:space:]]*Enabled:[[:space:]]*no' "$DST"; then
      :
    else
      install -m644 "$SRC" "$DST"
    fi
  fi
  # Ältere Installation aus install.sh hat im Startmenü und PATH Vorrang vor diesem Paket.
  for h in /root /home/*; do
    if [ -e "$h/.local/share/bonys-agents/app/bin/bonys-agents" ]; then
      echo "WARNUNG: Ältere Installation von Bony's Agents in $h/.local/share/bonys-agents/app" >&2
      echo "  Startmenü und Terminal starten dort womöglich weiter die alte Version. Entfernen mit:" >&2
      echo "  rm -rf ~/.local/share/bonys-agents/app ~/.local/bin/bonys-agents ~/.local/share/applications/bonys-agents.desktop" >&2
    fi
  done
fi
exit 0
EOF

cat > "$STAGE/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
# Die Agent-PCs der Benutzer werden bewusst NICHT gelöscht.
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q /usr/share/applications || true
# Entfernen bzw. vollständig entfernen (purge): auch die Paketquelle für Updates. Schon beim
# einfachen Entfernen, weil dann der Schlüssel unter /usr/share/keyrings fehlt und „apt update“
# sonst einen Fehler meldet. Bei einem Update („upgrade“) bleibt sie.
case "$1" in
  remove|purge) rm -f /etc/apt/sources.list.d/bonys-agents.sources ;;
esac
exit 0
EOF
chmod 755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/postrm"

# ---------- 4. Rechte und Paket ----------
find "$STAGE" -type d -exec chmod 755 {} +
find "$STAGE/opt" -type f -exec chmod 644 {} +
chmod 755 "$STAGE/opt/$PKG/BonysAgents" "$STAGE/opt/$PKG/bonys-agents"
find "$STAGE/opt" -type f \( -name "*.so*" -o -perm -u+x \) -exec chmod 755 {} + 2>/dev/null || true

mkdir -p dist
dpkg-deb --root-owner-group -Zxz --build "$STAGE" "$OUT" >/dev/null
echo "==> Fertig: $OUT ($(du -h "$OUT" | cut -f1))"
