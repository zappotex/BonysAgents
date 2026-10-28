#!/usr/bin/env bash
# Baut das Kursportal-Bundle (Overlay für den bestehenden Schulungsseiten-Stack) – deployt wird von Hand.
# Aufruf aus dem Repo-Stamm: packaging/kursportal-server/bundle-bauen.sh [Version]
set -Eeuo pipefail
cd "$(dirname "$0")/../.."
version="${1:-1}"
name="bonys-schulung-web-kursportal-v${version}"
out="${TMPDIR:-/tmp}/${name}"
rm -rf "$out"
mkdir -p "$out/portal"
cp packaging/kursportal-server/stack/{docker-compose.yml,Caddyfile,deploy.sh} "$out/"
cp packaging/kursportal-server/stack/portal/Dockerfile "$out/portal/"
cp packaging/kursportal-server/portal_server.py "$out/portal/server.py"
rsync -a --exclude gui --exclude __pycache__ --exclude trainer --exclude resources src/bonys_agents/ "$out/portal/bonys_agents/"
rsync -a --exclude __pycache__ src/bony_netz/ "$out/portal/bony_netz/"
python3 - "$out/portal/reservierte_ids.json" <<'PY'
import json, pathlib, sys
ids = sorted(json.loads(p.read_text(encoding="utf-8"))["id"] for p in pathlib.Path("kurspakete").glob("*/paket.json"))
pathlib.Path(sys.argv[1]).write_text(json.dumps(ids), encoding="utf-8")
PY
chmod +x "$out/deploy.sh"
tar -C "${TMPDIR:-/tmp}" -czf "${out}.tar.gz" "$name"
sha256sum "${out}.tar.gz"
