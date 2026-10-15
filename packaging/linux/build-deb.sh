#!/usr/bin/env bash
# Baut das .deb-Paket von Bony's Agents – je Edition (siehe docs/editionen.md):
#
#   packaging/linux/build-deb.sh               -> dist/bonys-agents_<version>_<arch>.deb             (Anwender)
#   packaging/linux/build-deb.sh kursleiter    -> dist/bonys-agents-kursleiter_<version>_<arch>.deb  (Kursleiter)
#
# Wechsel in beide Richtungen per Doppelklick (captain/gdebi) und mit apt: Beide Pakete haben GENAU dieselben
# Dateipfade und ersetzen einander (Replaces, die Kursleiter-Version zusätzlich „Provides: bonys-agents“). dpkg
# entfernt das andere Paket dann selbst („komplett ersetzt“, postrm disappear). Bewusst ohne Conflicts und Breaks – der
# grafische Installer (python-apt) lehnt ein Paket ab, sobald das installierte einen Conflicts-Eintrag dagegen hat
# („Beschädigt vorhandenes Paket“), und Breaks bräuchte bei dpkg -i --auto-deconfigure.
# Damit die Pfade gleich sind, stecken die Kursleiter-Dateien (Seiten der Vorführung, noVNC) in einem Archiv mit
# festem Namen (in der Anwender-Version leer); postinst packt es aus, postrm räumt es weg.
# Agent-PCs, Vorlagen und Einstellungen liegen im Benutzerordner und bleiben.
#
# Voraussetzung: Python 3.10+ mit venv, dpkg-deb. Das Paket enthält Python und Qt
# bereits (PyInstaller), braucht auf dem Zielsystem also kein Python.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

EDITION="${1:-${BONYS_EDITION:-anwender}}"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' src/bonys_agents/__init__.py)"
HOMEPAGE="$(sed -n 's/^REPO_URL = "\(.*\)"/\1/p' src/bonys_agents/__init__.py)"
ARCH="$(dpkg --print-architecture)"
APP="bonys-agents"   # gemeinsame Pfade beider Editionen (/opt, Befehle, Symbol, Paketquelle)
case "$EDITION" in
  anwender)
    PKG="bonys-agents"; OTHER="bonys-agents-kursleiter"; NAME="Bony's Agents"; DIST="dist/bonys-agents"
    RELATIONS="Replaces: $OTHER" ;;
  kursleiter)
    PKG="bonys-agents-kursleiter"; OTHER="bonys-agents"; NAME="Bony's Agents Kursleiter"
    DIST="dist/bonys-agents-kursleiter"
    RELATIONS="Provides: bonys-agents (= $VERSION)
Replaces: $OTHER" ;;
  *) echo "Unbekannte Edition: $EDITION (anwender | kursleiter)" >&2; exit 1 ;;
esac
STAGE="build/deb/${PKG}_${VERSION}_${ARCH}"
OUT="dist/${PKG}_${VERSION}_${ARCH}.deb"

echo "==> Baue $PKG $VERSION für $ARCH ($NAME)"

# ---------- 1. Programm bündeln ----------
if [ ! -x "$DIST/BonysAgents" ] || [ "${REBUILD:-1}" = "1" ]; then
  python3 -m venv build/venv
  if [ "$EDITION" = kursleiter ]; then
    python3 packaging/fetch-novnc.py   # noVNC (MPL-2.0) für die Vorführung, feste Version mit Prüfsumme
  fi
  build/venv/bin/pip install -q --upgrade pip
  build/venv/bin/pip install -q . pyinstaller
  build/venv/bin/pyinstaller --noconfirm --log-level WARN --distpath dist --workpath "build/pyinstaller-$EDITION" \
    packaging/bonys-agents.spec -- --edition "$EDITION"
fi
# Anwender: kein trainer/, kein noVNC – Kursleiter: beides (bricht sonst ab)
build/venv/bin/python packaging/check-edition.py "$DIST" "$EDITION"

# ---------- 2. Paketstruktur ----------
rm -rf "$STAGE"
DOC="$STAGE/usr/share/doc/$APP"   # gleicher Pfad in beiden Editionen (siehe oben)
install -d "$STAGE/DEBIAN" "$STAGE/opt" "$STAGE/usr/bin" \
  "$STAGE/usr/share/applications" "$DOC" \
  "$STAGE/usr/share/icons/hicolor/256x256/apps" "$STAGE/usr/share/icons/hicolor/512x512/apps" \
  "$STAGE/usr/lib/udev/rules.d"

cp -a "$DIST" "$STAGE/opt/$APP"
# Kursleiter-Dateien ins Archiv mit festem Namen (Anwender: leeres Archiv) – siehe oben
PKGDIR="$STAGE/opt/$APP/_internal/bonys_agents"
if [ -d "$PKGDIR/trainer" ]; then
  tar -C "$PKGDIR" --owner=0 --group=0 --sort=name -czf "$PKGDIR/edition-data.tar.gz" trainer
  rm -rf "$PKGDIR/trainer"
