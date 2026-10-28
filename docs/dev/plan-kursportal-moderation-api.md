# Entwurf: Moderations-Schnittstelle (Online-Moderation im Dialog)

Stand: 28.10.2026
Status: **Entschieden 28.10.2026 (Abschnitt 8), Phase 1 in Arbeit.** Setzt `plan-kursportal.md` und `plan-kursportal-katalog.md` voraus.
Jede Server-Änderung wird als Bundle gebaut, das Bony selbst deployt.

## 1. Ausgangslage

- Der Annahme-Server (`portal_server.py`, Dienst `portal` hinter Caddy) hat genau **einen** HTTP-Pfad: `POST /einreichen`
  mit Einreicher-Token. Moderiert wird ausschließlich per Kommandozeile im Container (`liste`, `zeige`, `entscheiden`, `katalog`),
  also nur von jemandem mit SSH- und Docker-Zugang.
- Der **Moderationsdialog** in der Kursleiter-Edition (Menü „Kursportal: Moderation …“) arbeitet nur auf einer lokalen Ablage
  dieses Rechners. Er sieht die Online-Einreichungen nicht und ändert den Online-Katalog nicht.
- Folgen: Moderation setzt Serverzugang voraus (breite Rechte, siehe Prüfliste Punkt „Docker-Gruppe ist root-gleichwertig“),
  ist unbequem und der Akteur im Verlauf ist ein frei eingetippter Text.

## 2. Ziel

Eine Moderatorin oder ein Moderator öffnet den vorhandenen Dialog, wählt „Online“, sieht die Einreichungen des Servers mit
Prüfbericht und Verlauf und trifft Entscheidungen (freigeben, ablehnen, veröffentlichen, zurückziehen) – **ohne SSH und ohne
Docker-Rechte**. Der Akteur im Verlauf ergibt sich aus dem Moderator-Zugang, nicht aus Freitext.

### Nicht-Ziele

- Keine automatische Veröffentlichung, auch nicht bei `approved` (Veröffentlichungsschranke bleibt).
- Kein Löschen von Einreichungen und keine Änderung des Verlaufs über die Schnittstelle.
- Kein Einreichen über den Moderations-Zugang, keine Token-Verwaltung über HTTP (Token anlegen/entfernen bleibt Server-Befehl).
- Keine Registrierung, keine öffentlichen Konten, kein Moderations-Zugang in der Anwender-Edition.
- Kein Ausführen von Paketinhalten – weder auf dem Server noch im Dialog.

## 3. Schnittstelle (Vorschlag)

Alle Pfade unter `/moderation/` am selben Host `kurse.bony23.de`, nur `GET` und `POST`, JSON, UTF-8, `Cache-Control: no-store`.

| Methode, Pfad | Zweck | Antwort |
|---|---|---|
| `GET /moderation/liste` | alle Einreichungen | `[{id, status, paket_id, name, version, zeit}]`, neueste zuerst, höchstens 500 |
| `GET /moderation/einreichung/<id>` | Bericht + Verlauf | bereinigter Bericht (wie `zeige`, ohne Fundwerte), `verlauf` mit Kettenprüfung |
| `POST /moderation/entscheiden/<id>` | Entscheidung | Body `{"nach": "approved|rejected|published|withdrawn", "begruendung": "…"}` → neues Ereignis |
| `GET /moderation/original/<id>` | Paketdatei zum Ansehen | `application/octet-stream`, `attachment`, nur Phase 4 und nur nach Bonys Ja |

Fehlercodes: `401` kein/falsches Token, `403` Token gehört nicht zu einem Moderator, `404` unbekannte Einreichung, `409` Übergang nicht erlaubt
(Meldung der Moderation, z. B. „Übergang withdrawn -> published ist nicht erlaubt“ oder die Sperre für mitgelieferte IDs), `422` Begründung fehlt/zu
lang, `429` Rate-Limit. Fehlertexte kommen nur aus eigenen, festen Meldungen – kein Echo von Anfragedaten.

Serverseitig gilt weiter alles aus der Moderation: Statusautomat, Pflicht zu Akteur und Begründung, Sperre reservierter IDs,
Katalogabgleich nach `published`/`withdrawn` (ruft `_katalog_abgleichen`).

## 4. Zugang und Sicherheit

**Eigene Moderator-Token**, getrennt von Einreicher-Token: Datei `moderatoren.json` im Datenvolume (Rechte 600), nur SHA-256, Name je
Eintrag (z. B. `bony`). Ein Einreicher-Token öffnet **nie** `/moderation/*` und umgekehrt (403).

