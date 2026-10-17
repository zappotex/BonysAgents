# Bony-Netz in Bony's Agents

Stand: Aufgaben 01 (Baustein und Einstellungen) und 02 (Agenten-PCs ins Netz) aus `bony-netz-paket`.

| Was | Wo |
|---|---|
| Gemeinsamer Baustein (wie in Bony's VPN, **nicht hier ändern**) | `src/bony_netz/` (Version in `__init__.py`) |
| Tests des Bausteins (unverändert übernommen) | `tests/test_bony_netz_baustein.py` |
| Logik für Bony's Agents (Zustand, Server wechseln, Instanz anlegen/löschen) | `src/bonys_agents/netz.py` |
| Fenster „Bony-Netz“ (Menü → „Bony-Netz …“) | `src/bonys_agents/gui/netz_dialog.py` |
| Agenten-PCs ins Netz: Schlüssel, Beitritt im Gast, Geräteliste, Entfernen | `src/bonys_agents/netz.py` (unterer Teil) |
| Einrichtungsschritt bzw. Klon-Erststart, Seed-Datei, Vorlagen ohne Tailscale-Identität | `src/bonys_agents/cloudinit.py` |
| Häkchen beim Erstellen | `gui/create_dialog.py`; Netz-Symbol, Kontextmenü, Löschen: `gui/main_window.py` |
| Tests gegen eine Test-Zentrale auf 127.0.0.1 | `tests/test_netz.py` |

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

