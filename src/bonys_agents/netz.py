# SPDX-License-Identifier: GPL-3.0-or-later
"""Bony-Netz in Bony's Agents: Server, Instanz und Zustand (Fenster: ``gui/netz_dialog.py``).

Mit der Zentrale spricht der gemeinsame Baustein ``bony_netz`` (derselbe wie in Bony's VPN, unverändert übernommen).
Die Anmeldung liegt in seiner Datei ``konto.json``, die sich beide Apps teilen – deshalb wird sie vor jeder Änderung
frisch geladen, damit eine Änderung aus Bony's VPN nicht überschrieben wird.

Alle Funktionen, die die Zentrale fragen, blockieren bis zu 15 Sekunden: nur im Hintergrund aufrufen.
Ist der Schalter „Bony-Netz verwenden“ aus (Standard), nimmt die App keinen Kontakt zur Zentrale auf.
Das Instanz-Token erscheint nirgends – weder in Texten noch in Fehlermeldungen.

Agenten-PCs im Netz (Aufgabe 02): Kurz vor dem ersten Start holt ``beitritt_vorbereiten`` einen Geräteschlüssel
(einmal nutzbar, 60 Minuten gültig) und erzeugt mit dem Baustein das Beitrittsskript. Es geht wie eine
WireGuard-Konfiguration nur über das Seed-ISO in den Agent-PC (Datei ``SEED_DATEI``) und wird dort von
``gast_beitritt`` einmal als root ausgeführt – bei einem neu installierten Agent-PC als eigener Einrichtungsschritt,
bei einem aus einer Vorlage beim ersten Start. Nachträglich geht es über den Gast-Agent (``nachtraeglich_verbinden``).
Den Schlüssel enthält nur dieses Skript: nicht vm.json, kein Protokoll auf dem Host, keine Meldung.
"""

from __future__ import annotations

import base64
import shlex
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bony_netz import Konto, NetzFehler, Zentrale, ZentraleFehler
from bony_netz.agentenpc import erstbeitritt_skript, geraetename
from bony_netz.konto import server_normalisieren

from bonys_agents.apps import APT_WAIT

if TYPE_CHECKING:
    from bonys_agents.vm import VM

AKTIV = "aktiv"   # Schlüssel in konto.extra

KEINE_VERBINDUNG = "Keine Verbindung zum Server"
ANMELDUNG_UNGUELTIG = "Anmeldung ungültig, bitte Instanz neu anlegen"


class KeinBonyNetz(Exception):
    """Unter der Adresse antwortet etwas, aber kein Bony-Netz-Server (z. B. eine normale Webseite)."""


@dataclass
class Zustand:
    text: str                       # Zustandszeile
    konto: Konto                    # frisch geladen (evtl. mit aktualisiertem Kursleiter-Status oder abgemeldet)
    info: dict = field(default_factory=dict)   # Antwort von /info, leer ohne Verbindung
    verbunden: bool = False
    detail: str = ""                # genauere Fehlermeldung, falls nicht verbunden


def kurz_id(instanz_id: str) -> str:
    return instanz_id[:8]


def aktiv(konto: Konto) -> bool:
    return bool(konto.extra.get(AKTIV))


def aendern(fn: Callable[[Konto], object]) -> Konto:
    """Konto frisch laden, ändern, speichern (OSError, wenn das nicht geht)."""
    konto = Konto.laden()
    fn(konto)
    konto.speichern()
    return konto


def aktiv_setzen(an: bool) -> Konto:
    return aendern(lambda k: k.extra.__setitem__(AKTIV, bool(an)))


def fehlertext(e: BaseException) -> str:
    if isinstance(e, ZentraleFehler):
        return e.meldung
    if isinstance(e, OSError):
        return f"Die Anmeldung ließ sich nicht speichern ({e.strerror or e})."
    return str(e)


def _kein_server(server: str, grund: str = "") -> KeinBonyNetz:
    return KeinBonyNetz(f"Unter {server} antwortet kein Bony-Netz-Server{f' ({grund})' if grund else ''}. "
                        "Bitte die Adresse prüfen.")


