#!/usr/bin/env bash
# Prüft die beiden .deb-Pakete (Anwender und Kursleiter) darauf, dass der Wechsel per Doppelklick und apt klappt
# und jede Edition das Richtige enthält:
#
#   packaging/linux/check-debs.sh dist/bonys-agents_X_amd64.deb dist/bonys-agents-kursleiter_X_amd64.deb
#
# - genau dieselben Dateipfade (dpkg entfernt das andere Paket dann selbst: „komplett ersetzt“)
# - gegenseitig Replaces, die Kursleiter-Version Provides: bonys-agents, KEIN Conflicts/Breaks
#   (der grafische Installer lehnt sonst mit „Beschädigt vorhandenes Paket“ ab)
# - Anwender: Archiv edition-data.tar.gz leer, nichts aus trainer/, kein noVNC; Kursleiter: alles da
set -euo pipefail

A="$1"
K="$2"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PYTHON:-python3}"
fail() { echo "FEHLER: $*" >&2; exit 1; }

files() { dpkg-deb -c "$1" | awk '$1 !~ /^d/ {print $6}' | sort; }
if ! diff <(files "$A") <(files "$K") >/dev/null; then
  diff <(files "$A") <(files "$K") | head -20 >&2
  fail "Die Pakete haben verschiedene Dateipfade – der Wechsel würde beide installiert lassen."
fi
for deb in "$A" "$K"; do
  for f in Conflicts Breaks; do
    [ -z "$(dpkg-deb -f "$deb" "$f")" ] || fail "$(basename "$deb") hat $f – der grafische Installer lehnt dann ab."
  done
done
[ "$(dpkg-deb -f "$A" Replaces)" = "bonys-agents-kursleiter" ] || fail "Anwender: Replaces: bonys-agents-kursleiter fehlt"
[ "$(dpkg-deb -f "$K" Replaces)" = "bonys-agents" ] || fail "Kursleiter: Replaces: bonys-agents fehlt"
dpkg-deb -f "$K" Provides | grep -q '^bonys-agents (= ' || fail "Kursleiter: Provides: bonys-agents fehlt"
if dpkg-deb -c "$A" | grep -iE 'bonys_agents/trainer|novnc'; then fail "Kursleiter-Teile im Anwender-Paket"; fi

for deb in "$A" "$K"; do
  ed=$([ "$deb" = "$K" ] && echo kursleiter || echo anwender)
  d="$(mktemp -d)"
  dpkg-deb -x "$deb" "$d"
  data="$d/opt/bonys-agents/_internal/bonys_agents/edition-data.tar.gz"
  n=$(tar -tzf "$data" | grep -vc '/$' || true)
  if [ "$ed" = anwender ]; then [ "$n" = 0 ] || fail "Anwender: Archiv nicht leer ($n Dateien)"; fi
  tar -xzf "$data" -C "$(dirname "$data")"   # wie postinst
  "$PY" "$HERE/../check-edition.py" "$d/opt/bonys-agents" "$ed"
  grep -H '^Name=' "$d/usr/share/applications/bonys-agents.desktop"
  rm -rf "$d"
done
echo "Beide Pakete in Ordnung: gleiche Pfade, wechseln sich gegenseitig aus, Inhalt passt zur Edition."
