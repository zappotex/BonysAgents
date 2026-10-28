# Kursportal-Annahme (Bundle v6 deployt, v7 vorbereitet)

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
    docker compose exec portal python /app/server.py loeschen <ID> art17|rechtsverstoss|abgelaufen|sonstiges <AKTEUR>
    docker compose exec portal python /app/server.py alt <TAGE>      # abgelehnte/zurückgezogene Einreichungen, älter als TAGE

## Löschen (Löschkonzept)

- `loeschen` entfernt Original und Verlauf einer Einreichung endgültig (Anfrage nach Art. 17 DSGVO, Rechtsverstoß, Frist).
  Eine **veröffentlichte** Einreichung muss vorher mit `entscheiden … withdrawn` zurückgezogen werden.
- Im Löschprotokoll (`ablage/geloescht.jsonl`) bleiben nur Zeit, Einreichungs-ID, fester Grund und Akteur –
  keine Namen und keine Texte aus dem Paket. Der Grund ist aus einer festen Liste, damit kein Freitext Personendaten enthält.
- Frist-Vorschlag (Entscheidung Bony): abgelehnte und zurückgezogene Einreichungen nach 90 Tagen mit `alt 90` suchen
  und mit Grund `abgelaufen` löschen; eine automatische Löschung gibt es bewusst nicht.

Einreichen (Einreicher):

    curl -H "Authorization: Bearer <TOKEN>" --data-binary @paket.bonyspaket https://kurse.bony23.de/einreichen

## Moderation online (ab Bundle v5)

Moderator-Token (getrennt von den Einreicher-Token; nur der SHA-256 liegt auf dem Server):

    docker compose exec portal python /app/server.py moderator-neu "bony"      # Token einmalig anzeigen
    docker compose exec portal python /app/server.py moderator-liste
    docker compose exec portal python /app/server.py moderator-entfernen "bony"
    docker compose exec portal python /app/server.py token-liste               # Einreicher (nur Namen)
    docker compose exec portal python /app/server.py token-entfernen "autor-name"

Schnittstelle (Moderator-Token als `Authorization: Bearer …`; Einreicher-Token → 403):

    GET  /moderation/liste
    GET  /moderation/einreichung/<ID>          # Bericht und Verlauf, ohne Fundwerte, mit kette_ok
    POST /moderation/entscheiden/<ID>          # {"nach": "approved|rejected|published|withdrawn", "begruendung": "…"}
    GET  /moderation/original/<ID>             # Paketdatei zum Ansehen (nur bei passender Prüfsumme)

Der Akteur im Verlauf ist der Name des Moderator-Tokens. In der App (Kursleiter-Edition): „Kursportal: Moderation …“ →
„Online (Kursportal)“. Limits: 10 Fehlversuche/Minute, 60 Anfragen/Minute, 10 Downloads/Minute je Moderator.

## Katalog (ab Bundle v3)

    docker compose exec portal python /app/server.py entscheiden <ID> approved <AKTEUR> "<Begründung>"
    docker compose exec portal python /app/server.py entscheiden <ID> published <AKTEUR> "<Begründung>"   # schreibt den Katalog
    docker compose exec portal python /app/server.py katalog     # Katalog neu schreiben (z. B. nach einer Störung)

Öffentlich: `https://kurse.bony23.de/katalog/index.json` und `…/katalog/pakete/<id>-<version>.bonyspaket`. Es erscheint
nur die neueste veröffentlichte Version je Paket-ID. IDs der mitgelieferten Pakete werden bei der Einreichung abgelehnt.

## Rechtstexte (ab Bundle v7)

Caddy liefert `https://kurse.bony23.de/datenschutz`, `/impressum`, `/einreichungsbedingungen` und `/meldeweg` aus dem
Ordner `rechtstexte/` im Projektverzeichnis auf dem Server (`rechtstexte/<seite>.html`, nur lesend eingebunden). Die
**fertigen Texte legt der Betreiber selbst dort ab** (Name, Anschrift und Hoster gehören nicht ins Repository). Fehlt eine
Seite, legt `deploy.sh` nur eine Platzhalterseite („wird gerade vorbereitet“) an; vorhandene Dateien überschreibt es nie,
und das Bundle enthält den Ordner nicht. Entwürfe: `docs/recht/kursportal/`. Die App verlinkt die Datenschutzerklärung
im Zustimmungsdialog und im Katalogfenster (`kurspaket.DATENSCHUTZ_URL`). Neue Seiten brauchen keinen Neustart.
