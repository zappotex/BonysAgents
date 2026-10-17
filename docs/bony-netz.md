# Bony-Netz in Bony's Agents

Stand: Aufgabe 01 aus `bony-netz-paket` (Baustein und Einstellungen).

| Was | Wo |
|---|---|
| Gemeinsamer Baustein (wie in Bony's VPN, **nicht hier ändern**) | `src/bony_netz/` (Version in `__init__.py`) |
| Tests des Bausteins (unverändert übernommen) | `tests/test_bony_netz_baustein.py` |
| Logik für Bony's Agents (Zustand, Server wechseln, Instanz anlegen/löschen) | `src/bonys_agents/netz.py` |
| Fenster „Bony-Netz“ (Menü → „Bony-Netz …“) | `src/bonys_agents/gui/netz_dialog.py` |
| Tests gegen eine Test-Zentrale auf 127.0.0.1 | `tests/test_netz.py` |

Baustein ersetzen: `src/bony_netz/` und `tests/test_bony_netz_baustein.py` durch die neue Fassung aus dem Paket
überschreiben, in Bony's VPN ebenso. Ruff-Ausnahmen für den Baustein stehen in `pyproject.toml`
(`per-file-ignores`), damit er unverändert bleiben kann. Ausgeliefert wird er im Wheel (`pyproject.toml`) und
in allen PyInstaller-Programmen (.deb, Windows, macOS); `packaging/check-edition.py` prüft, dass er drin ist.

Alle Tests setzen `BONY_NETZ_ORDNER` auf einen Testordner (`tests/conftest.py`) – die echte Anmeldung wird nie
angefasst.

## Notizen zum Baustein (0.1.0) – nicht hier angepasst

- `Zentrale._anfrage()` wirft bei einer Antwort, die kein JSON ist (z. B. eine Webseite mit Status 200),
  einen rohen `json.JSONDecodeError` statt `ZentraleFehler`/`NetzFehler`. Ebenso ein `KeyError`, wenn
  `instanz_registrieren()` kein `token` bekommt. `bonys_agents.netz` fängt das ab und meldet „Unter … antwortet
  kein Bony-Netz-Server“. Besser wäre es im Baustein selbst (für Bony's VPN genauso).
- `info()` prüft nicht, ob wirklich eine Zentrale antwortet (Felder `server_name`, `login_server`) – macht hier
  `netz.server_info()`.
- `test_baustein.py` und die Module haben keine SPDX-Lizenzzeile; ruff meldet E501 (Zeile im Skript) und UP037.
