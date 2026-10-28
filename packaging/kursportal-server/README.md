# Kursportal-Annahme (Entwurf, nicht deployt)

Zusätzlicher Dienst im bestehenden Docker-Stack der Schulungsseite. Er nimmt `.bonyspaket`-Dateien an, prüft sie mit
`kurspaket_portal` (Daten, nie Skripte ausführen) und legt Original und hashverkettetem Verlauf in einem Volume ab.
Veröffentlicht wird nichts; Entscheidungen trifft Bony per Kommando.

- Neue Domain: `kurse.bony23.de` (eigener Ursprung, getrennt von `schulung.bony23.de`) – **A-Eintrag vorher anlegen**.
- Dienst `portal` hängt nur im internen Netz `portal_intern` (kein Internetzugang), Dateisystem schreibgeschützt,
  `/tmp` als tmpfs, 768 MB RAM, 1 CPU, `cap_drop: ALL`, Nutzer `nobody`.
- Anmeldung per Einladungs-Token (auf dem Server nur der SHA-256). Grenzen: 50 MiB je Datei, 5/Stunde und 20/Tag je
  Einreicher, 60/Stunde gesamt, 2 GiB Speicher, 20 Fehlversuche/Minute.

## Bundle bauen (lokal)

    packaging/kursportal-server/bundle-bauen.sh 1     # erzeugt $TMPDIR/bonys-schulung-web-kursportal-v1.tar.gz

Das Bundle ist ein Overlay: `docker-compose.yml`, `Caddyfile`, `deploy.sh` und `portal/`. Das Verzeichnis `site/` bleibt
unberührt. Compose/Caddyfile basieren auf Bundle v16 der Schulungsseite – bei neuerem Stand vorher angleichen.

## Auf den Server (von Hand)

    scp -P <SSH-PORT> bonys-schulung-web-kursportal-v1.tar.gz <BENUTZER>@<SERVER>:~/

    cd ~
    tar -xzf bonys-schulung-web-kursportal-v1.tar.gz \
      -C bonys-schulung-web \
      --strip-components=1
    cd bonys-schulung-web
    chmod +x deploy.sh
    ./deploy.sh

## Betrieb

    docker compose exec portal python /app/server.py token-neu "autor-name"   # Token einmalig anzeigen, weitergeben
    docker compose exec portal python /app/server.py liste
    docker compose exec portal python /app/server.py zeige <ID>
    docker compose exec portal python /app/server.py entscheiden <ID> approved|rejected|published|withdrawn <AKTEUR> "<Begründung>"

Einreichen (Einreicher):

    curl -H "Authorization: Bearer <TOKEN>" --data-binary @paket.bonyspaket https://kurse.bony23.de/einreichen

## Katalog (ab Bundle v3)

    docker compose exec portal python /app/server.py entscheiden <ID> approved <AKTEUR> "<Begründung>"
    docker compose exec portal python /app/server.py entscheiden <ID> published <AKTEUR> "<Begründung>"   # schreibt den Katalog
    docker compose exec portal python /app/server.py katalog     # Katalog neu schreiben (z. B. nach einer Störung)

Öffentlich: `https://kurse.bony23.de/katalog/index.json` und `…/katalog/pakete/<id>-<version>.bonyspaket`. Es erscheint
nur die neueste veröffentlichte Version je Paket-ID. IDs der mitgelieferten Pakete werden bei der Einreichung abgelehnt.
