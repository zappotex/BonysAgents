# Prüfliste: Sicherheit des Kursportal-Annahme-Servers

Stand: 28.10.2026 · für Bonys Sicherheitsprüfung vor dem ersten echten Einreicher-Token.
Gegenstand: Dienst `portal` und die Route `kurse.bony23.de` im Stack `bonys-schulung-web` (Bundle v4).
Quellen: `packaging/kursportal-server/` (`portal_server.py`, `stack/docker-compose.yml`, `stack/Caddyfile`,
`stack/portal/Dockerfile`), `src/bonys_agents/kurspaket.py` (`entpacken`), `kurspaket_portal.py`, `kurspaket_moderation.py`,
`kurspaket_katalog.py`.

Bis diese Liste abgearbeitet ist, gibt es **kein Einreicher-Token** (`tokens.json` ist leer). Pakete sind Daten:
nichts aus einem Paket wird ausgeführt.

## 1. Was der Server mit einer fremden Datei macht

Annahme → Größenprüfung → Ablage als Original → `entpacken()` in ein temporäres Verzeichnis (tmpfs) → `laden()` und
Geheimnissuche → Bericht (ohne Fundwerte) → Status `approved`, `needs_review` oder `rejected`. Veröffentlicht wird nur durch
einen Menschen per `entscheiden … published`.

## 2. Prüfpunkte (mit Fundstelle und Erwartung)

| # | Prüfpunkt | Erwartung | Wo prüfen |
|---|---|---|---|
| 1 | Container ohne Internet | `portal` hängt nur in `portal_intern` (`internal: true`) | `docker-compose.yml`, `docker network inspect` |
| 2 | Dateisystem schreibgeschützt, nur `/tmp` (600 MB), `/data`, `/katalog` beschreibbar | `read_only: true`, tmpfs | Compose |
| 3 | Keine Rechte | `cap_drop: ALL`, `no-new-privileges`, Nutzer `nobody` | Compose, Dockerfile |
| 4 | Ressourcen begrenzt | 768 MB RAM, 1 CPU, 128 Prozesse | Compose |
| 5 | Nur Caddy erreicht den Dienst | kein `ports:` am `portal` | Compose |
| 6 | Nur `POST /einreichen` kommt durch | alles andere 404/405; Body höchstens 51 MB | `Caddyfile`, `curl` |
| 7 | Anmeldung nur per Token, nur SHA-256 gespeichert | `tokens.json` Rechte 600, Vergleich mit `hmac.compare_digest` | `portal_server.py`, `ls -l` im Volume |
| 8 | Limits | 50 MiB/Datei, 5/h und 20/Tag je Token, 60/h gesamt, 2 GiB Speicher, 20 Fehlversuche/Minute | `portal_server.py` |
| 9 | Entpacken | Pfadausbruch, absolute Pfade, Verweise/Sonderdateien, verschlüsselte ZIPs, 2000 Einträge, Tiefe 8, 200 MB gesamt (echte Bytes gezählt), Endungs-Whitelist | `kurspaket.entpacken`, Tests in `test_kurspaket.py` / `test_kurspaket_portal.py` |
| 10 | Keine Ausführung | kein `subprocess`/`exec` mit Paketinhalt im Portal-Pfad | `grep -n "subprocess\|os.system\|exec(" src/bonys_agents/kurspaket*.py` |
| 11 | Katalog nur lesend ausgeliefert | Caddy hängt `katalog_public` `:ro`; `attachment`, `nosniff`, keine Verzeichnisliste | Compose, Caddyfile, `curl` |
| 12 | Nichts Privates im Katalog | nur bereinigte Metadaten; kein Autor, kein Bericht, keine Fundstellen | `kurspaket_katalog.py` |
| 13 | Reservierte IDs | mitgelieferte IDs werden bei Einreichung abgelehnt und beim Veröffentlichen nie ausgeliefert | `reservierte_ids.json`, Tests |
| 14 | Verlauf manipulationssicher | hashverkettet, menschlicher Akteur + Begründung Pflicht | `kurspaket_moderation.py` |
| 15 | Keine Zugriffsprotokolle mit IPs im Portal | `log_message` unterdrückt; Caddy-Zugriffslog ist nicht eingeschaltet | `portal_server.py`, `Caddyfile` |