- **Akteur kommt vom Token:** `entscheiden` schreibt als Akteur den Moderatornamen, ein Feld im Body wird ignoriert.
- **Eigene Zähler:** Fehlversuche und Rate-Limits für `/moderation/*` getrennt von `/einreichen`, damit weder Einreicher die Moderation
  noch Moderatoren die Annahme ausbremsen (behebt zugleich einen Teil von Prüfliste Punkt 4.2). Vorschlag: 10 Fehlversuche/Minute,
  60 Anfragen/Minute je Token.
- **Schreibzugriff serialisieren:** `entscheiden` und `einreichen` hängen an derselben Ereigniskette. Server-Befehl, Annahme und neue
  Schnittstelle laufen in verschiedenen Prozessen/Threads → **Dateisperre je Einreichung** (`fcntl.flock` auf `verlauf.jsonl`) in
  `Moderation._anhaengen`, sonst können zwei gleichzeitige Entscheidungen die Hashkette brechen. Mit Test (zwei Threads).
- **Nichts Fremdes durchreichen:** Berichtsfelder sind bereits bereinigt (`_bereinigen`, Steuerzeichen, 300 Zeichen). Die Antwort wird
  zusätzlich gegen ein festes Schema gebaut (nur bekannte Felder, Längenlimits). Moderatoren sehen die Autorreferenz des
  Einreichers (interne Referenz, kein Personenname) im Verlauf; der öffentliche Katalog zeigt sie nie.
- **Transport:** nur HTTPS (Caddy), `Content-Security-Policy: default-src 'none'`, `nosniff` wie bisher; Body-Limit für
  `/moderation/entscheiden` klein (16 KiB).
- **Keine Log-Daten:** wie bisher keine IPs oder Anfragedaten im Portal-Log. Entscheidungen stehen im hashverketteten Verlauf.
- **Server-Befehle bleiben:** `moderator-neu <name>`, `moderator-liste`, `moderator-entfernen <name>`; zusätzlich fehlende Gegenstücke für
  Einreicher: `token-liste` (nur Namen), `token-entfernen <name>`. (Beim Aufräumen am 28.10. gab es dafür keinen Befehl.)

### Alternativen zum Token (Entscheidung Bony, Abschnitt 8)

| Variante | Vorteil | Nachteil |
|---|---|---|
| **A. Moderator-Token über HTTPS** (Vorschlag) | einfach, passt zum bestehenden Token-Muster, schnell testbar | Token im Besitz der App/der Person; bei Diebstahl voller Moderationszugriff bis zum Entfernen |
| B. Zusätzlich Client-Zertifikat (mTLS in Caddy) | Zugriff nur von Geräten mit Zertifikat; Code für Zertifikate gibt es (`x509.py`) | mehr Betrieb (Ausstellen/Widerrufen), Caddy-Änderung, schwerer zu testen |
| C. Route nur im Bony-Netz erreichbar | kein öffentlicher Moderationspfad | Server muss im Bony-Netz hängen; Moderation nur mit VPN; mehr Infrastruktur |

Empfehlung: **A jetzt**, mit eigenen Limits; B oder C nachrüsten, wenn mehr als wenige bekannte Moderatoren dazukommen.

## 5. Client (App, Kursleiter-Edition)

- Neues Modul `kurspaket_moderation_client.py` (`urllib`, nur HTTPS, Zeitlimit 20 s, Antwortgröße ≤ 2 MiB, Schema-Prüfung jeder Antwort,
  keine Weiterleitungen auf fremde Hosts). Gleiche Schnittstelle wie `Moderation` (`ids`, `status`, `bericht`, `verlauf`, `entscheiden`), damit der
  Dialog beide Quellen nutzen kann.
- **Dialog:** Umschalter „Lokal / Online“. Online: Moderator-Token wird einmal eingegeben und in einer eigenen Datei mit Rechten 600
  im Datenordner gespeichert (nicht in `settings.json`, nie in Logs, nie in Berichten), mit „Abmelden“.
- **Anzeige als Klartext:** Online-Berichte werden **nicht** als Markdown gerendert (schließt Prüfliste 4.6 für die Online-Quelle).
  Dasselbe sollte später für die lokale Anzeige gelten.
- Knöpfe wie bisher nach `ERLAUBT_MENSCH`; Fehler `409/422/429` als verständliche Meldung, Verbindungsfehler mit „später erneut“.
- Aktualisieren nur auf Knopfdruck oder alle 60 s bei geöffnetem Online-Reiter (keine Hintergrundabfragen, wenn der Dialog zu ist).
- Menüpunkt und Code nur in der Kursleiter-Edition erreichbar.

