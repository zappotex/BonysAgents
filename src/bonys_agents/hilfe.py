# SPDX-License-Identifier: GPL-3.0-or-later
"""Hilfe-Funktion über das Bony-Netz (Aufgabe 06): Der Kursleiter sieht – und bedient – den Agent-PC eines Teilnehmers.

Immer nur nach ausdrücklicher Zustimmung des Teilnehmers, jedes Mal neu, zeitlich begrenzt und jederzeit beendbar.
Hier steht alles ohne Qt (beide Editionen); die Fenster sind ``gui/hilfe_ui.py`` (Teilnehmer) und
``trainer/gui/hilfe_fenster.py`` (Kursleiter), die Nachrichten laufen über den Kursraum (``resources/kursraum``).

Ablauf:

1. Kursleiter „Helfen“ → Datennachricht ``hilfe-anfrage`` nur an diesen Teilnehmer (LiveKit
   ``destinationIdentities`` = instanz_id). „Hilfe anfordern“ beim Teilnehmer schickt nur ``hilfe-bitte`` (Symbol
   beim Kursleiter).
2. Beim Teilnehmer: „Nur ansehen“, „Ansehen und bedienen“ oder „Ablehnen“ – ohne Antwort nach 60 s „Ablehnen“.
3. Zustimmung: ``starten`` startet im Agent-PC (Gast-Agent, wie ``netz.nachtraeglich_verbinden``) **x11vnc** als
   eigene systemd-Einheit – nur auf der Adresse im Bony-Netz (``tailscale ip -4``, kein IPv6), Einmal-Passwort
   (Datei, die x11vnc nach dem Lesen löscht), eine Verbindung (``-once``), Ende nach 2 min ohne Verbindung
   (``-timeout``) und spätestens nach 30 min (``RuntimeMaxSec``), bei „Nur ansehen“ ``-viewonly``. Nennt die Anfrage
   die Adresse des Kursleiter-Rechners (``von``), nimmt x11vnc nur von dort Verbindungen an (``-allow``) – auch
   nicht von den eigenen Agent-PCs des Kursleiters. Ein **Totmannschalter** (Einheit ``bonys-hilfe-wache``) stoppt
   x11vnc, sobald sich die App des Teilnehmers länger als ``HERZSCHLAG_SEKUNDEN`` nicht meldet (Absturz, Netz weg) –
   die App „klopft“ bei jeder Statusprüfung (``status_skript``).
4. ``hilfe-zusage`` (Adresse, Port, Passwort, Modus) bzw. ``hilfe-absage`` geht nur an den Kursleiter.
5. ``beenden`` stoppt x11vnc sofort – Knopf „Beenden“, Kurs pausiert/beendet, Kursraum verlassen.

Dass der Kursleiter die Adresse nur erreicht, solange der Kurs läuft, nur den gewählten Agent-PC und dort nur den
Port der Hilfe, regelt die Zentrale. Anfragen nimmt die App nur von der Identität an, die die Zentrale als Kursleiter
nennt (``kursraum.Karte.leiter``). Zusätzlich verbindet sich die App des Kursleiters nur mit der Adresse, die die
Zentrale für diesen Teilnehmer nennt (``zusage_pruefen``).
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import secrets
import shlex
import shutil
import string
import subprocess
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bony_netz import Konto

from bonys_agents import kurse, netz
from bonys_agents.apps import APT_WAIT

if TYPE_CHECKING:
    from bonys_agents.vm import VM

# Datennachrichten im Kursraum (Thema = Art, Inhalt JSON)
ANFRAGE, ZUSAGE, ABSAGE, BITTE, ENDE = "hilfe-anfrage", "hilfe-zusage", "hilfe-absage", "hilfe-bitte", "hilfe-ende"
ANSEHEN, BEDIENEN = "ansehen", "bedienen"
MODUS_TEXT = {ANSEHEN: "Nur ansehen", BEDIENEN: "Ansehen und bedienen"}

ANTWORT_SEKUNDEN = 60          # so lange wartet die Rückfrage beim Teilnehmer, dann gilt „Ablehnen“
WARTEN_SEKUNDEN = 120          # x11vnc endet, wenn so lange keine Verbindung kommt
HOECHSTENS_MINUTEN = 30        # und spätestens nach dieser Zeit
PORT = 5959                    # im Agent-PC, nur auf der Adresse im Bony-Netz
EINHEIT = "bonys-hilfe"        # systemd-Einheit im Agent-PC
WACHE = "bonys-hilfe-wache"    # Totmannschalter: stoppt EINHEIT, wenn die App sich nicht mehr meldet
HERZSCHLAG_SEKUNDEN = 30       # so lange darf das letzte Klopfen der App (status_skript) her sein
WACHE_TAKT = 5                 # so oft schaut der Totmannschalter nach
ORDNER = "/run/bonys-hilfe"    # Passwortdatei (tmpfs, 0700) – x11vnc löscht sie nach dem Lesen
PASSWORT_LAENGE = 8            # VNC-Passwörter haben höchstens 8 Zeichen
_ZEICHEN = string.ascii_letters + string.digits
NETZ = ipaddress.ip_network("100.64.0.0/10")   # Adressen im Bony-Netz (Tailscale/Headscale)

# Exit-Codes des Startskripts
RC_KEIN_NETZ, RC_INSTALLATION, RC_START = 3, 4, 5

KEIN_AGENT_PC = ("Der Agent-PC, mit dem du an diesem Kurs teilnimmst, ist nicht auf diesem Rechner. Hilfe geht nur "
                 "für einen Agent-PC, der hier läuft.")
LAEUFT_NICHT = "„{name}“ muss laufen und fertig eingerichtet sein – starte ihn und bitte dann erneut um Hilfe."
KEIN_GAST_AGENT = ("Der Gast-Agent in „{name}“ antwortet nicht. Ohne ihn kann die App die Bildschirmfreigabe nicht "
                   "starten – warte einen Moment, bis der Agent-PC ganz hochgefahren ist.")
FEHLER_TEXT = {
    RC_KEIN_NETZ: "„{name}“ ist nicht mit dem Bony-Netz verbunden (keine Adresse von Tailscale).",
    RC_INSTALLATION: "x11vnc ließ sich in „{name}“ nicht installieren (Internet im Agent-PC?).",
    RC_START: "Die Bildschirmfreigabe ist in „{name}“ nicht gestartet.",
}


class HilfeFehler(Exception):
    """Für den Nutzer geschrieben – kann direkt angezeigt werden."""


@dataclass(frozen=True)
class Freigabe:
    """Was der Kursleiter zum Verbinden braucht (``hilfe-zusage``). Das Passwort gilt nur für diese Sitzung."""

    ip: str
    port: int
    modus: str
    passwort: str = field(repr=False)

    def nachricht(self, anfrage_id: str, pc: str) -> dict:
        return {"id": anfrage_id, "ip": self.ip, "port": self.port, "modus": self.modus,
                "passwort": self.passwort, "pc": pc}


def passwort() -> str:
    return "".join(secrets.choice(_ZEICHEN) for _ in range(PASSWORT_LAENGE))


# ---------------------------------------------------------------- Skripte im Agent-PC (als root)
def wache_skript(ordner: str = ORDNER) -> str:
    """Bash für den Totmannschalter: läuft neben x11vnc und stoppt es, wenn ``<ordner>/lebt`` zu alt ist."""
    lebt = shlex.quote(f"{ordner}/lebt")
    return (f"while systemctl is-active --quiet {EINHEIT}.service; do "
            f"a=$(( $(date +%s) - $(stat -c %Y {lebt} 2>/dev/null || echo 0) )); "
            f"if [ \"$a\" -gt {HERZSCHLAG_SEKUNDEN} ]; then systemctl stop {EINHEIT}.service; rm -rf "
            f"{shlex.quote(ordner)}; break; fi; sleep {WACHE_TAKT}; done")


def start_skript(modus: str, passwort: str, port: int = PORT, ordner: str = ORDNER, von: str = "") -> str:
    """Bash: x11vnc (bei Bedarf aus den Debian-Paketen installieren) nur auf der Adresse im Bony-Netz starten.

    Kommt über die Standardeingabe in den Agent-PC (``guest_run(via_stdin=True)``) – das Passwort steht so auf keiner
    Kommandozeile, auch nicht im Agent-PC: ``printf`` ist in bash eingebaut, x11vnc liest es aus einer Datei, die es
    danach löscht (``rm:``). Letzte Zeile der Ausgabe: ``BONYS_HILFE <Adresse>``. ``ordner`` nur für Tests.
    """
    if modus not in MODUS_TEXT:
        raise ValueError(f"Unbekannter Modus: {modus}")
    if not re.fullmatch(r"[A-Za-z0-9]{1,8}", passwort):
        raise ValueError("Das Passwort darf nur 1 bis 8 Buchstaben und Ziffern haben.")
    if von and not im_netz(von):
        raise ValueError("Die Adresse des Kursleiter-Rechners liegt nicht im Bony-Netz.")
    q_ordner = shlex.quote(ordner)
    datei = f"{ordner}/passwort"
    # Kein „-auth guess“: Das ruft Hilfsprogramme auf und verträgt sich nicht mit -nocmds (x11vnc bricht dann ab).
    # Den Zugangsschlüssel nennt der X-Server selbst in seinem Aufruf (lightdm: /var/run/lightdm/root/:0).
    argumente = [
        "/usr/bin/x11vnc", "-display", ":0", "-auth", "$AUTH",
        "-listen", "$IP", "-noipv6", "-rfbport", str(int(port)),
        "-once", "-timeout", str(WARTEN_SEKUNDEN), "-passwdfile", f"rm:{datei}",
        "-nevershared", "-nosel", "-noremote", "-nocmds", "-norc", "-nolookup",
        *(["-viewonly"] if modus == ANSEHEN else []),
        *(["-allow", von] if von else []),
    ]
    aufruf = " ".join(f'"{a}"' if a in ("$IP", "$AUTH") else shlex.quote(a) for a in argumente)
    return "\n".join([
        "set -u",
        "# Bony's Agents: Hilfe-Funktion – Bildschirmfreigabe für den Kursleiter (nur im Bony-Netz)",
        APT_WAIT,
        'IP="$(tailscale ip -4 2>/dev/null | head -n1)"',
        f'case "$IP" in 100.*) ;; *) echo "Keine Adresse im Bony-Netz."; exit {RC_KEIN_NETZ} ;; esac',
        "if ! command -v x11vnc >/dev/null 2>&1; then",
        '  echo "Installiere x11vnc aus den Debian-Paketen …"',
        "  bonys_apt_wait",
        "  export DEBIAN_FRONTEND=noninteractive",
        "  apt-get install -y --no-install-recommends x11vnc >/dev/null 2>&1 || "
        "{ apt-get update >/dev/null 2>&1 && apt-get install -y --no-install-recommends x11vnc >/dev/null 2>&1; } "
        f"|| {{ echo 'x11vnc ließ sich nicht installieren.'; exit {RC_INSTALLATION}; }}",
        "fi",
        "AUTH=\"$(ps -eo args= | awk '$1 ~ /(^|\\/)X(org)?$/ && $2 == \":0\" "
        "{ for (i = 3; i < NF; i++) if ($i == \"-auth\") { print $(i + 1); exit } }')\"",
        'if [ -z "$AUTH" ] || [ ! -f "$AUTH" ]; then',
        "  AUTH=''",
        "  for f in /var/run/lightdm/root/:0 /run/lightdm/root/:0 /home/*/.Xauthority /run/user/*/gdm/Xauthority; do",
        '    if [ -f "$f" ]; then AUTH="$f"; break; fi',
        "  done",
        "fi",
        f'[ -n "$AUTH" ] || {{ echo "Kein Zugang zum Bildschirm :0 gefunden (Xauthority)."; exit {RC_START}; }}',
        f"systemctl stop {WACHE}.service {EINHEIT}.service >/dev/null 2>&1 || true",
        f"systemctl reset-failed {WACHE}.service {EINHEIT}.service >/dev/null 2>&1 || true",
        f"rm -rf {q_ordner}",
        f"(umask 077; mkdir -p {q_ordner}; printf '%s\\n' {shlex.quote(passwort)} > {shlex.quote(datei)}; "
        f"touch {shlex.quote(ordner + '/lebt')})",
        f"systemd-run --quiet --unit={EINHEIT} --collect --property=RuntimeMaxSec={HOECHSTENS_MINUTEN * 60} "
        f"--property=KillMode=control-group {aufruf} || {{ rm -rf {q_ordner}; exit {RC_START}; }}",
        f"systemd-run --quiet --unit={WACHE} --collect --property=RuntimeMaxSec={HOECHSTENS_MINUTEN * 60 + 60} "
        f"/bin/bash -c {shlex.quote(wache_skript(ordner))} "
        f"|| {{ systemctl stop {EINHEIT}.service >/dev/null 2>&1; rm -rf {q_ordner}; exit {RC_START}; }}",
        "for i in $(seq 1 40); do",
        f'  if ss -Htln "sport = :{int(port)}" 2>/dev/null | grep -qF "$IP:{int(port)}"; then',
        '    echo "BONYS_HILFE $IP"; exit 0',
        "  fi",
        f"  systemctl is-active --quiet {EINHEIT}.service || break",
        "  sleep 0.25",
        "done",
        f"journalctl -u {EINHEIT}.service -n 8 --no-pager -o cat 2>/dev/null | tail -n 8",
        f"systemctl stop {WACHE}.service {EINHEIT}.service >/dev/null 2>&1 || true",
        f"rm -rf {q_ordner}",
        f"exit {RC_START}",
    ]) + "\n"


def stop_skript() -> str:
    """Bash: x11vnc sofort beenden (auch wenn es schon weg ist)."""
    return (f"systemctl stop {WACHE}.service {EINHEIT}.service >/dev/null 2>&1 || true\n"
            f"systemctl reset-failed {WACHE}.service {EINHEIT}.service >/dev/null 2>&1 || true\n"
            f"rm -rf {ORDNER}\n")


def status_skript() -> str:
    """Läuft x11vnc noch? Zugleich das Klopfen für den Totmannschalter (nur solange die App fragt, läuft die Hilfe)."""
    return (f"[ -d {ORDNER} ] && touch {ORDNER}/lebt\n"
            f"systemctl is-active --quiet {EINHEIT}.service && echo aktiv || echo aus\n")


# ---------------------------------------------------------------- Teilnehmer: Agent-PC des Kurses
def agent_pc(kurs_id: str) -> VM:
    """Der Agent-PC auf diesem Rechner, mit dem diese Instanz am Kurs teilnimmt (Zentrale fragen: blockiert)."""
    from bonys_agents import vm

    kurs = next((k for k in kurse.teilnahmen() if k.kurs_id == kurs_id), None)
    if kurs is None or not kurs.mein_geraet_id:
        raise HilfeFehler("Du nimmst an diesem Kurs nicht (mehr) teil.")
    netzname = next((name for name, g in netz.geraete().items() if str(g.get("geraet_id")) == kurs.mein_geraet_id),
                    "")
    if netzname:
        for m in vm.list_vms():
            if getattr(m.config, "netz_name", "") == netzname:
                return m
    raise HilfeFehler(KEIN_AGENT_PC)


def kurs_laeuft(kurs_id: str) -> bool:
    """Läuft der Kurs noch? (Teilnehmer, blockiert) – sonst endet eine Hilfe sofort."""
    return any(k.kurs_id == kurs_id and k.laeuft for k in kurse.teilnahmen())


def _bereit(machine: VM) -> None:
    if not machine.is_running() or not machine.progress().ready or machine.config.first_boot_pending:
        raise HilfeFehler(LAEUFT_NICHT.format(name=machine.name))


def starten(machine: VM, modus: str, port: int = PORT, von: str = "") -> Freigabe:
    """x11vnc im Agent-PC starten. Nur über den Gast-Agent – eine Passwort-Rückfrage für SSH gibt es hier nicht.

    ``von``: Adresse des Kursleiter-Rechners im Bony-Netz – dann nimmt x11vnc nur von dort Verbindungen an.
    """
    from bonys_agents import vm

    _bereit(machine)
    pw = passwort()
    try:
        ausgabe = machine.guest_run(start_skript(modus, pw, port, von=von if im_netz(von) else ""), timeout=600,
                                    via_stdin=True)
    except vm.NeedsPassword:
        raise HilfeFehler(KEIN_GAST_AGENT.format(name=machine.name)) from None
    except RuntimeError as e:
        m = re.search(r"\(Code (\d+)\)", str(e))
        rc = int(m.group(1)) if m else 0
        text = FEHLER_TEXT.get(rc, FEHLER_TEXT[RC_START]).format(name=machine.name)
        grund = _grund(str(e)) if rc == RC_START else ""
        raise HilfeFehler(text + (f"\n\nMeldung aus dem Agent-PC: {grund}" if grund else "")) from None
    m = re.search(r"^BONYS_HILFE (\S+)\s*$", ausgabe, re.M)
    if not m or not im_netz(m.group(1)):
        beenden(machine)
        raise HilfeFehler(FEHLER_TEXT[RC_START].format(name=machine.name))
    return Freigabe(m.group(1), port, modus, pw)


def _grund(fehler: str) -> str:
    """Letzte aussagekräftige Zeile aus der Ausgabe des Startskripts (Journal von x11vnc) – nur druckbare Zeichen,
    ohne Zeitstempel. Das Passwort steht nie darin (es liegt nur in der Datei)."""
    teile = fehler.split("):", 1)
    zeilen = [z.strip() for z in (teile[1] if len(teile) == 2 else "").splitlines() if z.strip()]
    zeilen = [re.sub(r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2} ", "", z) for z in zeilen
              if not z.startswith(("bonys-hilfe", "Started ", "passing arg"))]
    text = zeilen[-1] if zeilen else ""
    return "".join(c for c in text if c.isprintable())[:200]


def beenden(machine: VM) -> None:
    """x11vnc sofort stoppen – auch wenn der Agent-PC inzwischen aus ist (dann läuft ohnehin nichts mehr)."""
    from bonys_agents import vm

    if not machine.is_running():
        return
    try:
        machine.guest_run(stop_skript(), timeout=30)
    except (vm.NeedsPassword, RuntimeError):
        pass


def aktiv(machine: VM) -> bool | None:
    """Läuft x11vnc noch? None, wenn der Gast-Agent gerade nicht antwortet."""
    from bonys_agents import vm

    if not machine.is_running():
        return False
    try:
        return machine.guest_run(status_skript(), timeout=15).strip().endswith("aktiv")
    except (vm.NeedsPassword, RuntimeError):
        return None


# ---------------------------------------------------------------- Kursleiter: Zusage prüfen
def im_netz(ip: str) -> bool:
    try:
        adresse = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return adresse.version == 4 and adresse in NETZ


def zusage_pruefen(daten: dict, erwartete_ip: str = "") -> Freigabe:
    """``hilfe-zusage`` des Teilnehmers prüfen. ``erwartete_ip``: Adresse des Agent-PCs laut Zentrale.

    Die App verbindet sich nur mit einer Adresse im Bony-Netz – und, wenn die Zentrale sie nennt, nur mit genau
    der des gewählten Agent-PCs (eine gefälschte Zusage kann den Kursleiter also nicht anderswohin schicken).
    """
    if not isinstance(daten, dict):
        raise HilfeFehler("Die Zusage ist unvollständig.")
    ip, port, modus, pw = daten.get("ip"), daten.get("port"), daten.get("modus"), daten.get("passwort")
    if not isinstance(ip, str) or not im_netz(ip):
        raise HilfeFehler("Die Zusage nennt keine Adresse im Bony-Netz.")
    if erwartete_ip and ip != erwartete_ip:
        raise HilfeFehler("Die Adresse in der Zusage gehört nicht zum Agent-PC des Teilnehmers.")
    if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
        raise HilfeFehler("Die Zusage nennt keinen gültigen Port.")
    if modus not in MODUS_TEXT:
        raise HilfeFehler("Die Zusage nennt keinen gültigen Modus.")
    if not isinstance(pw, str) or not re.fullmatch(r"[A-Za-z0-9]{1,8}", pw):
        raise HilfeFehler("Die Zusage enthält kein gültiges Passwort.")
    return Freigabe(ip, port, modus, pw)


def teilnehmer_ip(kurs_id: str, instanz_id: str) -> str:
    """Adresse des Agent-PCs eines Teilnehmers laut Zentrale (Kursleiter, blockiert). "" wenn unbekannt.

    Wirft HilfeFehler, wenn der Kurs nicht läuft – dann gibt es auch keinen Netzzugang.
    """
    kurs = kurse.geleiteter_kurs(kurs_id)
    if kurs is None or not kurs.laeuft:
        raise HilfeFehler("Der Kurs läuft nicht – Hilfe geht nur, solange er läuft.")
    t = next((x for x in kurs.teilnehmer if x.instanz_id == instanz_id), None)
    if t is None:
        raise HilfeFehler("Der Teilnehmer ist nicht (mehr) in diesem Kurs.")
    return t.geraet_ip


# ---------------------------------------------------------------- Kursleiter: dieser Rechner im Bony-Netz?
TAILSCALE_PFADE = {
    "win32": [r"C:\Program Files\Tailscale\tailscale.exe"],
    "darwin": ["/Applications/Tailscale.app/Contents/MacOS/Tailscale", "/usr/local/bin/tailscale",
               "/opt/homebrew/bin/tailscale"],
}


@dataclass
class Rechner:
    """Zustand dieses Rechners im Bony-Netz (für den VNC-Betrachter des Kursleiters)."""

    verbunden: bool
    text: str
    installiert: bool = True


_SELBST_FRAGEN = object()


def eigene_ip(status=_SELBST_FRAGEN) -> str:
    """Adresse dieses Rechners im Bony-Netz (IPv4 aus ``tailscale status``) – "" wenn unbekannt. Blockiert."""
    st = tailscale_status() if status is _SELBST_FRAGEN else status
    selbst = st.get("Self") if isinstance(st, dict) and isinstance(st.get("Self"), dict) else {}
    ips = selbst.get("TailscaleIPs") or (st.get("TailscaleIPs") if isinstance(st, dict) else None) or []
    return next((str(i) for i in ips if isinstance(i, str) and im_netz(i)), "")


def _tailscale() -> str | None:
    exe = shutil.which("tailscale")
    if exe:
        return exe
    return next((p for p in TAILSCALE_PFADE.get(sys.platform, []) if os.path.isfile(p)), None)


def tailscale_status(run=subprocess.run) -> dict | None:
    """``tailscale status --json`` (ohne root) – None, wenn Tailscale fehlt oder der Dienst nicht antwortet."""
    exe = _tailscale()
    if not exe:
        return None
    try:
        proc = run([exe, "status", "--json"], capture_output=True, text=True, timeout=10, stdin=subprocess.DEVNULL)
        daten = json.loads(proc.stdout or "")
    except (OSError, subprocess.SubprocessError, ValueError):
        return {}
    return daten if isinstance(daten, dict) else {}


_FRAGEN = object()


def rechner_im_netz(status=_FRAGEN, geraete: list[dict] | None = None) -> Rechner:
    """Ist dieser Rechner mit dem Netz der eigenen Instanz verbunden (wie „Diesen Rechner verbinden“ in Bony's VPN)?

    Sicher erkennbar an der eigenen Adresse in der Geräteliste der Instanz. ``status``: Antwort von
    ``tailscale_status`` (None = nicht installiert) – ohne Angabe werden Tailscale und die Zentrale gefragt (blockiert).
    """
    st = tailscale_status() if status is _FRAGEN else status
    if st is None:
        return Rechner(False, "Tailscale ist auf diesem Rechner nicht installiert.", installiert=False)
    if not st:
        return Rechner(False, "Der Tailscale-Dienst läuft auf diesem Rechner nicht.")
    if st.get("BackendState") != "Running":
        return Rechner(False, "Dieser Rechner ist nicht mit dem Bony-Netz verbunden (Tailscale ist aus).")
    selbst = st.get("Self") if isinstance(st.get("Self"), dict) else {}
    ips = {str(i) for i in (selbst.get("TailscaleIPs") or st.get("TailscaleIPs") or []) if isinstance(i, str)}
    liste = list(netz.geraete().values()) if geraete is None else geraete
    if ips & {str(g.get("ip")) for g in liste if isinstance(g, dict)}:
        return Rechner(True, "Dieser Rechner ist im Bony-Netz.")
    return Rechner(False, "Dieser Rechner ist mit einem anderen Tailscale-Netz verbunden, nicht mit dem Bony-Netz "
                          "deiner Instanz.")


VERBINDEN_HINWEIS = {
    "linux": ("Damit du die Agent-PCs der Teilnehmer sehen kannst, muss dieser Rechner im Bony-Netz sein: In Bony's "
              "VPN unter „Bony-Netz“ „Diesen Rechner verbinden“ einschalten."),
    "win32": ("Damit du die Agent-PCs der Teilnehmer sehen kannst, muss dieser Rechner im Bony-Netz sein. Unter "
              "Windows geht das mit der offiziellen Tailscale-App: Anmeldeserver „{login}“. Schalte dort in den "
              "Einstellungen „Allow incoming connections“ aus – dann erreicht kein Gerät aus dem Netz diesen Rechner."),
    "darwin": ("Damit du die Agent-PCs der Teilnehmer sehen kannst, muss dieser Rechner im Bony-Netz sein. Unter "
               "macOS geht das mit der offiziellen Tailscale-App: Anmeldeserver „{login}“. Schalte dort in den "
               "Einstellungen „Allow incoming connections“ aus – dann erreicht kein Gerät aus dem Netz diesen "
               "Rechner."),
}


def verbinden_hinweis(plattform: str | None = None) -> str:
    plattform = plattform or sys.platform
    schluessel = "linux" if plattform.startswith("linux") else plattform
    text = VERBINDEN_HINWEIS.get(schluessel, VERBINDEN_HINWEIS["linux"])
    return text.format(login=Konto.laden().login_server or Konto.laden().server)