def _fragen(server: str, fn: Callable[[], object]):
    """Aufruf der Zentrale. Antwortet dort etwas anderes (Webseite statt JSON, 404), gibt es KeinBonyNetz –
    der Baustein meldet eine Antwort, die kein JSON ist, nicht selbst als Fehler."""
    try:
        return fn()
    except ZentraleFehler as e:
        if e.status in (404, 405):
            raise _kein_server(server, f"Fehler {e.status}") from None
        raise
    except (ValueError, KeyError, TypeError):
        raise _kein_server(server, "unerwartete Antwort") from None


def server_info(server: str) -> dict:
    """``/info`` des Servers – mit Prüfung, dass es wirklich eine Zentrale ist."""
    server = server_normalisieren(server)
    info = _fragen(server, lambda: Zentrale(server).info())
    if not isinstance(info, dict) or not isinstance(info.get("server_name"), str):
        raise _kein_server(server, "unerwartete Antwort")
    return info


def zustand() -> Zustand:
    """Server fragen und – falls angemeldet – die Instanz. Wirft nicht: Fehler stehen im Ergebnis.

    Ist die Anmeldung ungültig (Instanz auf dem Server gelöscht), wird sie hier verworfen.
    """
    konto = Konto.laden()
    try:
        info = server_info(konto.server)
        if konto.angemeldet:
            instanz = _fragen(konto.server, lambda: Zentrale(konto.server, konto.token).instanz())
            if not isinstance(instanz, dict):
                raise _kein_server(konto.server, "unerwartete Antwort")
            kursleiter = bool(instanz.get("ist_kursleiter"))
            if kursleiter != konto.ist_kursleiter:
                alt = konto.instanz_id

                def merken(k: Konto) -> None:
                    if k.instanz_id == alt:
                        k.ist_kursleiter = kursleiter

                try:
                    konto = aendern(merken)
                except OSError:
                    konto.ist_kursleiter = kursleiter
        return Zustand(f"Verbunden mit {info['server_name']}", konto, info, verbunden=True)
    except NetzFehler as e:
        return Zustand(KEINE_VERBINDUNG, konto, detail=str(e))
    except ZentraleFehler as e:
        if not e.anmeldung_ungueltig:
            return Zustand(e.meldung, konto, detail=e.meldung)
        alt = konto.instanz_id
        try:   # nur diese Instanz verwerfen – Bony's VPN könnte inzwischen eine neue angelegt haben
            konto = aendern(lambda k: k.abmelden() if k.instanz_id == alt else None)
        except OSError:
            pass
        return Zustand(ANMELDUNG_UNGUELTIG, konto, detail=e.meldung)
    except KeinBonyNetz as e:
        return Zustand(str(e), konto, detail=str(e))


def server_wechseln(adresse: str) -> Zustand:
    """Neuen Server prüfen und erst dann übernehmen (eine Anmeldung beim alten wird dabei verworfen).

    Wirft NetzFehler, ZentraleFehler oder KeinBonyNetz, wenn der neue Server nicht taugt – der alte bleibt dann.
    """
    adresse = server_normalisieren(adresse)
    server_info(adresse)
    aendern(lambda k: k.server_wechseln(adresse))
    return zustand()


def instanz_anlegen(server: str) -> Konto:
    """Neue Instanz beim Server anlegen und sofort speichern.

    Hat Bony's VPN inzwischen schon eine angelegt, wird keine zweite angelegt.
    """
    konto = Konto.laden()
    if konto.server != server_normalisieren(server):
        raise RuntimeError("Der Server wurde inzwischen geändert – bitte das Fenster neu öffnen.")
    if konto.angemeldet:
        return konto
    registrierung = _fragen(konto.server, lambda: Zentrale(konto.server).instanz_registrieren())
    konto.uebernehmen(registrierung)
    konto.speichern()
    return konto


def instanz_loeschen() -> Konto:
    """Instanz auf dem Server löschen (mit allen Agenten-PCs im Netz, Kursen und Teilnahmen), dann abmelden.

    Gibt es sie auf dem Server schon nicht mehr, wird nur abgemeldet.
    """
    konto = Konto.laden()
    if konto.angemeldet:
        try:
            _fragen(konto.server, lambda: Zentrale(konto.server, konto.token).instanz_loeschen())
        except ZentraleFehler as e:
            if not e.anmeldung_ungueltig:
                raise
    alt = konto.instanz_id
    return aendern(lambda k: k.abmelden() if k.instanz_id == alt else None)


