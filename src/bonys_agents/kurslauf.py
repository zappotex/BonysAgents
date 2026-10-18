# SPDX-License-Identifier: GPL-3.0-or-later
"""Kurspakete im Agent-PC: Startzustände je Lektion, Prüfaufgaben, Vertrauen (Signatur, Zustimmung zu Skripten).

**Startzustände** – Entscheidung (siehe ``docs/dev/plan-kurspakete.md``): Beim ersten Betreten einer Lektion läuft
ihr Startskript (falls vorhanden) im Agent-PC, danach entsteht ein **interner qcow2-Schnappschuss nur der
Festplatte** (``bonys-paket-<id>-<NN>``). Im laufenden Betrieb über den QEMU-Monitor
(``snapshot_blkdev_internal``, vorher ``sync`` im Gast), sonst mit ``qemu-img snapshot``. Ein Schnappschuss
kostet nur die Blöcke, die sich danach ändern, und hält auch fest, was der Teilnehmer vorher selbst eingerichtet hat
(z. B. die Anmeldung bei Hermes mit eigenem Konto) – das könnte ein Skript nie nachbauen. „Lektion zurücksetzen“:
Agent-PC herunterfahren, Schnappschuss zurückspielen, Schnappschüsse späterer Lektionen löschen, neu starten.

**Prüf- und Startskripte laufen ausschließlich im Agent-PC** – über den QEMU Guest Agent (kein SSH, kein Passwort,
kein Weg über diesen Rechner). Das Skript geht über die Standardeingabe an den Interpreter im Gast, mit
``timeout`` im Gast und als Benutzer des Agent-PCs (oder root, wenn das Paket es so will). Die Ausgabe wird
verworfen; das Ergebnis ist nur „geschafft / noch nicht“ plus der Hinweistext aus dem Paket.

**Vertrauen:** Mitgelieferte Kurspakete und solche mit gültiger Signatur (``pruefsummen.txt`` +
``pruefsummen.txt.minisig``, signiert mit dem Release-Schlüssel von Bony's Agents) gelten als „geprüft“. Bei allen
anderen fragt die Oberfläche vor dem ersten Start, ob die aufgelisteten Skripte im Agent-PC laufen dürfen – die
Zustimmung gilt für genau diese Skripte (Prüfsumme) und wird bei einer geänderten Fassung erneut eingeholt.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from bonys_agents import UPDATE_PUBLIC_KEY, host, kurspaket, qemu, signing, templates, vm
from bonys_agents.procutil import clean_env, no_window_flags

SNAP_PREFIX = "bonys-paket-"
DISK_DEVICE = "disk0"               # Name der Systemplatte in qemu.build_command
PRUEFSUMMEN = "pruefsummen.txt"
SIGNATUR = PRUEFSUMMEN + ".minisig"
INTERPRETER = {".sh": "/bin/bash", ".py": "/usr/bin/python3"}
ZEITLIMIT_RC = 124                  # Exit-Code von timeout(1)
_SNAP_RE = re.compile(r"^[A-Za-z0-9_.-]{1,120}$")


class NichtBereit(RuntimeError):
    """Der Agent-PC läuft nicht oder ist noch nicht fertig – die Meldung sagt, was zu tun ist."""


@dataclass
class Ergebnis:
    geschafft: bool
    text: str


# ---------------------------------------------------------------- Agent-PC: Zustand
def bereit(machine: vm.VM) -> bool:
    """Läuft und ist fertig eingerichtet (Desktop da)."""
    try:
        return machine.is_running() and machine.progress().ready and not machine.config.first_boot_pending
    except (OSError, ValueError):
        return False


def _qemu_img() -> Path:
    return qemu.find_binary("qemu-img", host.detect().os)


def _img(*args: str) -> str:
    proc = subprocess.run([str(_qemu_img()), *args], capture_output=True, text=True,
                          creationflags=no_window_flags(), env=clean_env())
    if proc.returncode != 0:
        raise RuntimeError(f"qemu-img {args[0]} fehlgeschlagen: {proc.stderr.strip()[-300:]}")
    return proc.stdout


# ---------------------------------------------------------------- Startzustände (Schnappschüsse)
def snapshot_name(paket: kurspaket.Kurspaket, lek: kurspaket.Lektion) -> str:
    return f"{SNAP_PREFIX}{paket.id}-{lek.ordner[:2]}"


def schnappschuesse(machine: vm.VM) -> set[str]:
    """Namen der internen Schnappschüsse der Systemplatte (geht auch, während der Agent-PC läuft)."""
    try:
        info = json.loads(_img("info", "-U", "--output=json", str(machine.disk)))
    except (RuntimeError, ValueError, OSError, qemu.QemuNotFound):
        return set()
    return {s.get("name", "") for s in info.get("snapshots") or [] if isinstance(s, dict)}


def startzustaende(machine: vm.VM, paket: kurspaket.Kurspaket) -> set[str]:
    """Lektionsordner, für die es einen Startzustand gibt."""
    vorhanden = schnappschuesse(machine)
    return {lek.ordner for lek in paket.lektionen if snapshot_name(paket, lek) in vorhanden}


def _hmp(machine: vm.VM, befehl: str) -> None:
    with qemu.QMP(machine.qmp_endpoint(), timeout=30) as q:
        out = q.hmp(befehl).strip()
    if out:
        raise RuntimeError(f"Schnappschuss nicht möglich: {out[-300:]}")


def startzustand_speichern(machine: vm.VM, name: str) -> None:
    """Schnappschuss der Festplatte unter ``name`` anlegen (ersetzt einen gleichnamigen)."""
    if not _SNAP_RE.match(name):
        raise ValueError("ungültiger Name für einen Schnappschuss")
    vorhanden = name in schnappschuesse(machine)
    if machine.is_running():
        try:   # Puffer im Gast auf die Platte schreiben – der Schnappschuss ist dann wie nach einem sauberen sync
            with qemu.GuestAgent(machine.qga_endpoint(), timeout=5) as ga:
                ga.run("sync", timeout=60)
        except (qemu.GuestAgentError, RuntimeError):
            pass
        if vorhanden:
            _hmp(machine, f"snapshot_delete_blkdev_internal {DISK_DEVICE} {name}")
        _hmp(machine, f"snapshot_blkdev_internal {DISK_DEVICE} {name}")
        return
    if vorhanden:
        _img("snapshot", "-d", name, str(machine.disk))
    _img("snapshot", "-c", name, str(machine.disk))


def startzustand_loeschen(machine: vm.VM, name: str) -> None:
    if name not in schnappschuesse(machine):
        return
    if machine.is_running():
        _hmp(machine, f"snapshot_delete_blkdev_internal {DISK_DEVICE} {name}")
    else:
        _img("snapshot", "-d", name, str(machine.disk))


def alle_loeschen(machine: vm.VM, paket: kurspaket.Kurspaket) -> int:
    """Alle Startzustände dieses Kurspakets entfernen (z. B. nach dem Abschluss). Gibt die Anzahl zurück."""
    n = 0
    for lek in paket.lektionen:
        name = snapshot_name(paket, lek)
        if name in schnappschuesse(machine):
            startzustand_loeschen(machine, name)
            n += 1
    return n


def lektion_vorbereiten(machine: vm.VM, paket: kurspaket.Kurspaket, index: int,
                        uebersprungen: bool = True) -> bool:
    """Startzustand für Lektion ``index`` herstellen, falls es ihn noch nicht gibt.

    Läuft das Startskript (bzw. bei ``uebersprungen`` auch die Startskripte übersprungener Lektionen davor, die noch
    keinen Startzustand haben) und legt dann den Schnappschuss an. Braucht der Weg ein Skript, muss der Agent-PC
    laufen (sonst NichtBereit). True, wenn ein neuer Startzustand entstanden ist.
    """
    lek = paket.lektionen[index]
    vorhanden = startzustaende(machine, paket)
    if lek.ordner in vorhanden:
        return False
    skripte = []
    if uebersprungen:
        for frueher in paket.lektionen[:index]:
            if frueher.ordner not in vorhanden and frueher.start:
                skripte.append(frueher)
    if lek.start:
        skripte.append(lek)
    if skripte and not bereit(machine):
        raise NichtBereit("Für den Startzustand dieser Lektion muss der Agent-PC laufen und fertig eingerichtet sein.")
    for s in skripte:
        rc = im_agent_pc_ausfuehren(machine, s.pfad / s.start.skript, s.start.als, s.start.zeitlimit)
        if rc != 0:
            raise RuntimeError(f"Das Startskript von Lektion „{s.titel}“ ist fehlgeschlagen"
                               + (" (Zeitlimit überschritten)." if rc == ZEITLIMIT_RC else f" (Code {rc})."))
    startzustand_speichern(machine, snapshot_name(paket, lek))
    return True


def lektion_zuruecksetzen(machine: vm.VM, paket: kurspaket.Kurspaket, index: int, starten: bool = True) -> None:
    """Agent-PC auf den Startzustand von Lektion ``index`` zurücksetzen.

    Fährt ihn herunter (nach 90 s hart), spielt den Schnappschuss zurück, löscht die Startzustände späterer
    Lektionen (die gehören zu einem Verlauf, den es jetzt nicht mehr gibt) und startet ihn wieder.
    """
    lek = paket.lektionen[index]
    name = snapshot_name(paket, lek)
    if name not in schnappschuesse(machine):
        raise NichtBereit(f"Für Lektion „{lek.titel}“ gibt es noch keinen Startzustand.")
    if machine.is_running():
        machine.stop()
        if machine.is_running():
            raise RuntimeError("Der Agent-PC ließ sich nicht herunterfahren.")
    _img("snapshot", "-a", name, str(machine.disk))
    for spaeter in paket.lektionen[index + 1:]:
        startzustand_loeschen(machine, snapshot_name(paket, spaeter))
    if starten:
        machine.start()


# ---------------------------------------------------------------- Skripte im Agent-PC
def befehl_im_gast(skript: Path, als: str, username: str, zeitlimit: int) -> tuple[str, list[str]]:
    """(Programm, Argumente) für guest-exec: ``timeout`` im Gast, saubere Umgebung, Interpreter liest stdin."""
    interpreter = INTERPRETER.get(skript.suffix.lower())
    if interpreter is None:
        raise ValueError(f"Unbekannte Skriptart: {skript.name}")
    if not vm.USERNAME_RE.match(username):
        raise ValueError("ungültiger Benutzername")
    home = "/root" if als == "root" else f"/home/{username}"
    user = "root" if als == "root" else username
    umgebung = ["/usr/bin/env", "-i", f"HOME={home}", f"USER={user}", f"LOGNAME={user}", "LANG=de_DE.UTF-8",
                f"PATH={home}/.local/bin:/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin:/sbin"]
    lesen = [interpreter, "-s"] if interpreter.endswith("bash") else [interpreter, "-"]
    wer = [] if als == "root" else ["/usr/sbin/runuser", "-u", username, "--"]
    args = ["-k", "3", str(int(zeitlimit)), *wer, *umgebung, *lesen]
    return "/usr/bin/timeout", args


def im_agent_pc_ausfuehren(machine: vm.VM, skript: Path, als: str, zeitlimit: int) -> int:
    """Skript aus einem Kurspaket im Agent-PC ausführen – nur über den Gast-Agent. Gibt den Exit-Code zurück,
    nie die Ausgabe. Ohne erreichbaren Gast-Agent: NichtBereit (es gibt bewusst keinen Weg über SSH)."""
    if not machine.is_running():
        raise NichtBereit("Der Agent-PC läuft nicht – bitte zuerst starten.")
    inhalt = skript.read_bytes()
    programm, args = befehl_im_gast(skript, als, machine.config.username, zeitlimit)
    try:
        with qemu.GuestAgent(machine.qga_endpoint(), timeout=5) as ga:
            rc, _out, _err = ga.exec(programm, args, stdin=inhalt, timeout=zeitlimit + 15)
    except qemu.GuestAgentError:
        raise NichtBereit("Der Agent-PC antwortet noch nicht – warte, bis der Desktop da ist, und versuche es dann "
                          "noch einmal.") from None
    return rc


def pruefen(machine: vm.VM | None, paket: kurspaket.Kurspaket, lek: kurspaket.Lektion) -> Ergebnis:
    """Prüfaufgabe der Lektion – Ergebnis nur „geschafft / noch nicht“ mit dem Hinweistext aus dem Paket."""
    p = lek.pruefung
    if p is None:
        raise ValueError("Diese Lektion hat keine Prüfaufgabe.")
    if p.typ == "vorlage-vorhanden":
        ok = bool(templates.list_templates())
    elif p.typ == "agent-pc-laeuft":
        ok = machine is not None and bereit(machine)
    else:
        if machine is None:
            raise NichtBereit("Für dieses Kurspaket ist noch kein Agent-PC eingerichtet.")
        if not bereit(machine):
            raise NichtBereit("Der Agent-PC muss laufen und fertig eingerichtet sein, damit geprüft werden kann.")
        rc = im_agent_pc_ausfuehren(machine, lek.pfad / p.skript, p.als, p.zeitlimit)
        if rc == ZEITLIMIT_RC:
            return Ergebnis(False, f"{p.noch_nicht} (Die Prüfung hat zu lange gedauert.)")
        ok = rc == 0
    return Ergebnis(ok, p.geschafft if ok else p.noch_nicht)


# ---------------------------------------------------------------- Vertrauen
def pruefsummen_text(ordner: Path) -> str:
    """Inhalt für ``pruefsummen.txt`` (Format wie ``sha256sum``) über alle Dateien des Pakets."""
    zeilen = []
    for p, rel in kurspaket._dateien(ordner):
        if rel.as_posix() in (PRUEFSUMMEN, SIGNATUR) or p.is_symlink():
            continue
        zeilen.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {rel.as_posix()}")
    return "\n".join(zeilen) + "\n"


def signatur_pruefen(paket: kurspaket.Kurspaket, public_key: str = UPDATE_PUBLIC_KEY) -> bool:
    """True, wenn ``pruefsummen.txt`` gültig signiert ist UND genau zu den Dateien des Pakets passt."""
    datei, sig = paket.pfad / PRUEFSUMMEN, paket.pfad / SIGNATUR
    if not datei.is_file() or not sig.is_file():
        return False
    try:
        daten = datei.read_bytes()
        signing.verify(daten, sig.read_text("utf-8"), public_key)
    except (OSError, UnicodeDecodeError, signing.SignatureError):
        return False
    return daten.decode("utf-8", errors="replace") == pruefsummen_text(paket.pfad)


def geprueft(paket: kurspaket.Kurspaket) -> bool:
    """Mitgeliefert oder gültig signiert – dann fragt die Oberfläche nicht nach den Skripten."""
    return paket.mitgeliefert or signatur_pruefen(paket)


def skripte_kennung(paket: kurspaket.Kurspaket) -> str:
    """Prüfsumme über alle Skripte (Pfad und Inhalt) – die Zustimmung gilt genau für diese Fassung."""
    h = hashlib.sha256()
    for lek in paket.lektionen:
        rel = [lek.start.skript] if lek.start else []
        if lek.pruefung and lek.pruefung.typ == kurspaket.SKRIPT:
            rel.append(lek.pruefung.skript)
        for r in rel:
            h.update(f"{lek.ordner}/{r}".encode() + b"\0" + (lek.pfad / r).read_bytes() + b"\0")
    return h.hexdigest()


def zustimmung_noetig(paket: kurspaket.Kurspaket) -> bool:
    if not paket.skripte() or geprueft(paket):
        return False
    return kurspaket.Fortschritt.laden(paket.id).skripte_erlaubt != skripte_kennung(paket)


def zustimmen(paket: kurspaket.Kurspaket) -> None:
    f = kurspaket.Fortschritt.laden(paket.id)
    f.skripte_erlaubt = skripte_kennung(paket)
    f.speichern()
