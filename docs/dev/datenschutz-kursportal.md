# Datenschutz und Recht: Bestandsaufnahme Kursportal

Stand: 28.10.2026 · Auftrag von Bony: „wir müssen das auch alles rechtlich sicher, DSGVO-sicher machen“.
Dies ist eine **technische Bestandsaufnahme, keine Rechtsberatung**. Sie sagt, welche Daten wo anfallen, und
sammelt Fragen, die jemand mit Fachwissen (Datenschutzbeauftragte/r, Anwält/in) bewerten muss.
Der Release 0.28.0 wartet auf Bonys Wunsch, bis die Punkte in Abschnitt 4 (A) erledigt sind (Stand: Standard aus mit Zustimmung umgesetzt, Rest offen).

Gegenstand: die App (Community-Katalog, Moderationsdialog) und der Annahme-Server `kurse.bony23.de`
(`packaging/kursportal-server/`, Sicherheit siehe `pruefliste-kursportal-server.md`).

## 1. Datenflüsse

| # | Vorgang | Personenbezogene Daten | Wo gespeichert | Zweck |
|---|---|---|---|---|
| D1 | App öffnet den Community-Katalog (`GET /katalog/index.json`) | IP-Adresse und User-Agent (Programmname/Version) der anfragenden Person beim Server und beim Hoster | **Nicht gespeichert**: Der Portal-Dienst schreibt keine Anfragedaten (`log_message` unterdrückt), Caddy hat keine Zugriffsprotokollierung (kein `log`-Eintrag im Caddyfile, am Server bestätigt) | Katalogliste ausliefern |
| D2 | App lädt ein Community-Paket (`GET /katalog/pakete/…`) | wie D1 | wie D1 | Paket herunterladen |
| D3 | Einreichung (`POST /einreichen`) | Token-Name der einreichenden Person (Autorreferenz, vom Betreiber vergeben, kann ein Klarname sein); Inhalt und Metadaten der Paketdatei (Feld `autor` in `paket.json`, Texte, Links); IP wird **nicht** gespeichert | `/data/ablage/<ID>/` im Docker-Volume: Original, `verlauf.jsonl` | Annahme und Prüfung |
| D4 | Moderation | Name des Moderators (Token-Name), Begründungen im Verlauf; Zeitpunkte | `verlauf.jsonl`, hashverkettet (unveränderbar gedacht) | Nachvollziehbarkeit der Entscheidung |
| D5 | Veröffentlichung | Name, Beschreibung, Version, Stufe, Dauer, Größe, Prüfsumme des Pakets; **kein** Autor, kein Bericht (Prüfpunkt 12) | `katalog_public` (öffentlich) | Katalog |
| D6 | Token-Verwaltung | nur SHA-256 der Token plus Token-Name | `tokens.json`, `moderatoren.json` (Rechte 600) | Zugang |
| D7 | Moderator-Token auf dem Rechner der Moderation | Token im Klartext in `kursportal-moderator.json` (Rechte 600 unter Linux/macOS, **unter Windows ohne Unix-Rechte**) | lokal | Anmeldung |
| D8 | Docker-Container-Logs | Dienste `web`, `portal`, `counter`: `json-file` ohne Größen-/Alterbegrenzung; im Stichprobenblick nur Caddy-Meldungen zu Zertifikaten, keine IPs | Server | Betrieb |
| D9 | Hoster | verarbeitet den Server; Auftragsverarbeitung, Standort, Logs des Hosters **nicht bekannt** | extern | Hosting |

Nicht erhoben: Cookies, Tracking, Analyse, Konten, E-Mail-Adressen, Zahlungsdaten. Die App sendet keine Kennung
außer dem User-Agent (Programmname und Version).

## 2. Geprüft und bestätigt (28.10.2026)

- Caddy: kein Zugriffsprotokoll konfiguriert (Caddyfile lokal und am Server durchsucht, nur ACME-/Start-Meldungen im Log).
- Portal: keine Verwendung der Client-Adresse außer in Rate-Limits, die nach **Token** und nicht nach IP zählen
  (Sperre bei Fehlversuchen ist global).
- Katalog (D5) enthält keine Angaben zur einreichenden Person.
- Tokens liegen nur als Hash auf dem Server.

## 3. Offen und riskant

1. **Erledigt in der App (28.10.2026, uncommitted): Community-Katalog im Standard aus, Einschalten nur nach einmaliger Zustimmung.** Noch offen dazu: Datenschutzerklärung und Link. Ursprünglicher Befund: Im Standard an ging ohne Zustimmung geht bei jedem Öffnen des Katalogs eine Anfrage an einen
   weiteren Server (IP beim Hoster sichtbar). Es gibt im Katalogfenster nur einen Hinweistext, aber keine
   Datenschutzerklärung dazu. Rechtsgrundlage und Information (Art. 6, 13 DSGVO) sind nicht geklärt.
2. **Keine Datenschutzerklärung, kein Impressum** für `kurse.bony23.de` (im Repository nicht gefunden).
3. **Unveränderbarer Verlauf gegen Recht auf Löschung (Art. 17).** Löschen heißt derzeit den ganzen Einreichungsordner
   entfernen; ein Konzept (Fristen, wer, wie) gibt es nicht. Token-Namen als Klarnamen vermeiden oder Pseudonyme verwenden.