# ---------------------------------------------------------------- Agenten-PCs im Netz (Aufgabe 02)
SEED_DATEI = "bony-netz.sh"                        # Name im Seed-ISO (neben user-data)
GAST_SKRIPT = "/root/bony-netz-beitritt.sh"        # dort läuft das Beitrittsskript; es löscht sich danach selbst
GAST_FERTIG = "/var/lib/bonys-agents/bony-netz.done"
GAST_PROTOKOLL = "/var/log/bony-netz-beitritt.log"  # schreibt das Beitrittsskript selbst
SCHRITT_ID = "bony-netz"                           # Schlüssel in „BONYS-FAILED …“ (keine App)
SCHRITT_TITEL = "Mit dem Bony-Netz verbinden"
# Meldung an die App beim ersten Start aus einer Vorlage – Format wie cloudinit.FAILED_MARKER
FEHLER_ZEILE = f"BONYS-FAILED 0/0 {SCHRITT_ID} {SCHRITT_TITEL}"
ABFRAGE_SEKUNDEN = 30                              # Geräteliste höchstens so oft abfragen

IM_NETZ = "im Netz"
OFFLINE = "offline"
NICHT_VERBUNDEN = "nicht verbunden"


def bereit(konto: Konto | None = None) -> bool:
    """Bony-Netz eingeschaltet und eine Instanz angemeldet (ohne den Server zu fragen)."""
    konto = konto or Konto.laden()
    return aktiv(konto) and konto.angemeldet


def _zentrale() -> tuple[Konto, Zentrale]:
    konto = Konto.laden()
    if not bereit(konto):
        raise RuntimeError("Das Bony-Netz ist ausgeschaltet oder es ist keine Instanz angemeldet "
                           "(Menü → „Bony-Netz …“).")
    return konto, Zentrale(konto.server, konto.token)


def _anmeldung_pruefen(konto: Konto, e: ZentraleFehler) -> None:
    """Instanz auf dem Server gelöscht: Anmeldung verwerfen (wie ``zustand``), nur diese Instanz."""
    if e.anmeldung_ungueltig:
        alt = konto.instanz_id
        try:
            aendern(lambda k: k.abmelden() if k.instanz_id == alt else None)
        except OSError:
            pass


@dataclass(frozen=True)
class Beitritt:
    """Beitrittsskript für einen Agent-PC (nur im Speicher; enthält den einmal nutzbaren Geräteschlüssel)."""

    netzname: str
    skript: str = field(repr=False)


def beitritt_vorbereiten(name: str) -> Beitritt:
    """Geräteschlüssel holen und das Beitrittsskript für den Agent-PC ``name`` erzeugen – erst kurz vor dem Start.

    Wirft NetzFehler, ZentraleFehler (409 = Gerätegrenze erreicht, ``meldung`` direkt anzeigbar) oder KeinBonyNetz.
    """
    konto, zentrale = _zentrale()
    try:
        antwort = _fragen(konto.server, zentrale.geraeteschluessel)
    except ZentraleFehler as e:
        _anmeldung_pruefen(konto, e)
        raise
    try:
        login_server = antwort.get("login_server") or konto.login_server
        skript = erstbeitritt_skript(login_server, antwort["schluessel"], name)
    except (AttributeError, KeyError, TypeError, ValueError):
        raise _kein_server(konto.server, "unerwartete Antwort") from None
    return Beitritt(geraetename(name), skript)


def beitritt_mit_hinweis(name: str) -> tuple[Beitritt | None, str]:
    """Wie ``beitritt_vorbereiten``, aber ohne Ausnahme: (Beitritt, "") oder (None, Hinweis für die Oberfläche).

    Ohne Schlüssel wird der Agent-PC ganz normal (ohne Netz) erstellt.
    """
    try:
        return beitritt_vorbereiten(name), ""
    except (NetzFehler, ZentraleFehler, KeinBonyNetz, RuntimeError) as e:
        return None, (f"„{name}“ wird ohne Bony-Netz erstellt: {fehlertext(e)} Verbinden geht später über "
                      "das Kontextmenü in der Liste („Mit dem Bony-Netz verbinden“).")