else
  tar --owner=0 --group=0 -czf "$PKGDIR/edition-data.tar.gz" -T /dev/null
fi
ln -s "/opt/$APP/bonys-agents" "$STAGE/usr/bin/bonys-agents"
ln -s "/opt/$APP/BonysAgents" "$STAGE/usr/bin/bonys-agents-gui"

install -m644 src/bonys_agents/resources/icon.png "$STAGE/usr/share/icons/hicolor/256x256/apps/$APP.png"
install -m644 src/bonys_agents/resources/logo.png "$STAGE/usr/share/icons/hicolor/512x512/apps/$APP.png"
sed "s/^Name=.*/Name=$NAME/" packaging/linux/bonys-agents.desktop > "$STAGE/usr/share/applications/$APP.desktop"
chmod 644 "$STAGE/usr/share/applications/$APP.desktop"
install -m644 packaging/linux/70-bonys-agents-kvm.rules "$STAGE/usr/lib/udev/rules.d/"

# Bony's VPN ist ein eigenes Paket (bonys-vpn, https://github.com/zappotex/bonys-vpn) – hier nur „Suggests“.
{
  echo "$NAME"
  echo "Copyright (C) 2026 Bony"
  echo "Lizenz: GPL-3.0-or-later (vollständiger Text unten)."
  echo "Mitgelieferte Komponenten und ihre Lizenzen: /usr/share/doc/$APP/THIRD-PARTY-LICENSES"
  echo "Name und Logo „Bony's Agents“ sind von der Lizenz ausgenommen."
  echo
  cat LICENSE
} > "$DOC/copyright"
chmod 644 "$DOC/copyright"
install -m644 THIRD-PARTY-LICENSES "$DOC/THIRD-PARTY-LICENSES"
install -m644 README.md "$DOC/README.md"

# Eigene Paketquelle für Updates über die Aktualisierungsverwaltung – nur, wenn der öffentliche
# Signierschlüssel im Repository liegt (packaging/linux/bonys-agents-archive-keyring.asc, siehe docs/RELEASE.md).
# Die Vorlage legt postinst nach /etc/apt/sources.list.d/, purge entfernt sie wieder. Beide Editionen nutzen
# dieselbe Quelle und denselben Schlüssel.
KEY_ASC="packaging/linux/bonys-agents-archive-keyring.asc"
if [ -s "$KEY_ASC" ]; then
  install -d "$STAGE/usr/share/keyrings" "$STAGE/usr/share/$APP"
  gpg --dearmor < "$KEY_ASC" > "$STAGE/usr/share/keyrings/$APP.gpg"
  chmod 644 "$STAGE/usr/share/keyrings/$APP.gpg"
  PY=build/venv/bin/python; [ -x "$PY" ] || PY=python3
  PYTHONPATH=src "$PY" -c "from bonys_agents import updates; print(updates.apt_sources_text(), end='')" \
    > "$STAGE/usr/share/$APP/$APP.sources"
  chmod 644 "$STAGE/usr/share/$APP/$APP.sources"
  echo "==> Paketquelle: $(grep '^URIs:' "$STAGE/usr/share/$APP/$APP.sources")"
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

if [ "$EDITION" = kursleiter ]; then
  DESCRIPTION="Virtuelle Agent-PCs – Version für Kursleiter (Schulungen)
 Bony's Agents Kursleiter enthält alles aus Bony's Agents und zusätzlich
 die Funktionen für Schulungen: Vorlagen im Netzwerk freigeben, einen
 Agent-PC live im Browser vorführen und Hilfe-Anfragen der Teilnehmer
 annehmen. Teilnehmer brauchen nur das Paket bonys-agents. Ersetzt
 bonys-agents (und umgekehrt) – Agent-PCs und Einstellungen bleiben."
else
  DESCRIPTION="Virtuelle Agent-PCs mit Brave, Telegram und Hermes Agent
 Bony's Agents erstellt per Mausklick einen eigenen virtuellen Rechner
 (Debian 13 mit Cinnamon-Desktop), in dem Brave, Telegram und der
 KI-Agent Hermes fertig eingerichtet sind – sauber getrennt vom
 eigentlichen System. Speicherort frei wählbar, z. B. auf einer externen SSD.
 Für Kursleiter gibt es das Paket bonys-agents-kursleiter."
fi

cat > "$STAGE/DEBIAN/control" <<EOF
Package: $PKG
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Maintainer: Bony <bonys-agents@users.noreply.github.com>
Installed-Size: $SIZE_KB
Depends: $QEMU, qemu-utils, acl, python3, libc6 (>= $GLIBC), libegl1, libgl1, libfontconfig1, libfreetype6,
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
Suggests: bonys-vpn, remmina, remmina-plugin-rdp, remmina-plugin-spice, virt-viewer
$RELATIONS
Homepage: $HOMEPAGE
Description: $DESCRIPTION
EOF