4. **Personendaten in Paketen.** `autor`, Texte und Bilder können Namen, Adressen oder Fotos enthalten. Die Prüfung sucht
   Geheimnisse, nicht Personendaten; veröffentlichte Pakete enthalten diese Texte vollständig.
5. **Urheberrecht und Lizenz.** Die offene Bibliothek steht unter CC BY-SA 4.0; für das Kursportal gibt es keine
   Einreichungsbedingungen (Rechteeinräumung, Zusicherung der Urheberschaft, Freistellung).
6. **Haftung für fremde Inhalte.** Kein Meldeweg für Rechtsverstöße, keine Entfernungsfrist, kein Ansprechpartner
   (Hostinganbieter-Pflichten, DDG/DSA). Technisch ist das Zurückziehen (`withdrawn`) in Sekunden möglich.
7. **Auftragsverarbeitung mit dem Hoster** und Speicherort der Daten (EU?) nicht dokumentiert.
8. **Docker-Logs ohne Rotation.** Keine Personendaten bekannt, aber unbegrenzt; Aufbewahrung sollte begrenzt werden.
9. **Moderator-Token unter Windows** ohne Dateirechte-Schutz (D7).
10. **Verzeichnis der Verarbeitungstätigkeiten** (Art. 30) und gegebenenfalls Datenschutz-Folgenabschätzung: Pflicht
    hängt von Bonys Rolle ab (privat, Verein, Firma) und ist zu klären.

## 4. Maßnahmen (Vorschlag, nichts davon umgesetzt)

**A. Vor Release 0.28.0 (App):**
- [x] Entscheidung Bony (28.10.2026): Community-Katalog **Standard aus** mit einmaliger Information und Zustimmung beim
  ersten Einschalten (umgesetzt: `community_zustimmung`, Test `test_katalog_dialog_community_fragt_vor_dem_ersten_einschalten`).
- [x] Hinweistext im Zustimmungsdialog und im Handbuch: wohin die Anfrage geht und was der Server sieht (umgesetzt).
- [x] Technik für `kurse.bony23.de/datenschutz` (Caddy, Ordner `rechtstexte/`) und Link im Zustimmungs- und Katalogfenster vorbereitet (Bundle v7); der Text selbst kommt von Bony/Fachperson.

**B. Vor dem ersten Einreicher-Token:**
- Einreichungsbedingungen (Urheberschaft, Lizenz CC BY-SA 4.0, keine Personendaten Dritter, Zustimmung zur
  Veröffentlichung und zur Speicherung des Token-Namens).
- Meldeweg für Rechtsverstöße (Mailadresse, Frist) im Impressum; Prozess „Zurückziehen und löschen“ schriftlich festhalten.
- Löschkonzept (Fristen für abgelehnte, zurückgezogene und alte Einreichungen) und ein kleines Server-Kommando dafür.
- [x] Löschkonzept im Server umgesetzt (Kommandos `loeschen`, `alt`, Löschprotokoll; Bundle v6 gebaut, Deploy durch Bony).
- [x] Entwürfe für Datenschutzerklärung, Impressum, Einreichungsbedingungen und Meldeweg: `docs/recht/kursportal/` (Fachperson muss prüfen).
- Pseudonyme als Token-Namen vorgeben.
- Technische Prüfung der Paketmetadaten auf offensichtliche Personendaten (E-Mail-Adressen, Telefonnummern) als Hinweis
  im Prüfbericht (ohne Werte).
- Hoster: Auftragsverarbeitungsvertrag und Standort dokumentieren.

**C. Später:** Docker-Log-Rotation für `web` (Portal ist in Bundle v6 begrenzt: `max-size 5m`, 3 Dateien); Moderator-Token unter Windows im Schlüsselbund des
Systems speichern; Verzeichnis der Verarbeitungstätigkeiten.

## 5. Fragen an eine Fachperson

1. Reicht für den Katalogabruf (IP-Adresse beim Hoster) ein Hinweis plus berechtigtes Interesse, oder braucht es eine Einwilligung?
2. Ist ein hashverketteter Verlauf mit Token-Namen zulässig, wenn Löschung auf Anfrage möglich bleibt?
3. Was muss in Impressum und Datenschutzerklärung stehen, und wer ist Verantwortlicher (Bony privat, Verein, Firma)?
4. Welche Einreichungsbedingungen und welcher Meldeweg sind nötig, um für eingereichte Inhalte nicht selbst zu haften?
5. Genügt CC BY-SA 4.0 als Lizenz für Einreichungen, auch wenn Autoren ihren Namen nicht nennen wollen?
6. **Bony-Netz (Zentrale, Relay, Kursraum):** Besteht eine Meldepflicht bei der Bundesnetzagentur (§ 5 TKG), und welche
   Pflichten folgen aus dem Fernmeldegeheimnis (§ 3 TDDDG)? Weitere Fragen und der Entwurf der Datenschutzerklärung:
   `docs/recht/bony-netz/`.

## 6. Entscheidungen Bony

- [x] Community-Katalog: Standard **aus** mit Zustimmung (Bony, 28.10.2026).
- [x] Verantwortlicher: Bony **privat** (28.10.2026). Das bedeutet unter anderem: Impressum mit Name und ladungsfähiger Anschrift, die Fachperson soll die Texte dafür prüfen.
- [ ] Wer prüft die Texte (Fachperson)?
- [ ] Release 0.28.0 wartet (Bony, 28.10.2026), bis A erledigt ist.
