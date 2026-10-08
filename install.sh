#!/usr/bin/env bash
# Bony's Agents – Installer für Linux
#
# Installiert alles Nötige (Python, QEMU, Qt-Bibliotheken), richtet die App ein
# und legt einen Eintrag im Anwendungsmenü und auf dem Schreibtisch an.
# Aufruf:  ./install.sh        (fragt einmal nach dem sudo-Passwort)
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
APP_DIR="$DATA/bonys-agents/app"
BIN_DIR="$HOME/.local/bin"

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
fail() { printf '\n\033[1;31mFehler: %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(uname -s)" = "Linux" ] || fail "Dieses Skript ist für Linux. Unter Windows: install.cmd"
[ "$(id -u)" -ne 0 ] || fail "Bitte als normaler Benutzer starten (nicht mit sudo) – das Skript fragt selbst nach."

if [ "$(uname -m)" = "aarch64" ]; then ARCH=aarch64; else ARCH=x86_64; fi

# ---------- 1. Systempakete ----------
say "Installiere Systempakete (Python, QEMU, Qt-Bibliotheken) …"
if command -v apt-get >/dev/null; then
  if [ "$ARCH" = aarch64 ]; then QEMU_PKGS="qemu-system-arm qemu-efi-aarch64"; else QEMU_PKGS="qemu-system-x86"; fi
  sudo apt-get update || echo "Warnung: Paketlisten nicht vollständig aktualisiert – versuche es trotzdem."
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3 python3-venv python3-pip $QEMU_PKGS qemu-system-gui qemu-utils acl \
    libegl1 libgl1 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 \
    libxcb-shape0 libxcb-xinerama0 libxcb-randr0 libxcb-render-util0 libxcb-image0 libdbus-1-3 libfontconfig1
elif command -v dnf >/dev/null; then
  sudo dnf install -y python3 python3-pip qemu-kvm qemu-img qemu-ui-gtk acl \
    mesa-libEGL libxkbcommon-x11 xcb-util-cursor xcb-util-wm xcb-util-keysyms xcb-util-renderutil xcb-util-image
elif command -v pacman >/dev/null; then
  sudo pacman -S --needed --noconfirm python python-pip qemu-desktop acl libxkbcommon-x11 xcb-util-cursor
elif command -v zypper >/dev/null; then
  sudo zypper --non-interactive install python3 python3-pip qemu-x86 qemu-tools qemu-ui-gtk acl \
    libxkbcommon-x11-0 libxcb-cursor0
else
  fail "Kein unterstützter Paketmanager gefunden (apt, dnf, pacman, zypper)."
fi

# ---------- 2. Zugriff auf KVM ----------
say "Richte Hardware-Virtualisierung (KVM) ein …"
if [ ! -e /dev/kvm ]; then
  sudo modprobe kvm_intel 2>/dev/null || sudo modprobe kvm_amd 2>/dev/null || true
fi
if [ -e /dev/kvm ]; then
  getent group kvm >/dev/null || sudo groupadd -r kvm
  sudo usermod -aG kvm "$USER"
  sudo setfacl -m "u:$USER:rw" /dev/kvm || true
else
  echo "Hinweis: /dev/kvm fehlt – bitte Virtualisierung (Intel VT-x / AMD-V) im BIOS/UEFI einschalten."
fi

# ---------- 3. App installieren ----------
say "Installiere Bony's Agents nach $APP_DIR …"
python3 -m venv "$APP_DIR"
"$APP_DIR/bin/python" -m pip install --upgrade pip >/dev/null
"$APP_DIR/bin/python" -m pip install "$SRC"

mkdir -p "$BIN_DIR"
ln -sf "$APP_DIR/bin/bonys-agents" "$BIN_DIR/bonys-agents"

# ---------- 4. Menüeintrag und Schreibtisch ----------
say "Lege Verknüpfungen an …"
ICON_DIR="$DATA/icons/hicolor/256x256/apps"
mkdir -p "$ICON_DIR" "$DATA/applications"
cp "$SRC/src/bonys_agents/resources/icon.png" "$ICON_DIR/bonys-agents.png"
rm -f "$DATA/icons/hicolor/scalable/apps/bonys-agents.svg"  # altes Icon (bis 0.2.0)
DESKTOP_FILE="$DATA/applications/bonys-agents.desktop"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Bony's Agents
Comment=Virtuelle Agent-PCs mit Brave, Telegram und Hermes Agent
Exec=$APP_DIR/bin/bonys-agents-gui
Icon=bonys-agents
Terminal=false
Categories=System;Emulator;
EOF
DESK="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
if [ -d "$DESK" ]; then
  cp "$DESKTOP_FILE" "$DESK/"
  chmod +x "$DESK/bonys-agents.desktop"
  gio set "$DESK/bonys-agents.desktop" metadata::trusted true 2>/dev/null || true
fi
update-desktop-database "$DATA/applications" 2>/dev/null || true

# ---------- 5. Abschlussprüfung ----------
say "Prüfe das System …"
"$APP_DIR/bin/bonys-agents" doctor || true

cat <<EOF

Fertig! Bony's Agents findest du jetzt
  • im Anwendungsmenü und auf dem Schreibtisch („Bony's Agents“)
  • im Terminal als:  bonys-agents

EOF
if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
  read -r -p "Jetzt starten? (J/n) " answer || answer=n
  case "${answer:-j}" in
    [nN]*) ;;
    *) nohup "$APP_DIR/bin/bonys-agents-gui" >/dev/null 2>&1 & ;;
  esac
fi