cat > "$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
  # Kursleiter-Dateien (Seiten der Vorführung, noVNC) auspacken – in der Anwender-Version ist das Archiv leer
  D=/opt/bonys-agents/_internal/bonys_agents
  rm -rf "$D/trainer"
  [ -f "$D/edition-data.tar.gz" ] && tar -xzf "$D/edition-data.tar.gz" -C "$D" --no-same-owner
  # Reste von Bony's VPN aus 0.14 (vom Helfer als root angelegte __pycache__, gehören keinem Paket)
  rm -rf /usr/lib/bonys-agents/vpn
  rmdir /usr/lib/bonys-agents 2>/dev/null || true
  # Angemeldete Benutzer bekommen automatisch Zugriff auf KVM (Regel 70-bonys-agents-kvm.rules)
  if command -v udevadm >/dev/null 2>&1; then
    udevadm control --reload-rules 2>/dev/null || true
    udevadm trigger --name-match=kvm 2>/dev/null || true
  fi
  command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q /usr/share/applications || true
  command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t /usr/share/icons/hicolor || true
  # Paketquelle für Updates (Aktualisierungsverwaltung). Hat der Nutzer sie mit „Enabled: no“
  # abgeschaltet, bleibt das so – auch beim Wechsel der Edition (bonys-agents ↔ bonys-agents-kursleiter):
  # Dann hat das alte Paket die Quelle entfernt und sich die Wahl gemerkt.
  SRC=/usr/share/bonys-agents/bonys-agents.sources
  DST=/etc/apt/sources.list.d/bonys-agents.sources
  OFF=/var/lib/bonys-agents/apt-source-disabled
  if [ -f "$SRC" ] && [ -f /usr/share/keyrings/bonys-agents.gpg ]; then
    if [ -f "$DST" ] && grep -qiE '^[[:space:]]*Enabled:[[:space:]]*no' "$DST"; then
      :
    elif [ -f "$OFF" ]; then
      { cat "$SRC"; echo "Enabled: no"; } > "$DST"
      chmod 644 "$DST"
    else
      install -m644 "$SRC" "$DST"
    fi
  fi
  rm -f "$OFF"
  rmdir /var/lib/bonys-agents 2>/dev/null || true
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
# sonst einen Fehler meldet. Bei einem Update („upgrade“) bleibt sie – und ebenso, wenn die andere
# Edition den Schlüssel schon übernommen hat (Wechsel bonys-agents ↔ bonys-agents-kursleiter).
DST=/etc/apt/sources.list.d/bonys-agents.sources
case "$1" in
  remove|purge|disappear) rm -rf /opt/bonys-agents/_internal/bonys_agents/trainer ;;   # ausgepackte Kursleiter-Dateien
esac
case "$1" in
  remove|purge|disappear)
    if [ ! -e /usr/share/keyrings/bonys-agents.gpg ] && [ -f "$DST" ]; then
      if grep -qiE '^[[:space:]]*Enabled:[[:space:]]*no' "$DST"; then   # Wahl merken, falls gleich gewechselt wird
        mkdir -p /var/lib/bonys-agents
        touch /var/lib/bonys-agents/apt-source-disabled
      fi
      rm -f "$DST"
    fi ;;
esac
exit 0
EOF
cat > "$STAGE/DEBIAN/preinst" <<'EOF'
#!/bin/sh
set -e
# Bis 0.14 brachte dieses Paket Bony's VPN mit (Helfer, Kill-Switch-Unit). Seit 0.15 ist es ein eigenes Paket
# (bonys-vpn). Fehlt das, verschwindet der Helfer mit diesem Update – ein eingeschalteter Kill-Switch ließe
# den Rechner ohne Tunnel offline, ohne Programm zum Abschalten. Also vorher abschalten. Tunnel bleiben.
if [ "$1" = "upgrade" ] && dpkg --compare-versions "$2" lt 0.15 \
   && ! dpkg-query -W -f='${db:Status-Status}' bonys-vpn 2>/dev/null | grep -q '^installed$' \
   && [ -x /usr/sbin/bonys-vpn-helper ]; then
  /usr/sbin/bonys-vpn-helper killswitch off >/dev/null 2>&1 || true
fi
exit 0
EOF
chmod 755 "$STAGE/DEBIAN/preinst" "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/postrm"

# ---------- 4. Rechte und Paket ----------
find "$STAGE" -type d -exec chmod 755 {} +
find "$STAGE/opt" -type f -exec chmod 644 {} +
chmod 755 "$STAGE/opt/$APP/BonysAgents" "$STAGE/opt/$APP/bonys-agents"
find "$STAGE/opt" -type f \( -name "*.so*" -o -perm -u+x \) -exec chmod 755 {} + 2>/dev/null || true

mkdir -p dist
dpkg-deb --root-owner-group -Zxz --build "$STAGE" "$OUT" >/dev/null
echo "==> Fertig: $OUT ($(du -h "$OUT" | cut -f1))"