def geraete() -> dict[str, dict]:
    """Geräte der Instanz nach Netzname. Wirft NetzFehler, ZentraleFehler, KeinBonyNetz oder RuntimeError."""
    konto, zentrale = _zentrale()
    try:
        liste = _fragen(konto.server, zentrale.geraete)
    except ZentraleFehler as e:
        _anmeldung_pruefen(konto, e)
        raise
    if not isinstance(liste, list):
        raise _kein_server(konto.server, "unerwartete Antwort")
    return {g["name"]: g for g in liste if isinstance(g, dict) and isinstance(g.get("name"), str)}


def netz_zustand(netzname: str, liste: dict[str, dict]) -> str:
    """„im Netz“, „offline“ oder „nicht verbunden“ (noch nicht beigetreten bzw. vom Server entfernt)."""
    geraet = liste.get(netzname)
    if geraet is None:
        return NICHT_VERBUNDEN
    return IM_NETZ if geraet.get("online") else OFFLINE


def geraet_entfernen(netzname: str) -> bool:
    """Gerät(e) mit diesem Namen aus dem Netz entfernen. False, wenn es dort keins (mehr) gibt.

    Wirft NetzFehler, ZentraleFehler, KeinBonyNetz oder RuntimeError (Bony-Netz aus).
    """
    konto, zentrale = _zentrale()
    try:
        liste = _fragen(konto.server, zentrale.geraete)
        treffer = [g for g in liste or [] if isinstance(g, dict) and g.get("name") == netzname]
        for g in treffer:
            try:
                _fragen(konto.server, lambda g=g: zentrale.geraet_entfernen(str(g["geraet_id"])))
            except KeinBonyNetz:
                pass   # 404: schon weg
    except ZentraleFehler as e:
        _anmeldung_pruefen(konto, e)
        raise
    return bool(treffer)


def loeschen_hinweis(machine: VM) -> str:
    """Vor dem Löschen eines Agent-PCs: aus dem Bony-Netz entfernen. Gibt einen Hinweis zurück, wenn das nicht ging
    (der Agent-PC wird trotzdem gelöscht), sonst ""."""
    netzname = machine.config.netz_name
    if not netzname:
        return ""
    if not bereit():
        return (f"„{machine.name}“ war im Bony-Netz. Das Bony-Netz ist ausgeschaltet oder abgemeldet – das Gerät "
                f"„{netzname}“ bleibt auf dem Server, bis die Instanz gelöscht wird.")
    try:
        geraet_entfernen(netzname)
    except (NetzFehler, ZentraleFehler, KeinBonyNetz, RuntimeError) as e:
        return (f"„{machine.name}“ ist gelöscht, aber nicht aus dem Bony-Netz entfernt: {fehlertext(e)} Das Gerät "
                f"„{netzname}“ bleibt auf dem Server, bis die Instanz gelöscht wird.")
    return ""


