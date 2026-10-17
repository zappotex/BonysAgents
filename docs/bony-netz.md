# Bony-Netz in Bony's Agents

Stand: Aufgaben 01 (Baustein und Einstellungen), 02 (Agenten-PCs ins Netz) und 04 (Kurse verwalten) aus
`bony-netz-paket`. Aufgabe 03 steht in Bony's VPN.

| Was | Wo |
|---|---|
| Gemeinsamer Baustein (wie in Bony's VPN, **nicht hier ändern**) | `src/bony_netz/` (Version in `__init__.py`) |
| Tests des Bausteins (unverändert übernommen) | `tests/test_bony_netz_baustein.py` |
| Logik für Bony's Agents (Zustand, Server wechseln, Instanz anlegen/löschen) | `src/bonys_agents/netz.py` |
| Fenster „Bony-Netz“ (Menü → „Bony-Netz …“) | `src/bonys_agents/gui/netz_dialog.py` |
| Agenten-PCs ins Netz: Schlüssel, Beitritt im Gast, Geräteliste, Entfernen | `src/bonys_agents/netz.py` (unterer Teil) |
| Einrichtungsschritt bzw. Klon-Erststart, Seed-Datei, Vorlagen ohne Tailscale-Identität | `src/bonys_agents/cloudinit.py` |
| Häkchen beim Erstellen | `gui/create_dialog.py`; Netz-Symbol, Kontextmenü, Löschen: `gui/main_window.py` |
| Kurse (Aufgabe 04): Logik ohne Qt | `src/bonys_agents/kurse.py` |
| Fenster „Kurse“ (Knopf im Kopf), Reiter „Teilnahme“ | `src/bonys_agents/gui/kurse_dialog.py` |
| Reiter „Kursleitung“, „Neuer Kurs“, Kursansicht (nur Kursleiter-Version) | `src/bonys_agents/trainer/gui/kurse_leiten.py` |
| „Der Kurs X hat begonnen“ | `gui/main_window.py` (`_check_kurse`) |
| Tests gegen eine Test-Zentrale auf 127.0.0.1 (mit Kurs-Endpunkten) | `tests/test_netz.py`, `tests/test_kurse.py` |

Baustein ersetzen: `src/bony_netz/` und `tests/test_bony_netz_baustein.py` durch die neue Fassung aus dem Paket
überschreiben, in Bony's VPN ebenso. Ruff-Ausnahmen für den Baustein stehen in `pyproject.toml`
(`per-file-ignores`), damit er unverändert bleiben kann. Ausgeliefert wird er im Wheel (`pyproject.toml`) und
in allen PyInstaller-Programmen (.deb, Windows, macOS); `packaging/check-edition.py` prüft, dass er drin ist.

Alle Tests setzen `BONY_NETZ_ORDNER` auf einen Testordner (`tests/conftest.py`) – die echte Anmeldung wird nie
angefasst.

## Baustein 0.1.1

Fehler in 0.1.0 (gefunden beim ersten echten Klon mit Bony-Netz, 17.10.2026): Das Beitrittsskript las `/etc/os-release`
direkt ein, dessen `NAME="Debian GNU/Linux"` überschrieb den Gerätenamen – `tailscale up` scheiterte, sobald Tailscale
erst installiert werden musste. In 0.1.1 korrigiert, in beiden Projekten und im Paket (`bony-netz-paket.tar.gz`, die
alte Fassung liegt daneben als `bony-netz-paket-0.1.0.tar.gz`). Betroffene Agent-PCs: Rechtsklick → „Mit dem
Bony-Netz verbinden“ (Tailscale ist dann schon da).

## Notizen zum Baustein (0.1.0) – nicht hier angepasst

- `Zentrale._anfrage()` wirft bei einer Antwort, die kein JSON ist (z. B. eine Webseite mit Status 200),
  einen rohen `json.JSONDecodeError` statt `ZentraleFehler`/`NetzFehler`. Ebenso ein `KeyError`, wenn
  `instanz_registrieren()` kein `token` bekommt. `bonys_agents.netz` fängt das ab und meldet „Unter … antwortet
  kein Bony-Netz-Server“. Besser wäre es im Baustein selbst (für Bony's VPN genauso).
- `info()` prüft nicht, ob wirklich eine Zentrale antwortet (Felder `server_name`, `login_server`) – macht hier
  `netz.server_info()`.
- `test_baustein.py` und die Module haben keine SPDX-Lizenzzeile; ruff meldet E501 (Zeile im Skript) und UP037.

## Aufgabe 02: Agenten-PCs ins Netz – wie es läuft

- Agenten-PCs werden über cloud-init (Seed-ISO, NoCloud) eingerichtet. Neu installiert: Einrichtungsskript mit
  Schritten als Dienst `bonys-provision.service` (darüber kommen auch Brave, Telegram, Hermes). Aus einer Vorlage:
  `bonys-clone-firstboot` über `runcmd`. Der Beitritt nutzt genau diese Wege:
  - neu installiert: **Schritt 2** „Mit dem Bony-Netz verbinden“, gleich nach Sprache/Tastatur (so früh, weil der
    Schlüssel nur 60 Minuten gilt; ein Fehlschlag erscheint wie andere Schritte als „fertig mit Fehlern“),
  - aus einer Vorlage: im Erststart-Skript, vor dem Import einer WireGuard-Konfiguration (Kill-Switch).
- `vm.create(..., bony_netz=True)` holt den Geräteschlüssel erst nach Download und Festplatte, direkt vor dem
  Seed-ISO. Das Beitrittsskript aus `bony_netz.erstbeitritt_skript` liegt nur im Seed-ISO (`bony-netz.sh`, wie
  `bonys-vpn.conf`); das Seed-ISO löscht die App nach der Einrichtung. Im Gast wird es nach
  `/root/bony-netz-beitritt.sh` (700) kopiert, nach fremden apt-Läufen einmal als root ausgeführt und danach
  gelöscht (auch bei einem Fehler). Erledigt: `/var/lib/bonys-agents/bony-netz.done`.
- Netzname (`geraetename(Name des Agent-PCs)`) steht in `vm.json` als `netz_name`; die `geraet_id` wird über den
  Namen in `zentrale.geraete()` gefunden.
- Nachträglich verbinden: über `VM.guest_run` (Gast-Agent, sonst SSH mit Passwort) – das Skript geht base64-kodiert
  über die Standardeingabe. Der Schlüssel wird erst geholt, wenn klar ist, dass der Befehl ankommt.
- Vorlagen: `generalize_script` löscht `/var/lib/tailscale` und die Erledigt-Markierung (nur lokal, kein
  `tailscale logout` – das nähme den Original-Agent-PC aus dem Netz).

### Offen / Hinweise

- Kill-Switch von Bony's VPN: Ist er an, geht ohne WireGuard-Tunnel auch Tailscale nicht ins Internet (der Beitritt
  selbst läuft vorher).
- Wird ein Agent-PC gelöscht, während der Server nicht erreichbar ist, bleibt das Gerät auf dem Server. Ein neuer
  Agent-PC mit demselben Namen bekommt von Headscale dann womöglich einen abgewandelten Namen und erscheint als
  „nicht verbunden“. Eine Geräteliste zum Aufräumen gibt es noch nicht.

## Aufgabe 04: Kurse – wie es mit der Schulung im eigenen Netz zusammenpasst

Die vorhandene Schulung (Vorlage freigeben, „Schulung beitreten“, Vorführen, Hilfe-Schalter) läuft ohne Server direkt
zwischen den Rechnern im selben Netz (LAN oder VPN) mit eigenem Code und Fingerabdruck. Sie bleibt **unverändert**.
Die Kurse über das Bony-Netz kommen daneben:

- Ein Knopf **„Kurse“** (früher „Kurs beitreten“) öffnet das Fenster „Kurse“. Darin „Kursleitung“ (nur
  Kursleiter-Version, Modul in `trainer/` – fehlt in der Anwender-Version ganz) und „Teilnahme“. Der bisherige Weg
  steht unten als „Schulung im Netzwerk beitreten …“ (öffnet `JoinDialog` wie früher).
- Ohne Bony-Netz (aus oder keine Instanz) zeigt das Fenster einen Hinweis mit „Bony-Netz …“ und fragt die Zentrale
  nicht; die Schulung im eigenen Netz geht trotzdem.
- Später (Aufgaben 05/06) sollen Kursraum und Hilfe für Bony-Netz-Kurse dieselben Fenster nutzen: Kursansicht →
  „Kursraum öffnen“, Teilnehmerliste → „Helfen“. Der Hilfe-Schalter im eigenen Netz bleibt für Kurse ohne Internet.

Umsetzung:
- `kurse._aufruf` deutet einen 404 der Zentrale **nicht** als „kein Bony-Netz-Server“ (anders als `netz._fragen`):
  „Code abgelaufen“ kommt als 404 mit Meldung für den Nutzer. Antworten ohne JSON ergeben weiter `KeinBonyNetz`,
  ein 401 meldet die Instanz ab (wie überall).
- Gemerkt in `konto.extra`: `kursleiter_name` (Kursleiter) und `anzeigename` (Teilnehmer). `ist_kursleiter` wird
  nach `instanz()` bzw. dem Einlösen in `konto.json` nachgetragen (sieht auch Bony's VPN).
- Agent-PC-Auswahl: `zentrale.geraete()`, online zuerst. **Ohne** den Rechner selbst, wenn Bony's VPN ihn verbunden
  hat (`konto.extra["vpn_rechner"]`, gleiche Instanz) – sonst könnte ein Teilnehmer dem Kursleiter versehentlich
  den eigenen Rechner öffnen. Neben dem Netznamen steht der Name des Agent-PCs auf diesem Rechner.
- Abfragen: Kursliste und Kursansicht alle 15 s, solange sichtbar; „Teilnahme“ und die Meldung im Hauptfenster
  höchstens jede Minute. Das Hauptfenster fragt beim Start einmal und danach nur weiter, solange es Teilnahmen gibt
  (nach dem Fenster „Kurse“ wieder einmal).
- „Kursraum öffnen/betreten“: Platzhalter (`kurse.KURSRAUM_SPAETER`) bis Aufgabe 05.

### Offen / Hinweise
- Echt zu prüfen (Fertig-wenn): Kurs anlegen, zweiter Rechner mit anderer Instanz tritt bei; nach „Kurs starten“
  `ping` vom Kursleiter (Rechner über Bony's VPN oder Agent-PC) auf genau diesen Agent-PC, nicht auf andere des
  Teilnehmers; nach „Pausieren“/„Beenden“ sofort weg; Teilnehmer untereinander nie. Das regelt die Zentrale
  (Headscale-Regeln) – die App zeigt nur an.
- Was die Zentrale bei einem erneuten Beitritt nach „Entfernen“ tut, steht nicht in API.md; die App zeigt dann
  einfach die Meldung der Zentrale.
