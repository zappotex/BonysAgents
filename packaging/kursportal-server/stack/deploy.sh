#!/usr/bin/env bash
# Deploy-Skript für schulung.bony23.de
# Als Benutzer zappotex im entpackten Projektverzeichnis ausführen.
set -Eeuo pipefail

readonly DOMAIN="schulung.bony23.de"
readonly DOMAIN_KURSE="kurse.bony23.de"

command -v docker >/dev/null 2>&1 || { echo 'Docker fehlt.' >&2; exit 1; }
if docker info >/dev/null 2>&1; then
  DOCKER=(docker)
elif sudo docker info >/dev/null 2>&1; then
  DOCKER=(sudo docker)
else
  echo 'Docker ist für diesen Benutzer nicht erreichbar. sudo wird benötigt.' >&2
  exit 1
fi
"${DOCKER[@]}" compose version >/dev/null 2>&1 || { echo 'Docker Compose fehlt.' >&2; exit 1; }

printf 'Prüfe DNS für %s ...\n' "$DOMAIN"
getent ahostsv4 "$DOMAIN" || printf 'WARNUNG: DNS ist lokal noch nicht auflösbar.\n'
getent ahostsv4 "$DOMAIN_KURSE" || printf 'WARNUNG: DNS für %s ist lokal noch nicht auflösbar (A-Eintrag fehlt?).\n' "$DOMAIN_KURSE"

# Rechtstexte: der Betreiber legt die fertigen Seiten in ./rechtstexte ab; fehlende Seiten bekommen nur einen Hinweis.
mkdir -p rechtstexte
for seite in datenschutz impressum einreichungsbedingungen meldeweg; do
  if [ ! -e "rechtstexte/${seite}.html" ]; then
    printf '<!doctype html><html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>%s</title><body style="font-family:sans-serif;max-width:40em;margin:2em auto;padding:0 1em"><p>Diese Seite wird gerade vorbereitet.</p></body></html>\n' "$seite" > "rechtstexte/${seite}.html"
  fi
done

printf 'Starte Schulungsseite ...\n'
"${DOCKER[@]}" compose pull
"${DOCKER[@]}" compose up -d --build --force-recreate --remove-orphans
"${DOCKER[@]}" compose ps

printf '\nContainerstatus:\n'
"${DOCKER[@]}" compose ps
printf '\nDie öffentliche Prüfung erfolgt nach DNS-Propagation über:\n'
printf '  curl -I https://%s\n' "$DOMAIN"
printf '  curl -I https://%s/healthz\n' "$DOMAIN"