def gast_beitritt(*, aus_seed: bool = True, skript: str = "", console: str | None = None,
                  fertig: str = GAST_FERTIG, ziel: str = GAST_SKRIPT) -> str:
    """Bash (als root im Agent-PC): Beitrittsskript einmal ausführen. Exit-Code 1, wenn der Beitritt scheitert.

    ``aus_seed``: Skript aus dem Seed-ISO (Datei ``SEED_DATEI``, nur lesend eingehängt) – sonst ``skript`` direkt
    (nachträglich über den Gast-Agent, kommt über die Standardeingabe). Wiederholbar: Nach einem erfolgreichen Beitritt
    passiert nichts mehr; das Beitrittsskript prüft außerdem selbst, ob Tailscale schon verbunden ist.
    Fremde apt-Läufe (z. B. apt-daily beim ersten Start eines Klons) werden abgewartet.
    ``console``: Fehlermeldung für die App zusätzlich dorthin. ``fertig``/``ziel`` nur für Tests.
    """
    q_fertig, q_ziel = shlex.quote(fertig), shlex.quote(ziel)
    melden = (f'    echo "{FEHLER_ZEILE}" | tee -a {shlex.quote(console)} >/dev/null' if console else "")
    if aus_seed:
        holen = [
            '  NETZ_MNT="$(mktemp -d)"',
            '  NETZ_DEV="$(blkid -t LABEL=cidata -o device 2>/dev/null | head -n1)"',
            '  [ -n "$NETZ_DEV" ] || NETZ_DEV="$(blkid -t LABEL=CIDATA -o device 2>/dev/null | head -n1)"',
            '  if [ -n "$NETZ_DEV" ] && mount -o ro "$NETZ_DEV" "$NETZ_MNT" 2>/dev/null; then',
            f'    [ -f "$NETZ_MNT/{SEED_DATEI}" ] && install -m 0700 "$NETZ_MNT/{SEED_DATEI}" {q_ziel}',
            '    umount "$NETZ_MNT" 2>/dev/null || true',
            "  fi",
            '  rmdir "$NETZ_MNT" 2>/dev/null || true',
        ]
    else:
        b64 = base64.b64encode(skript.encode("utf-8")).decode("ascii")
        holen = [
            "  (umask 077; base64 -d > " + q_ziel + " <<'BONY_NETZ'",
            *[b64[i:i + 76] for i in range(0, len(b64), 76)],
            "BONY_NETZ",
            "  )",
        ]
    zeilen = [
        "# Bony-Netz: Agent-PC mit dem Netz der Instanz verbinden (Skript aus dem Baustein bony_netz)",
        APT_WAIT,
        "NETZ_RC=0",
        f"if [ -f {q_fertig} ]; then",
        '  echo "Bony-Netz: schon verbunden."',
        "else",
        *holen,
        f"  if [ -f {q_ziel} ]; then",
        '    echo "Bony-Netz: installiere Tailscale aus der offiziellen Paketquelle und verbinde …"',
        "    bonys_apt_wait",
        f"    if bash {q_ziel} </dev/null; then",
        f'      mkdir -p "$(dirname {q_fertig})" && touch {q_fertig}',
        '      echo "Bony-Netz: verbunden als $(tailscale ip -4 2>/dev/null | head -n1)."',
        "    else",
        f'      echo "WARNUNG: Der Beitritt zum Bony-Netz ist fehlgeschlagen – Protokoll: {GAST_PROTOKOLL}"',
        f"      tail -n 5 {GAST_PROTOKOLL} 2>/dev/null || true",
        *(["  " + melden] if melden else []),
        "      NETZ_RC=1",
        "    fi",
        f"    rm -f {q_ziel}   # Schlüssel nicht liegen lassen (nach Erfolg löscht sich das Skript selbst)",
        "  else",
        '    echo "WARNUNG: Kein Beitrittsskript für das Bony-Netz gefunden."',
        *([melden] if melden else []),
        "    NETZ_RC=1",
        "  fi",
        "fi",
    ]
    return "\n".join(zeilen) + "\n"


def nachtraeglich_verbinden(machine: VM, password: str | None = None) -> str:
    """Laufenden, fertig eingerichteten Agent-PC nachträglich verbinden – über den Gast-Agent, sonst SSH.

    Der Geräteschlüssel wird erst geholt, wenn klar ist, dass der Befehl in den Agent-PC kommt (sonst
    vm.NeedsPassword vorher, ohne einen Schlüssel zu verbrauchen). Gibt die Ausgabe zurück.
    """
    from bonys_agents import vm

    if not machine.is_running() or not machine.progress().ready or machine.config.first_boot_pending:
        raise RuntimeError(f"„{machine.name}“ muss laufen und fertig eingerichtet sein.")
    if not password and not machine.guest_agent_ready():
        raise vm.NeedsPassword("Der Gast-Agent antwortet nicht – für SSH wird das Passwort des Agent-PCs gebraucht.")
    beitritt = beitritt_vorbereiten(machine.name)
    skript = "set -uo pipefail\n" + gast_beitritt(aus_seed=False, skript=beitritt.skript) + 'exit "$NETZ_RC"\n'
    machine.config.netz_name = beitritt.netzname
    machine.save()   # schon vorher: Auch wenn es scheitert, zeigt die Liste den Zustand („nicht verbunden“)
    return machine.guest_run(skript, password=password, timeout=900, via_stdin=True)