## 3. Selbst nachprüfen (nur lesend)

    curl -s -o /dev/null -w "%{http_code}\n" -X POST https://kurse.bony23.de/einreichen                     # 401
    curl -s -o /dev/null -w "%{http_code}\n" https://kurse.bony23.de/katalog/pakete/                        # 404
    curl -s -o /dev/null -w "%{http_code}\n" -X POST https://kurse.bony23.de/katalog/index.json             # 405
    curl -s https://kurse.bony23.de/katalog/index.json                                                       # Katalog (derzeit leer)
    docker compose ps                                  # portal, counter, web laufen
    docker compose exec portal id                      # uid=65534 (nobody)
    docker compose exec portal sh -c 'touch /app/x'    # muss scheitern (read-only)
    docker compose exec portal python -c "import urllib.request as u; u.urlopen('https://example.org', timeout=5)"   # muss scheitern (kein Internet)

## 4. Bekannte Schwächen und Restrisiken (von Claude gefunden, nicht behoben)

1. **Entpacken fremder ZIPs auf einem öffentlichen Host.** Abgeschottet, aber die Abschottung ist die einzige Verteidigung
   gegen einen Fehler in Pythons `zipfile` oder in `entpacken()`. Empfehlung: Image regelmäßig neu bauen (Python-Updates).
2. **Fehlversuch-Sperre ist global.** 20 falsche Token pro Minute sperren auch gültige Einreicher (Absicht, aber eine einfache
   Möglichkeit, das Portal lahmzulegen). Ohne Token sind es nur die Bekannten, die einreichen.
3. **Zähler stehen im Arbeitsspeicher.** Ein Neustart des Containers setzt die Stunden-/Tageslimits zurück.
4. **Annahme läuft nacheinander (`_SPERRE`).** Viele gleichzeitige, langsame Uploads halten Verbindungen/Threads offen
   (Schutz: 30-s-Lesezeitlimit, 128 Prozesse, 60 Einreichungen/h gesamt).
5. **Docker-Gruppe ist root-gleichwertig.** Claudes SSH-Zugang (Gruppe `docker`) gehört nach den Arbeiten entfernt.
6. **Moderationsdialog zeigt Paketdaten als Markdown.** Die Anzeige ist nicht eigens gegen Markdown-Tricks gehärtet
   (Links sind abgeschaltet, trotzdem prüfen). In der App-Katalogliste wird dagegen Klartext verwendet.
7. **Ablage wächst bis 2 GiB**, dann antwortet der Dienst 507; es gibt kein automatisches Aufräumen.
8. **Die Portal-Image enthält das ganze Paket `bonys_agents`** (nur das GUI-Verzeichnis ist ausgenommen). Zusätzlicher
   Code, der nicht gebraucht wird, vergrößert die Angriffsfläche; eine schlankere Image wäre möglich.
9. **Rechtliches** (fremde Inhalte hosten, Haftung, Datenschutz der Einreicher-Namen) ist nicht geklärt – siehe Fahrplan
   „Rechtliches zum Server klären“.

## 5. Entscheidungen für Bony

- [ ] Sind die Punkte 1–15 in Ordnung, oder soll etwas verschärft werden (z. B. Seccomp-Profil, schlankere Image)?
- [ ] Welche Restrisiken in Abschnitt 4 sind für den ersten Einsatz mit wenigen bekannten Einreichern vertretbar?
- [ ] Wer bekommt das erste Token, und wer moderiert?
- [ ] Wann wird Claudes SSH-Zugang entfernt?

## 6. Nach der Freigabe

`docker compose exec portal python /app/server.py token-neu "<name>"` (Token einmalig anzeigen, sicher weitergeben,
nie in Dateien oder Chats ablegen).