## 6. Phasen

1. **Server lesend:** `moderatoren.json`, `moderator-*`- und `token-*`-Befehle, `GET /moderation/liste` und `/einreichung/<id>`, Dateisperre,
   getrennte Limits; Caddy-Route. Tests: ohne/falsches/Einreicher-Token, Schema, Limits, parallele Zugriffe, kein Fundwert/Pfad in Antworten.
2. **Server schreibend:** `POST /moderation/entscheiden/<id>`; Akteur vom Token; alle Übergänge und Sperren; Katalogabgleich.
   Tests: erlaubt/verboten, reservierte ID, zwei gleichzeitige Entscheidungen, Hashkette bleibt gültig.
3. **Client und Dialog:** Modul, Umschalter, Token-Speicher, Klartext-Anzeige. Tests offscreen mit Test-Server (wie `test_kursportal_server`).
4. **Original ansehen (optional, nur nach Ja):** `GET /moderation/original/<id>`; Client entpackt mit `kurspaket.entpacken` in ein Temp-Verzeichnis
   und zeigt Texte **als Klartext**, Skripte nur als Text, nie ausführen; Verzeichnis danach löschen.
5. **Bundle v5 + echter Test (Bony deployt):** Moderator anlegen, Einreichung → Online-Dialog → Freigabe → Veröffentlichen → App lädt →
   Rücknahme; dazu Negativtests am echten Server (Einreicher-Token auf `/moderation`, falsches Token, Übergang verboten).

Jede Phase endet mit Fokustests, vollständiger Suite, `ruff` und Eintrag in `docs/coordination/STATUS.md`; erst danach die nächste.

## 7. Risiken

- **Neue öffentliche Angriffsfläche:** Zum ersten Mal gibt es einen öffentlichen Pfad, der Zustände ändert. Gegenmittel: eigene starke Token (256 Bit),
  getrennte Limits, kleine Bodygrenze, nur feste Felder, Schema-Prüfung, Moderator-Entfernung per Befehl, Prüfliste vor dem Deploy erweitern.
- **Gestohlener Moderator-Token:** erlaubt Freigabe/Veröffentlichung. Gegenmittel: Veröffentlichen bleibt eine bewusste Handlung mit Begründung, jeder Schritt
  steht im Verlauf; Variante B/C bei Bedarf; Token bei Verdacht sofort entfernen und Verlauf prüfen.
- **Race Conditions:** siehe Dateisperre. Ohne sie ist die Hashkette gefährdet.
- **Denial of Service der Moderation:** getrennte Zähler verhindern, dass Fehlversuche anderer sie sperren; ein Angreifer mit Netzzugang kann trotzdem
  den Pfad fluten (Caddy-Limit/Rate-Limit-Modul wäre eine spätere Option).
- **Überfrachtung:** Phase 4 (Original ansehen) bringt die meiste Fläche (Entpacken im Client). Deshalb getrennt und optional.

## 8. Entscheidungen (Bony, 28.10.2026)

Alle fünf Fragen mit „ja“ zum Vorschlag beantwortet:

1. Zugang per **Moderator-Token (A)**. 2. Moderator zunächst **nur Bony**. 3. **Phase 4 „Original ansehen“ wird mitgeplant.**
4. Online-Anzeige immer **Klartext**, später auch lokal. 5. Schnittstelle am **selben Host** `kurse.bony23.de`.

Ursprüngliche Fragen:

1. Zugang: **A (Token)** wie vorgeschlagen, oder B (Client-Zertifikat) oder C (nur im Bony-Netz)?
2. Wer sind die Moderatoren (Namen für `moderator-neu`)? Nur Bony zunächst?
3. Phase 4 „Original ansehen“ jetzt mitplanen oder später? (Ohne sie sieht die Moderation nur den Prüfbericht, nicht den Paketinhalt.)
4. Soll die Online-Anzeige im Dialog immer Klartext sein (Vorschlag) – und die lokale ebenfalls?
5. Darf die Schnittstelle am selben Host `kurse.bony23.de` liegen oder soll ein eigener Host/Port her?

## 9. Veröffentlichungsschranke

Dieser Entwurf aktiviert nichts. Jede Phase, die den Server betrifft, wird als Bundle gebaut und von Bony deployt; Veröffentlichungen im Katalog
geschehen nur durch eine menschliche Moderationsentscheidung.
