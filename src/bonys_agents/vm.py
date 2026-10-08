# SPDX-License-Identifier: GPL-3.0-or-later
"""Agent-PCs anlegen, starten, stoppen, löschen – der eigentliche Programmkern.

CLI und Desktop-App nutzen beide ausschließlich diese Schnittstelle.
"""

from __future__ import annotations

import base64
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path

import psutil

from bonys_agents import apps, cloudinit, desktops, diagnose, host, images, qemu, remote, screen, storage
from bonys_agents import progress as pct
from bonys_agents.procutil import clean_env, spawn_detached, terminal_command

ProgressFn = Callable[[str, float, str], None]  # (Phase, 0..1, Nachricht)

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")
# Festplatte: Stufen für den Schieberegler; die Kommandozeile erlaubt jeden Wert dazwischen.
DISK_STEPS_GB = [32, 48, 64, 96, 128, 192, 256, 384, 512, 768, 1024]
MIN_DISK_GB, MAX_DISK_GB = DISK_STEPS_GB[0], DISK_STEPS_GB[-1]
DEFAULT_DISK_GB = 64


def format_gb(gb: int) -> str:
    return f"{gb // 1024} TB" if gb >= 1024 and gb % 1024 == 0 else f"{gb} GB"


def check_disk_gb(gb: int) -> None:
    if not MIN_DISK_GB <= gb <= MAX_DISK_GB:
        raise ValueError(f"Festplatte: {MIN_DISK_GB} bis {MAX_DISK_GB} GB erlaubt (angegeben: {gb} GB)")


IMAGES_DIRNAME = "_images"  # Bild-Cache je Speicherort (kann nie ein VM-Name sein)

STATUS_ABORTED = "Einrichtung abgebrochen"
STATUS_READY_FOR_DESKTOP = "startet mit Desktop"
STATUS_STOPPING = "wird heruntergefahren"
STATUS_TEMPLATE_MISSING = "nicht verfügbar – Vorlage fehlt"
# Liegt im Ordner eines Agent-PCs, solange daraus eine Vorlage entsteht (Inhalt: PID des Prozesses)
TEMPLATE_LOCK = "vorlage-wird-erstellt.lock"

# Herunterfahren: ab wann „Sofort ausschalten“ angeboten wird, wann hart ausgeschaltet wird.
STOP_OFFER_KILL_AFTER = 15
STOP_TIMEOUT = 90

# Alte Konsolenprotokolle (console-<Datum>.log), die beim Start aufbewahrt werden
KEEP_CONSOLE_LOGS = 5
# Protokolle der Einrichtung im Gast → Dateien im VM-Ordner („Einrichtungsprotokoll holen“)
GUEST_SETUP_LOGS = {
    "/var/log/bonys-agents.log": "einrichtung-bonys-agents.log",
    "/var/log/cloud-init-output.log": "einrichtung-cloud-init-output.log",
}

# Von diesem Prozess gestartete QEMU-Instanzen. Die Popen-Objekte werden aufbewahrt und
# regelmäßig abgefragt – sonst bleibt ein beendetes QEMU als Zombie stehen, den psutil
# weiter für „läuft“ hält (z. B. nach dem Herunterfahren aus der Desktop-App heraus).
_children: dict[int, subprocess.Popen] = {}


def reap_children() -> None:
    """Beendete, selbst gestartete QEMU-Prozesse einsammeln."""
    for pid, proc in list(_children.items()):
        if proc.poll() is not None:
            _children.pop(pid, None)


def _reap(pid: int) -> None:
    """Einen Zombie einsammeln – über sein Popen-Objekt oder direkt per waitpid (nur POSIX)."""
    proc = _children.pop(pid, None)
    if proc is not None:
        proc.poll()
    elif os.name == "posix":
        try:
            os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            pass  # nicht unser Kind – den sammelt sein eigener Elternprozess ein


def data_dir() -> Path:
    return storage.data_dir()


def vms_dir() -> Path:
    """Standard-Speicherort im Hauptsystem."""
    return storage.default_library()


@dataclass
class VMConfig:
    name: str
    arch: str
    cpus: int
    ram_mb: int
    disk_gb: int = DEFAULT_DISK_GB
    username: str = "agent"
    apps: list[str] = field(default_factory=apps.default_app_ids)
    keyboard: str = "de"
    timezone: str = "Europe/Berlin"
    # Desktop für die automatische Anmeldung; ältere Agent-PCs haben Cinnamon
    desktop: str = desktops.DEFAULT
    # zusätzlich installierte Desktops („Desktop hinzufügen …“)
    extra_desktops: list[str] = field(default_factory=list)
    provisioned: bool = False
    # Ersteinrichtung läuft ohne Fenster; danach schaltet sich der Gast aus und wird mit Fenster neu gestartet.
    first_boot_pending: bool = False
    # Fernzugriff: feste, eindeutige Host-Ports (0 = noch nicht vergeben, z. B. bei älteren Agent-PCs)
    rdp_port: int = 0
    spice_port: int = 0
    # Fernzugriff „dauerhaft“: bei jedem Start an. „Nur bis zum Herunterfahren“ steht nur in runtime.json.
    remote_permanent: bool = False
    spice_password: str = ""      # für SPICE aus dem Heimnetz
    display: str = "qemu"         # „qemu“ = QEMU-Fenster, „spice“ = SPICE-Fenster (remote-viewer/Remmina)
    # Bildschirm: „auto“ = Auflösung folgt dem Fenster, „scale“ = Bild skalieren, „fixed“ = feste Auflösung
    screen_mode: str = screen.AUTO
    screen_size: str = screen.DEFAULT_SIZE   # für „scale“ und „fixed“
    # Zuletzt gesehener Einrichtungsschritt – nach einem Abbruch geht der Fortschritt dort weiter
    setup_step: int = 0
    setup_total: int = 0
    setup_title: str = ""
    # Aus dieser Vorlage entstanden (nur zur Anzeige – verknüpft ist, wer ein Backing-File hat)
    template: str = ""
    created: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))


@dataclass
class Progress:
    step: int
    total: int
    title: str
    ready: bool
    percent: float = 0.0
    resumed: bool = False   # Schritt stammt vom Lauf vor einem Abbruch (Gast startet gerade neu)
    resume_step: int = 0    # „BONYS-RESUME Schritt N“: Einrichtung wird bei Schritt N fortgesetzt


class VM:
    # Netz abschotten (nur für die Arbeitskopie beim Erstellen einer Vorlage)
    restrict_net = False

    def __init__(self, path: Path):
        self.path = path
        data = json.loads((path / "vm.json").read_text("utf-8"))
        if data.pop("remote_lan", False):  # bis 0.6: „Fernzugriff aus dem Heimnetz“ = jetzt „dauerhaft“
            data["remote_permanent"] = True
        known = {f.name for f in fields(VMConfig)}
        self.config = VMConfig(**{k: v for k, v in data.items() if k in known})

    # ---------- Pfade ----------
    @property
    def name(self) -> str:
        return self.config.name

    @property
    def location(self) -> Path:
        """Speicherort (Ordner, in dem der VM-Ordner liegt)."""
        return self.path.parent

    def size_on_disk(self) -> int:
        return sum(f.stat().st_size for f in self.path.rglob("*") if f.is_file())

    @property
    def disk(self) -> Path:
        return self.path / "disk.qcow2"

    @property
    def seed_iso(self) -> Path:
        return self.path / "seed.iso"

    @property
    def console_log(self) -> Path:
        return self.path / "console.log"

    @property
    def qemu_log(self) -> Path:
        return self.path / "qemu.log"

    @property
    def pidfile(self) -> Path:
        return self.path / "qemu.pid"

    @property
    def runtime_file(self) -> Path:
        return self.path / "runtime.json"

    def save(self) -> None:
        (self.path / "vm.json").write_text(json.dumps(asdict(self.config), indent=2), "utf-8")

    # ---------- Zustand ----------
    def pid(self) -> int | None:
        reap_children()
        try:
            pid = int(self.pidfile.read_text().strip())
        except (OSError, ValueError):
            # QEMU löscht die pidfile schon beim Beenden, hält Ports (SPICE) aber noch kurz offen.
            # Bis der Prozess wirklich weg ist, gilt er weiter als laufend – sonst scheitert ein
            # sofortiger Neustart („binding socket to 127.0.0.1:5901 failed“).
            return self._recorded_pid()
        try:
            proc = psutil.Process(pid)
            if proc.status() == psutil.STATUS_ZOMBIE:
                _reap(pid)  # beendet, nur noch nicht eingesammelt
                return None
            if proc.is_running() and "qemu" in proc.name().lower():
                return pid
        except psutil.Error:
            pass
        return None

    def _recorded_pid(self) -> int | None:
        """QEMU-Prozess laut runtime.json – nur wenn er noch läuft und wirklich zu diesem Agent-PC gehört."""
        rt = self.runtime()
        pid = rt.get("pid")
        if not isinstance(pid, int):
            return None
        try:
            proc = psutil.Process(pid)
            if proc.status() == psutil.STATUS_ZOMBIE:
                _reap(pid)
                return None
            if (proc.is_running() and "qemu" in proc.name().lower()
                    and proc.create_time() >= float(rt.get("started", 0)) - 10
                    and qemu._esc(self.disk) in " ".join(proc.cmdline())):
                return pid
        except (psutil.Error, ValueError, TypeError):
            pass
        return None

    def is_running(self) -> bool:
        return self.pid() is not None

    def runtime(self) -> dict:
        try:
            return json.loads(self.runtime_file.read_text("utf-8"))
        except (OSError, ValueError):
            return {}

    def _update_runtime(self, **values) -> None:
        rt = self.runtime()
        rt.update(values)
        self.runtime_file.write_text(json.dumps(rt), "utf-8")

    def progress(self) -> Progress:
        """Liest den Einrichtungsfortschritt aus der seriellen Konsole des Gasts."""
        c = self.config
        step, total, title, ready = 0, 0, "", c.provisioned
        try:
            text = pct.strip_ansi(self.console_log.read_text("utf-8", errors="replace"))
        except OSError:
            text = ""
        for m in re.finditer(rf"{cloudinit.STEP_MARKER} (\d+)/(\d+) ([^\n]*)", text):
            step, total, title = int(m.group(1)), int(m.group(2)), m.group(3).strip()
        resume_step = 0
        for m in re.finditer(rf"{cloudinit.RESUME_MARKER} Schritt (\d+)", text):
            resume_step = int(m.group(1))
        if re.search(rf'(?<!"){cloudinit.READY_MARKER}(?!")', text):
            ready = True
        if ready and not c.provisioned:
            c.provisioned = True
            self.save()
            self._remove_seed()  # erst jetzt: Das Seed-ISO enthält das Passwort, wird aber bis READY gebraucht
        resumed = False
        if step and (step, total, title) != (c.setup_step, c.setup_total, c.setup_title) and not ready:
            c.setup_step, c.setup_total, c.setup_title = step, total, title
            self.save()
        elif not step and c.setup_step and not ready:
            # Neustart nach einem Abbruch: bis der Gast weitermacht, den letzten Stand zeigen
            step, total, title, resumed = c.setup_step, c.setup_total, c.setup_title, True
        percent = pct.setup_percent(text, c.apps, ready, c.first_boot_pending, running=self.is_running(),
                                    resume_step=c.setup_step, desktop=c.desktop)
        return Progress(step, total, title, ready, percent, resumed, resume_step)

    def eta_seconds(self, percent: float) -> float | None:
        """Grobe Restzeit der Einrichtung – gemessen ab dem letzten Start von QEMU."""
        rt = self.runtime()
        started = rt.get("started")
        if not started:
            return None
        return pct.eta_seconds(started, rt.get("start_percent", pct.BOOT[0]), time.time(), percent)

    def _remove_seed(self) -> None:
        # Seed enthält das Passwort im Klartext – nach der Einrichtung nicht mehr nötig.
        # Unter Windows kann QEMU die Datei noch geöffnet halten; dann beim nächsten Start.
        try:
            self.seed_iso.unlink(missing_ok=True)
        except OSError:
            pass

    def was_started(self) -> bool:
        """Lief QEMU schon einmal? (Die serielle Konsole wird beim Start angelegt bzw. rotiert.)"""
        try:
            if self.console_log.stat().st_size > 0:
                return True
        except OSError:
            pass
        return self.config.setup_step > 0 or any(self.path.glob("console-*.log"))

    # ---------- Vorlagen ----------
    def backing_file(self) -> Path | None:
        """Vorlage, auf der die Festplatte aufbaut (verknüpfter Agent-PC) – sonst None."""
        return qemu.backing_file(self.disk)

    def is_linked(self) -> bool:
        return self.backing_file() is not None

    def template_missing(self) -> bool:
        """Verknüpft, aber die Vorlage ist nicht erreichbar (z. B. Laufwerk fehlt)."""
        b = self.backing_file()
        return b is not None and not b.exists()

    def template_lock_pid(self) -> int | None:
        """PID des Prozesses, der gerade eine Vorlage aus diesem Agent-PC erstellt – sonst None."""
        try:
            pid = int((self.path / TEMPLATE_LOCK).read_text().strip())
        except (OSError, ValueError):
            return None
        return pid if psutil.pid_exists(pid) else None

    def _check_usable(self) -> None:
        if self.template_lock_pid() is not None:
            raise RuntimeError(f"Aus „{self.name}“ wird gerade eine Vorlage erstellt – bitte warten, bis das "
                               "fertig ist.")
        if self.template_missing():
            raise RuntimeError(f"„{self.name}“ ist mit einer Vorlage verknüpft, die nicht erreichbar ist:\n"
                               f"{self.backing_file()}\nIst das Laufwerk eingesteckt?")

    def make_independent(self, progress: Callable[[float], None] | None = None) -> None:
        """Verknüpften Agent-PC in eine unabhängige Festplatte umwandeln (übernimmt die Daten der Vorlage)."""
        if self.is_running():
            raise RuntimeError("Bitte den Agent-PC zuerst herunterfahren.")
        self._check_usable()
        if not self.is_linked():
            return
        qemu.rebase(qemu.find_binary("qemu-img", host.detect().os), self.disk, None, progress=progress)

    def status(self) -> str:
        running = self.is_running()
        if not running and self.template_missing():
            return STATUS_TEMPLATE_MISSING
        ready = self.progress().ready
        pending = self.config.first_boot_pending
        if running:
            if self.runtime().get("stopping_since"):
                return STATUS_STOPPING
            return "läuft" if ready and not pending else "wird eingerichtet"
        if pending and ready:
            return STATUS_READY_FOR_DESKTOP
        if pending and self.was_started():
            return STATUS_ABORTED
        return "gestoppt"

    def needs_window_start(self) -> bool:
        """Einrichtung fertig, Gast ausgeschaltet – jetzt mit Fenster starten."""
        return self.config.first_boot_pending and not self.is_running() and self.progress().ready

    def finish_first_boot(self, headless: bool = False) -> bool:
        """Nach der unsichtbaren Ersteinrichtung mit Fenster neu starten. True, wenn gestartet."""
        if not self.needs_window_start():
            return False
        self.start(headless=headless)
        return True

    def console_tail(self, lines: int = 200) -> str:
        """Letzte Zeilen der seriellen Konsole – ohne Terminal-Steuerzeichen."""
        try:
            text = self.console_log.read_text("utf-8", errors="replace")
        except OSError:
            return ""
        return "\n".join(pct.strip_ansi(text).splitlines()[-lines:])

    def abort_reason(self) -> diagnose.AbortInfo:
        """Warum endete QEMU vor dem Ende der Einrichtung? (wird je Start einmal ermittelt)"""
        rt = self.runtime()
        cached = rt.get("abort_reason")
        if cached and rt.get("abort_for") == rt.get("started"):
            return diagnose.AbortInfo(cached.get("reason", ""), cached.get("detail", ""))
        try:
            qemu_log = self.qemu_log.read_text("utf-8", errors="replace")[-4000:]
        except OSError:
            qemu_log = ""
        try:
            boot_time = psutil.boot_time()
        except Exception:  # noqa: BLE001
            boot_time = None
        info = diagnose.explain_abort(
            qemu_log=qemu_log, kernel_log=diagnose.kernel_log(rt.get("started")),
            pid=rt.get("pid"), started=rt.get("started"), boot_time=boot_time,
            powered_off=bool(rt.get("powered_off")), stop_requested=bool(rt.get("stopping_since")),
            console=self.console_tail(40),
        )
        if rt:
            self._update_runtime(abort_reason={"reason": info.reason, "detail": info.detail},
                                 abort_for=rt.get("started"))
        return info

    # ---------- Steuerung ----------
    def start(self, headless: bool | None = None) -> None:
        """Startet QEMU. Ohne Angabe: während der Ersteinrichtung ohne Fenster, sonst mit."""
        if self.is_running():
            return
        self._check_usable()
        p = self.progress()
        ready = p.ready
        if headless is None:
            headless = self.config.first_boot_pending and not ready
        if ready:
            self._remove_seed()
            if self.config.first_boot_pending:
                self.config.first_boot_pending = False
                self.save()
        self._launch(headless)
        if self.config.first_boot_pending:
            # Restzeit ab dem Stand beim Start schätzen (nach einem Abbruch nicht wieder ab 18 %)
            self._update_runtime(start_percent=max(pct.BOOT[0], p.percent))

    # ---------- Fernzugriff ----------
    def ensure_remote_ports(self) -> None:
        """Feste RDP-/SPICE-Ports vergeben (eindeutig über alle Agent-PCs), falls noch keine da sind."""
        if self.config.rdp_port and self.config.spice_port:
            return
        others = [m for m in list_vms() if m.path.resolve() != self.path.resolve()]
        used_rdp = {m.config.rdp_port for m in others}
        used_spice = {m.config.spice_port for m in others}
        if not self.config.rdp_port:
            self.config.rdp_port = remote.next_free_port(remote.FIRST_RDP_PORT, used_rdp)
        if not self.config.spice_port:
            self.config.spice_port = remote.next_free_port(remote.FIRST_SPICE_PORT, used_spice)
        self.save()

    def _ensure_spice_password(self) -> None:
        if not self.config.spice_password:
            self.config.spice_password = secrets.token_urlsafe(9)

    def remote_active(self) -> bool:
        """Ist der Fernzugriff gerade eingeschaltet (RDP-Weiterleitung aktiv)?"""
        return self.is_running() and bool(self.runtime().get("remote_on"))

    def set_remote(self, on: bool, permanent: bool = False, password: str | None = None,
                   ssh_prompt: bool = False) -> str:
        """Fernzugriff ein-/ausschalten – bei laufendem Agent-PC sofort, ohne Neustart.

        Ein: xrdp im Gast starten (per Gast-Agent, notfalls SSH) und die RDP-Weiterleitung
        ins Heimnetz per QMP setzen. „permanent“ = auch bei jedem weiteren Start, sonst nur
        bis zum Herunterfahren bzw. Neustart. Aus: beides rückgängig, auch „dauerhaft“.
        Gibt eine kurze Meldung für die Oberfläche zurück.
        """
        c = self.config
        running = self.is_running()
        if on and "xrdp" not in c.apps:
            raise RuntimeError("Im Agent-PC fehlt „Fernzugriff (RDP)“ – über „Programme hinzufügen …“ "
                               f"oder „bonys-agents install {self.name} xrdp“ nachrüsten.")
        if on and not running and not permanent:
            raise RuntimeError("Der Agent-PC läuft nicht. „Nur bis zum Herunterfahren“ geht nur bei laufendem "
                               "Agent-PC – sonst „dauerhaft“ wählen.")
        self.ensure_remote_ports()
        if not running:
            c.remote_permanent = on and permanent
            if on:
                self._ensure_spice_password()
            self.save()
            return ("Fernzugriff dauerhaft eingeschaltet – wirkt ab dem nächsten Start." if on
                    else "Fernzugriff ausgeschaltet.")
        if not self.progress().ready or c.first_boot_pending:
            raise RuntimeError("Der Agent-PC richtet sich noch ein – Fernzugriff geht erst danach.")
        rule = qemu.rdp_forward(REMOTE_ADDR, c.rdp_port)
        if on:
            # Gast: xrdp an. Dauerhaft = auch beim Booten; sonst nur jetzt (systemd vergisst es beim Neustart).
            script = ("systemctl enable --now xrdp" if permanent
                      else "systemctl disable xrdp xrdp-sesman >/dev/null 2>&1; systemctl start xrdp")
            self.guest_run(script, password=password, ssh_prompt=ssh_prompt)
            with qemu.QMP(self.runtime()["qmp_port"]) as q:
                q.hostfwd_remove(rule)  # falls schon da (z. B. dauerhaft → nur bis zum Herunterfahren)
                q.hostfwd_add(rule)
            if permanent:
                self._ensure_spice_password()
            c.remote_permanent = permanent
            self.save()
            self._update_runtime(remote_on=True, remote_boot_id=self._guest_boot_id())
            if permanent and not self.runtime().get("spice_lan"):
                return "Fernzugriff dauerhaft an. RDP geht sofort, SPICE aus dem Heimnetz ab dem nächsten Start."
            return "Fernzugriff an – " + ("dauerhaft." if permanent else "bis zum Herunterfahren.")
        # Aus: erst die Tür nach außen zu, dann xrdp im Gast stoppen
        with qemu.QMP(self.runtime()["qmp_port"]) as q:
            q.hostfwd_remove(rule)
        c.remote_permanent = False
        self.save()
        self._update_runtime(remote_on=False)
        self.guest_run("systemctl disable --now xrdp xrdp-sesman", password=password, ssh_prompt=ssh_prompt)
        if self.runtime().get("spice_lan"):
            # SPICE lauscht seit dem Start im Heimnetz und lässt sich nicht umstellen – Passwort sofort
            # verfallen lassen, dann kommt niemand mehr hinein. Nicht beim SPICE-Fenster: das braucht den Zugang.
            if c.display == "spice":
                return "Fernzugriff aus. SPICE bleibt bis zum Herunterfahren erreichbar (mit Passwort)."
            with qemu.QMP(self.runtime()["qmp_port"]) as q:
                q.execute("expire_password", protocol="spice", time="now")
        return "Fernzugriff ausgeschaltet."

    def _guest_boot_id(self) -> str:
        try:
            with qemu.GuestAgent(self.runtime()["qga_port"], timeout=3) as ga:
                return ga.run("cat /proc/sys/kernel/random/boot_id", timeout=10)[1].strip()
        except (qemu.GuestAgentError, RuntimeError, KeyError, TypeError):
            return ""

    def check_remote_reset(self) -> bool:
        """„Nur bis zum Herunterfahren“: nach einem Neustart im Gast die Weiterleitung entfernen.

        (Beendet sich QEMU, ist sie ohnehin weg.) True, wenn zurückgesetzt wurde.
        """
        rt = self.runtime()
        if not (rt.get("remote_on") and not self.config.remote_permanent and rt.get("remote_boot_id")):
            return False
        if not self.is_running():
            return False
        boot_id = self._guest_boot_id()
        if not boot_id or boot_id == rt["remote_boot_id"]:
            return False  # gleiche Sitzung – oder Gast gerade nicht erreichbar
        with qemu.QMP(rt["qmp_port"]) as q:
            q.hostfwd_remove(qemu.rdp_forward(REMOTE_ADDR, self.config.rdp_port))
        self._update_runtime(remote_on=False)
        return True

    def guest_run(self, script: str, password: str | None = None, ssh_prompt: bool = False,
                  timeout: float = 120) -> str:
        """Befehl als root im Gast – über den QEMU Guest Agent, notfalls per SSH.

        SSH braucht das Passwort des Agent-PCs: entweder ``password`` oder ``ssh_prompt``
        (ssh fragt im Terminal). Sonst NeedsPassword, damit die Oberfläche fragen kann.
        """
        try:
            with qemu.GuestAgent(self.runtime().get("qga_port") or 0, timeout=5) as ga:
                rc, out = ga.run(script, timeout=timeout)
        except qemu.GuestAgentError:
            if not password and not ssh_prompt:
                raise NeedsPassword("Der Gast-Agent antwortet nicht – für SSH wird das Passwort "
                                    "des Agent-PCs gebraucht.") from None
            rc = self._ssh(SSH_SUDO_SCRIPT, script, password)
            out = ""
            if rc == 255:
                raise RuntimeError("SSH-Verbindung oder Anmeldung fehlgeschlagen – stimmt das Passwort?") from None
        if rc != 0:
            raise RuntimeError(f"Befehl im Agent-PC fehlgeschlagen (Code {rc}): {out.strip()[-300:]}")
        return out

    def set_display(self, mode: str) -> None:
        if mode not in ("qemu", "spice"):
            raise ValueError("Anzeige: „qemu“ (QEMU-Fenster) oder „spice“ (SPICE-Fenster)")
        self.config.display = mode
        self.save()

    def set_screen(self, mode: str, size: str | None = None) -> None:
        """Bildschirm-Einstellung – wirkt ab dem nächsten Start (QEMU legt sie beim Start fest)."""
        screen.check_mode(mode)
        if size is not None:
            w, h = screen.parse_size(size)
            self.config.screen_size = f"{w}x{h}"
        self.config.screen_mode = mode
        self.save()

    def screen_settings(self) -> tuple[str, str]:
        """(Modus, Größe) – ungültige Werte aus einer von Hand geänderten vm.json fallen auf den Standard zurück."""
        mode = self.config.screen_mode if self.config.screen_mode in screen.MODES else screen.AUTO
        try:
            size = "x".join(map(str, screen.parse_size(self.config.screen_size)))
        except ValueError:
            size = screen.DEFAULT_SIZE
        return mode, size

    def screen_pending(self) -> bool:
        """Läuft der Agent-PC noch mit einer anderen Bildschirm-Einstellung als gespeichert?"""
        if not self.is_running():
            return False
        started = self.runtime().get("screen_setting")
        return started is not None and started != screen.guest_setting(*self.screen_settings())

    def update_display_driver(self, password: str | None = None, ssh_prompt: bool = False) -> str:
        """Skripte für die automatische Auflösung im laufenden Agent-PC einrichten bzw. erneuern."""
        if not self.is_running() or not self.progress().ready or self.config.first_boot_pending:
            raise RuntimeError(f"„{self.name}“ muss laufen und fertig eingerichtet sein.")
        self.guest_run(screen.guest_setup_script(), password=password, ssh_prompt=ssh_prompt, timeout=300)
        if self.runtime().get("screen_setting") is None:
            return ("Anzeige-Treiber eingerichtet. Damit die Auflösung dem Fenster folgt, den Agent-PC "
                    "einmal herunterfahren und neu starten.")
        mode, size = self.screen_settings()
        if mode == screen.AUTO:
            return "Anzeige-Treiber eingerichtet – die Auflösung folgt jetzt dem Fenster."
        return f"Anzeige-Treiber eingerichtet – Bildschirm: {screen.label(mode, size)}."

    def fullscreen(self) -> str:
        """QEMU-Fenster auf dem Monitor, auf dem es liegt, in den Vollbildmodus schalten (bzw. zurück).

        QEMU bietet dafür keinen QMP-Befehl – unter Linux/X11 wird Strg+Alt+F an das Fenster
        geschickt (xdotool). Sonst: RuntimeError mit dem Hinweis auf die Tastenkombination.
        """
        if not self.is_running():
            raise RuntimeError("Der Agent-PC läuft nicht.")
        hint = ("Vollbild ein/aus: im Fenster des Agent-PCs Strg+Alt+F drücken "
                "(macOS: ⌘+F, SPICE-Fenster: F11).")
        cmd = self.runtime().get("command") or []
        if "-display" in cmd[:-1] and cmd[cmd.index("-display") + 1] == "none":
            raise RuntimeError(hint)  # kein QEMU-Fenster (SPICE-Fenster bzw. unsichtbare Einrichtung)
        if not window_tools_available():
            if sys.platform.startswith("linux") and not shutil.which("xdotool"):
                hint += "\n\nDamit der Knopf das selbst erledigt: Programm „xdotool“ installieren."
            raise RuntimeError(hint)
        win = _find_qemu_window(self.name)
        if not win:
            raise RuntimeError("Das Fenster des Agent-PCs wurde nicht gefunden.\n\n" + hint)
        try:
            subprocess.run(["xdotool", "windowactivate", "--sync", win, "key", "--clearmodifiers", "ctrl+alt+f"],
                           capture_output=True, timeout=5, env=clean_env(), check=True)
        except (OSError, subprocess.SubprocessError) as e:
            raise RuntimeError(f"Vollbild ließ sich nicht umschalten ({e}).\n\n{hint}") from None
        return "Vollbild umgeschaltet – zurück mit Strg+Alt+F."

    def capabilities(self) -> dict:
        qemu_bin = qemu.find_binary(qemu.ARCH_BINARY[self.config.arch], host.detect().os)
        return qemu.capabilities(qemu_bin, storage.data_dir() / "qemu-capabilities.json")

    def remote_info(self) -> dict:
        """Verbindungsdaten für Anzeige und Kommandozeile."""
        c = self.config
        running = self.is_running()
        rt = self.runtime() if running else {}
        try:
            spice_ok = self.capabilities()["spice"]
        except qemu.QemuNotFound:
            spice_ok = False
        active = bool(rt.get("remote_on"))
        # SPICE hört nur zur Startzeit festgelegt: im Heimnetz nur, wenn beim Start dauerhaft an war.
        spice_lan = bool(rt.get("spice_lan")) if running else c.remote_permanent
        lan = [a.ip for a in remote.lan_addresses()]
        return {
            "active": active, "permanent": c.remote_permanent, "temporary": active and not c.remote_permanent,
            "addresses": lan, "rdp_port": c.rdp_port,
            "spice_port": c.spice_port if spice_ok else None, "spice_supported": spice_ok,
            "spice_lan": spice_ok and spice_lan,
            "username": c.username, "spice_password": c.spice_password if spice_ok and spice_lan else "",
            "rdp_installed": "xrdp" in c.apps, "display": c.display,
            # dauerhaft eingeschaltet, aber SPICE lief beim Start nur lokal
            "needs_restart": running and c.remote_permanent and spice_ok and not rt.get("spice_lan"),
        }

    def sync_remmina(self) -> None:
        """Remmina-Profile anlegen/aktualisieren (nur wenn Remmina installiert ist)."""
        if not self.config.rdp_port or not sys.platform.startswith("linux"):
            return
        try:
            spice = self.config.spice_port if self.capabilities()["spice"] else None
        except qemu.QemuNotFound:
            spice = None
        remote.sync_profiles(self.name, self.config.username, self.config.rdp_port, spice)

    def connect(self, protocol: str) -> None:
        protocol = protocol.upper()
        if not self.is_running():
            raise RuntimeError("Der Agent-PC läuft nicht.")
        info = self.remote_info()
        if protocol == "RDP" and not info["rdp_installed"]:
            raise RuntimeError("Im Agent-PC fehlt „Fernzugriff (RDP)“ – über „Programme hinzufügen …“ "
                               f"oder „bonys-agents install {self.name} xrdp“ nachrüsten.")
        if protocol == "RDP" and not info["active"]:
            raise RuntimeError("Der Fernzugriff ist aus – erst „Fernzugriff einschalten“.")
        if protocol == "SPICE" and not info["spice_supported"]:
            raise RuntimeError("Dieser QEMU-Build kann kein SPICE – bitte RDP verwenden.")
        self.sync_remmina()
        port = self.config.rdp_port if protocol == "RDP" else self.config.spice_port
        remote.connect(protocol, self.name, self.config.username, port, self.path)

    def _launch(self, headless: bool) -> None:
        info = host.detect()
        qemu_bin = qemu.find_binary(qemu.ARCH_BINARY[self.config.arch], info.os)
        firmware = qemu.find_aarch64_firmware(qemu_bin) if self.config.arch == "aarch64" else None
        qmp_port, ssh_port, qga_port = qemu.free_port(), qemu.free_port(), qemu.free_port()
        self.ensure_remote_ports()
        caps = qemu.capabilities(qemu_bin, storage.data_dir() / "qemu-capabilities.json")
        c = self.config
        spice_ok = caps["spice"]
        # SPICE-Fenster statt QEMU-Fenster: QEMU ohne eigenes Fenster, wir öffnen den Viewer.
        spice_window = not headless and c.display == "spice" and spice_ok and remote.spice_viewer_available()
        qemu_headless = headless or spice_window
        # Fernzugriff ist standardmäßig aus: kein RDP-Port, SPICE nur an diesem Rechner.
        # Nur bei „dauerhaft“ gleich beim Start ins Heimnetz (SPICE lässt sich später nicht mehr umstellen).
        remote_on = c.remote_permanent and not c.first_boot_pending and "xrdp" in c.apps
        spice_lan = spice_ok and remote_on
        pw_file = self.path / "spice-password"
        pw_file.unlink(missing_ok=True)
        if spice_lan:
            self._ensure_spice_password()
            self.save()
            pw_file.write_text(c.spice_password, "utf-8")
            pw_file.chmod(0o600)
        else:
            pw_file = None
        # Ton: ohne eigenes Fenster über SPICE, sonst über das Audiosystem des Hosts
        audio = "spice" if spice_ok and qemu_headless else qemu.host_audio_driver(info.os, caps["audio"])
        screen_mode, screen_size = self.screen_settings()
        screen_setting = screen.guest_setting(screen_mode, screen_size)
        spec = qemu.LaunchSpec(
            qemu_bin=qemu_bin, arch=c.arch, accel=info.accel,
            name=qemu_window_title(self.name),
            cpus=c.cpus, ram_mb=c.ram_mb,
            disk=self.disk, qmp_port=qmp_port, ssh_port=ssh_port,
            serial_log=self.console_log, pidfile=self.pidfile,
            seed_iso=self.seed_iso if self.seed_iso.exists() else None,
            firmware=firmware, headless=qemu_headless, qga_port=qga_port,
            display=qemu.window_display(info.os, caps.get("displays", []), screen_mode),
            screen=screen.start_size(screen_mode, screen_size), screen_setting=screen_setting,
            restrict_net=self.restrict_net,
            rdp_addr=REMOTE_ADDR if remote_on else None, rdp_port=c.rdp_port,
            spice_addr=REMOTE_ADDR if spice_lan else "127.0.0.1",
            spice_port=c.spice_port if spice_ok else None, spice_password_file=pw_file, audio=audio,
        )
        cmd = qemu.build_command(spec)
        # Feste Ports (SPICE, RDP) kurz frei werden lassen, z. B. direkt nach dem Ausschalten
        for port in (spec.spice_port, spec.rdp_port if spec.rdp_addr else None):
            if port:
                _wait_port_free(port)
        self.pidfile.unlink(missing_ok=True)
        rotate_log(self.console_log)  # QEMU legt die Konsole neu an – die alte bleibt als console-<Datum>.log
        log = self.qemu_log.open("w", encoding="utf-8")
        kwargs: dict = {"stdout": log, "stderr": subprocess.STDOUT, "stdin": subprocess.DEVNULL}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000008  # DETACHED_PROCESS
        else:
            kwargs["start_new_session"] = True
        proc = subprocess.Popen(cmd, env=clean_env(), **kwargs)
        _children[proc.pid] = proc
        self.runtime_file.write_text(
            json.dumps({"qmp_port": qmp_port, "ssh_port": ssh_port, "qga_port": qga_port, "accel": info.accel,
                        "command": cmd, "started": time.time(), "pid": proc.pid,
                        "remote_on": remote_on, "spice_lan": spice_lan,
                        "rdp_port": c.rdp_port, "spice_port": c.spice_port if spice_ok else None,
                        "audio": audio, "screen_setting": screen_setting}),
            "utf-8",
        )
        # Kurz warten: scheitert QEMU sofort (z. B. falsche Option), Fehler melden.
        for _ in range(30):
            time.sleep(0.2)
            if proc.poll() is not None:
                _children.pop(proc.pid, None)
                log.close()
                err = self.qemu_log.read_text("utf-8", errors="replace")[-2000:]
                raise RuntimeError("QEMU ist sofort beendet:\n" + err)
            if self.pidfile.exists():
                break
        log.close()
        if not qemu_headless and screen_mode != screen.FIXED and (spec.display or "").startswith("gtk"):
            # zoom-to-fit: QEMU öffnet das Fenster in der Größe des Firmware-Bilds (640x480) – auf Startgröße bringen
            size_qemu_window(self.name, *spec.screen)
        self.sync_remmina()
        if spice_window:
            _wait_for_port(c.spice_port)
            try:
                self.connect("SPICE")
            except RuntimeError:
                pass  # Viewer fehlt doch – Agent-PC läuft trotzdem (Verbinden-Knopf zeigt den Hinweis)

    def request_stop(self) -> bool:
        """Herunterfahren anstoßen und sofort zurückkehren.

        Zuerst über den Gast-Agent (systemctl poweroff im Gast – kein Desktop kann das abfangen;
        GNOME etwa beansprucht den Ausschaltknopf für sich und reagiert in VMs nicht verlässlich),
        sonst per ACPI-Ausschaltknopf. Merkt sich den Zeitpunkt, damit Oberfläche und Kommandozeile
        „wird heruntergefahren“ mit Countdown zeigen können. False, wenn QEMU nicht erreichbar war.
        """
        if not self.is_running():
            return True
        self.mark_stopping()
        if self._guest_shutdown():
            return True
        try:
            with qemu.QMP(self.runtime().get("qmp_port"), timeout=3) as q:
                q.execute("system_powerdown")
            return True
        except (OSError, RuntimeError, TypeError, ValueError):
            return False

    def _guest_shutdown(self) -> bool:
        port = self.runtime().get("qga_port")
        if not port:
            return False
        try:
            with qemu.GuestAgent(port, timeout=2) as ga:
                ga.shutdown()
            return True
        except qemu.GuestAgentError:
            return False

    def mark_stopping(self) -> None:
        """Status sofort auf „wird heruntergefahren“ setzen (Countdown zählt ab dem ersten Mal)."""
        if self.is_running() and not self.runtime().get("stopping_since"):
            self._update_runtime(stopping_since=time.time())

    def stopping_for(self) -> float | None:
        """Sekunden seit dem Herunterfahren-Befehl – None, wenn nicht gerade heruntergefahren wird."""
        since = self.runtime().get("stopping_since")
        if not since or not self.is_running():
            return None
        return max(0.0, time.time() - since)

    def power_off(self, timeout: float = 5) -> None:
        """Sofort ausschalten wie beim Stecker-Ziehen: QMP „quit“, notfalls den Prozess beenden."""
        pid = self.pid()
        if pid is None:
            return
        self._update_runtime(powered_off=True)  # für die Anzeige der Abbruch-Ursache
        try:
            with qemu.QMP(self.runtime().get("qmp_port"), timeout=2) as q:
                q.execute("quit")
        except (OSError, RuntimeError, TypeError, ValueError):
            pass
        if not self._wait_stopped(timeout):
            try:
                psutil.Process(pid).kill()
            except psutil.Error:
                pass
            self._wait_stopped(5)
        # QEMU löscht seine pidfile kurz vor dem Ende – selbst gestartete Prozesse gleich einsammeln.
        proc = _children.pop(pid, None)
        if proc is not None:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _children[pid] = proc

    def _wait_stopped(self, timeout: float) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self.is_running():
                return True
            time.sleep(0.25)
        return not self.is_running()

    def stop(self, force: bool = False, timeout: float = STOP_TIMEOUT) -> bool:
        """Herunterfahren und warten (Kommandozeile). Nach ``timeout`` Sekunden hart ausschalten.

        True, wenn hart ausgeschaltet werden musste.
        """
        if not self.is_running():
            return False
        if force or not self.request_stop():
            self.power_off()
            return True
        if self._wait_stopped(timeout):
            return False
        self.power_off()
        return True

    def missing_apps(self) -> list[apps.AppSpec]:
        return [a for a in apps.APPS.values() if a.id not in self.config.apps]

    def install_app(self, app_id: str, password: str | None = None,
                    log: Callable[[str], None] | None = None) -> None:
        """App nachträglich per SSH installieren (Agent-PC muss laufen und eingerichtet sein).

        Ohne ``password`` fragt ssh selbst im Terminal. Mit ``password`` wird es nur über die
        Umgebung an ein kurzlebiges SSH_ASKPASS-Hilfsskript gereicht – nie gespeichert.
        """
        spec = apps.APPS.get(app_id)
        if spec is None:
            raise ValueError(f"Unbekannte App '{app_id}'. Verfügbar: {', '.join(apps.APPS)}")
        if app_id in self.config.apps:
            raise ValueError(f"{spec.name} ist in „{self.name}“ bereits installiert.")
        if not self.is_running() or not self.progress().ready or self.config.first_boot_pending:
            raise RuntimeError("Der Agent-PC muss laufen und fertig eingerichtet sein.")
        script = cloudinit.app_install_script(spec, self.config.username)
        rc = self._ssh(SSH_SUDO_SCRIPT, script, password, log)
        if rc == 255:
            raise RuntimeError("SSH-Verbindung oder Anmeldung fehlgeschlagen – stimmt das Passwort?")
        if rc != 0:
            raise RuntimeError(f"Installation von {spec.name} fehlgeschlagen (Code {rc}) – siehe Ausgabe.")
        self.config.apps = [a for a in apps.APPS if a in self.config.apps or a == app_id] \
            + [a for a in self.config.apps if a not in apps.APPS]
        self.save()

    def installed_desktops(self) -> list[str]:
        return [self.config.desktop] + [d for d in self.config.extra_desktops if d != self.config.desktop]

    def install_desktop(self, desktop_id: str, make_default: bool = True, password: str | None = None,
                        log: Callable[[str], None] | None = None) -> None:
        """Weiteren Desktop im laufenden Agent-PC installieren (per SSH, wie Programme hinzufügen).

        ``make_default``: künftig automatisch in diesen Desktop anmelden (wirkt ab dem nächsten Start).
        Der bisherige Desktop bleibt installiert und lässt sich am Anmeldebildschirm weiter wählen.
        """
        spec = desktops.get(desktop_id)
        if desktop_id in self.installed_desktops():
            if not make_default or desktop_id == self.config.desktop:
                raise ValueError(f"{spec.name} ist in „{self.name}“ bereits installiert.")
        if not self.is_running() or not self.progress().ready or self.config.first_boot_pending:
            raise RuntimeError("Der Agent-PC muss laufen und fertig eingerichtet sein.")
        script = cloudinit.desktop_install_script(spec, self.config.username, make_default)
        rc = self._ssh(SSH_SUDO_SCRIPT, script, password, log)
        if rc == 255:
            raise RuntimeError("SSH-Verbindung oder Anmeldung fehlgeschlagen – stimmt das Passwort?")
        if rc != 0:
            raise RuntimeError(f"Installation von {spec.name} fehlgeschlagen (Code {rc}) – siehe Ausgabe.")
        c = self.config
        installed = self.installed_desktops() + ([desktop_id] if desktop_id not in self.installed_desktops() else [])
        if make_default:
            c.desktop = desktop_id
        c.extra_desktops = [d for d in installed if d != c.desktop]
        self.save()

    def _ssh(self, remote_cmd: str, script: str, password: str | None = None,
             log: Callable[[str], None] | None = None) -> int:
        """``script`` per SSH an ``remote_cmd`` im Gast schicken. Gibt den Exit-Code zurück (255 = SSH).

        Ohne ``password`` fragt ssh selbst im Terminal. Mit ``password`` wird es nur über die
        Umgebung an ein kurzlebiges SSH_ASKPASS-Hilfsskript gereicht – nie gespeichert.
        """
        ssh = shutil.which("ssh")
        if not ssh:
            raise RuntimeError("Das Programm „ssh“ wurde nicht gefunden (Paket openssh-client).")
        cmd = [
            ssh, "-p", str(self.runtime().get("ssh_port")),
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", f"UserKnownHostsFile={self.path / 'known_hosts'}",
            "-o", "ConnectTimeout=15",
            f"{self.config.username}@127.0.0.1",
            remote_cmd,
        ]
        env = clean_env()
        with tempfile.TemporaryDirectory(prefix="bonys-ssh-") as tmp:
            if password:
                askpass = Path(tmp) / "askpass.sh"
                askpass.write_text('#!/bin/sh\nprintf "%s\\n" "$BONYS_SSH_PASSWORD"\n')
                askpass.chmod(0o700)
                env.update(SSH_ASKPASS=str(askpass), SSH_ASKPASS_REQUIRE="force",
                           DISPLAY=env.get("DISPLAY", ":0"), BONYS_SSH_PASSWORD=password)
                cmd[1:1] = ["-o", "NumberOfPasswordPrompts=1"]
            pipe = subprocess.PIPE if log else None
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=pipe,
                                    stderr=subprocess.STDOUT if log else None, env=env,
                                    text=True, encoding="utf-8", errors="replace")
            proc.stdin.write(script)
            proc.stdin.close()
            if log:
                for line in proc.stdout:
                    log(line.rstrip("\n"))
            return proc.wait()

    def upgrade(self, password: str | None = None, ssh_prompt: bool = False,
                log: Callable[[str], None] | None = None, timeout: float = 4 * 3600) -> UpgradeResult:
        """Agent-PC aktualisieren: apt full-upgrade, Flatpaks und die installierten KI-Werkzeuge.

        Läuft über den QEMU Guest Agent (die Ausgabe kommt live über die serielle Konsole),
        sonst per SSH – dafür braucht es das Passwort (``password``) bzw. ``ssh_prompt``.
        """
        if not self.is_running() or not self.progress().ready or self.config.first_boot_pending:
            raise RuntimeError(f"„{self.name}“ muss laufen und fertig eingerichtet sein.")
        script = apps.upgrade_script(self.config.apps, self.config.username)
        emit = log or (lambda line: None)
        port = self.runtime().get("qga_port") or 0
        try:
            pos = self.console_log.stat().st_size  # Ausgabe ab hier live weiterreichen
        except OSError:
            pos = 0
        try:
            with qemu.GuestAgent(port, timeout=5) as ga:
                pid = ga.execute("guest-exec", path="/bin/bash", arg=["-c", script],
                                 **{"capture-output": True})["pid"]
        except qemu.GuestAgentError:
            pid = None
        if pid is not None:
            rc, out = self._guest_exec_follow(port, pid, pos, emit, timeout)
        else:
            if not password and not ssh_prompt:
                raise NeedsPassword("Der Gast-Agent antwortet nicht – für SSH wird das Passwort "
                                    "des Agent-PCs gebraucht.")
            lines: list[str] = []

            def collect(line: str) -> None:
                lines.append(line)
                emit(line)

            rc = self._ssh(SSH_SUDO_SCRIPT, script, password, collect)
            if rc == 255:
                raise RuntimeError("SSH-Verbindung oder Anmeldung fehlgeschlagen – stimmt das Passwort?")
            out = "\n".join(lines)
        return UpgradeResult(ok=rc == 0, reboot_required=apps.REBOOT_MARKER in out, exit_code=rc)

    def _guest_exec_follow(self, port: int, pid: int, pos: int, emit: Callable[[str], None],
                           timeout: float) -> tuple[int, str]:
        """Auf einen per Gast-Agent gestarteten Befehl warten, die serielle Konsole live weiterreichen.

        Für jede Abfrage neu verbinden: qemu-ga bedient nur einen Client gleichzeitig – sonst wäre
        der Gast-Agent während eines langen Updates für alles andere blockiert.
        """
        deadline = time.time() + timeout
        pending = ""
        st: dict = {}
        while True:
            try:
                with qemu.GuestAgent(port, timeout=10) as ga:
                    st = ga.execute("guest-exec-status", pid=pid)
            except qemu.GuestAgentError:
                st = {}  # kurz belegt (z. B. andere Abfrage der App) – beim nächsten Mal wieder
            try:
                with self.console_log.open("rb") as f:
                    f.seek(pos)
                    chunk = f.read()
                pos += len(chunk)
            except OSError:
                chunk = b""
            pending += pct.strip_ansi(chunk.decode("utf-8", errors="replace"))
            *complete, pending = pending.split("\n")
            for line in complete:
                emit(line)
            if st.get("exited"):
                break
            if time.time() > deadline:
                raise RuntimeError(f"Aktualisierung nicht innerhalb von {timeout / 3600:.0f} Stunden fertig.")
            time.sleep(1)
        if pending:
            emit(pending)
        out = b"".join(base64.b64decode(st.get(k, "")) for k in ("out-data", "err-data"))
        return int(st.get("exitcode", 0)), out.decode("utf-8", errors="replace")

    def ssh_command(self) -> list[str]:
        """Anmeldung per SSH als Benutzer des Agent-PCs (Port aus runtime.json)."""
        port = self.runtime().get("ssh_port")
        if not self.is_running() or not port:
            raise RuntimeError("Der Agent-PC läuft nicht.")
        ssh = shutil.which("ssh") or "ssh"
        return [ssh, "-p", str(port), "-o", "StrictHostKeyChecking=accept-new",
                "-o", f"UserKnownHostsFile={self.path / 'known_hosts'}", f"{self.config.username}@127.0.0.1"]

    def open_terminal(self) -> None:
        """Terminalfenster auf dem Host mit SSH in den Agent-PC öffnen (fragt dort nach dem Passwort)."""
        spawn_detached(terminal_command(self.ssh_command()))

    def fetch_setup_logs(self, password: str | None = None, ssh_prompt: bool = False) -> list[Path]:
        """Einrichtungsprotokolle aus dem Gast in den VM-Ordner kopieren (Gast-Agent, sonst SSH)."""
        if not self.is_running():
            raise RuntimeError("Der Agent-PC läuft nicht.")
        sep = "=====BONYS-FILE "
        script = "".join(f'echo "{sep}{src}"; cat {src} 2>&1 || true\n' for src in GUEST_SETUP_LOGS)
        try:
            with qemu.GuestAgent(self.runtime().get("qga_port") or 0, timeout=3) as ga:
                out = ga.run(script, timeout=60)[1]
        except (qemu.GuestAgentError, RuntimeError):
            if not password and not ssh_prompt:
                raise NeedsPassword("Der Gast-Agent ist noch nicht installiert – für SSH wird das Passwort "
                                    "des Agent-PCs gebraucht.") from None
            lines: list[str] = []
            rc = self._ssh(SSH_SUDO_SCRIPT, script, password, lines.append)
            if rc == 255:
                raise RuntimeError("SSH-Verbindung oder Anmeldung fehlgeschlagen – stimmt das Passwort? "
                                   "(Ganz am Anfang der Einrichtung gibt es den Benutzer noch nicht.)") from None
            out = "\n".join(lines)
        files: list[Path] = []
        for chunk in out.split(sep)[1:]:
            src, _, content = chunk.partition("\n")
            name = GUEST_SETUP_LOGS.get(src.strip())
            if name:
                target = self.path / name
                target.write_text(pct.strip_ansi(content), "utf-8")
                files.append(target)
        if not files:
            raise RuntimeError("Keine Protokolle erhalten.")
        return files

    def resize(self, new_gb: int) -> None:
        """Virtuelle Festplatte vergrößern (nie verkleinern). Der Gast erweitert die Partition beim Start."""
        check_disk_gb(new_gb)
        if self.is_running():
            raise RuntimeError("Bitte den Agent-PC zuerst herunterfahren.")
        self._check_usable()
        if new_gb <= self.config.disk_gb:
            raise ValueError(f"Nur vergrößern möglich: aktuell {format_gb(self.config.disk_gb)}, "
                             f"gewünscht {format_gb(new_gb)}.")
        qemu.resize_disk(qemu.find_binary("qemu-img", host.detect().os), self.disk, new_gb)
        self.config.disk_gb = new_gb
        self.save()

    def delete(self) -> None:
        if self.template_lock_pid() is not None:
            raise RuntimeError(f"Aus „{self.name}“ wird gerade eine Vorlage erstellt – bitte warten.")
        self.stop(force=True)
        shutil.rmtree(self.path, ignore_errors=True)
        storage.forget(self.name)
        remote.remove_profiles(self.name)


@dataclass
class UpgradeResult:
    ok: bool
    reboot_required: bool
    exit_code: int = 0

    def message(self, name: str) -> str:
        text = f"„{name}“ ist aktualisiert." if self.ok else \
            f"„{name}“: Aktualisierung mit Fehlern beendet (Code {self.exit_code}) – siehe Ausgabe."
        if self.reboot_required:
            text += " Ein Neustart des Agent-PCs ist nötig."
        return text


class NeedsPassword(RuntimeError):
    """Für diesen Schritt wird das Passwort des Agent-PCs gebraucht (SSH statt Gast-Agent)."""


def qemu_window_title(name: str) -> str:
    return f"Bony's Agents – {name}"


def window_title_pattern(name: str) -> str:
    """Suchmuster (POSIX-Regex) für den Titel des QEMU-Fensters: „QEMU (Bony's Agents – NAME)“, ggf. mit Zusatz."""
    return r"\(" + qemu_window_title(name) + r"\)"


def _find_qemu_window(name: str) -> str | None:
    try:
        out = subprocess.run(["xdotool", "search", "--name", window_title_pattern(name)],
                             capture_output=True, text=True, timeout=5, env=clean_env()).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return None
    return out[-1] if out else None


def size_qemu_window(name: str, width: int, height: int, timeout: float = 8.0) -> bool:
    """Bildfläche des QEMU-Fensters auf width x height setzen (nur Linux/X11 mit xdotool, sonst nichts)."""
    if not window_tools_available():
        return False
    deadline = time.time() + timeout
    while time.time() < deadline:
        win = _find_qemu_window(name)
        if win:
            try:
                subprocess.run(["xdotool", "windowsize", win, str(width), str(height + screen.GTK_MENUBAR)],
                               capture_output=True, timeout=5, env=clean_env(), check=True)
                return True
            except (OSError, subprocess.SubprocessError):
                return False
        time.sleep(0.3)
    return False


def window_tools_available() -> bool:
    """Kann der Vollbild-Knopf das QEMU-Fenster selbst umschalten? (Linux mit X11 und xdotool)"""
    return (sys.platform.startswith("linux") and os.environ.get("XDG_SESSION_TYPE", "x11") != "wayland"
            and bool(os.environ.get("DISPLAY")) and shutil.which("xdotool") is not None)


# Fernzugriff „an“ = aus dem Heimnetz erreichbar (lokal geht es über dieselbe Weiterleitung).
REMOTE_ADDR = "0.0.0.0"
# Skript erst vollständig per stdin empfangen, dann ohne stdin als root ausführen.
SSH_SUDO_SCRIPT = 'sudo bash -c \'f="$(mktemp)" && cat > "$f" && bash "$f" </dev/null; rc=$?; rm -f "$f"; exit $rc\''


def rotate_log(path: Path, keep: int = KEEP_CONSOLE_LOGS) -> Path | None:
    """``console.log`` → ``console-<Datum>.log``, damit ein Neustart die Ausgabe nicht überschreibt.

    Höchstens ``keep`` alte Protokolle bleiben erhalten. Gibt die neue Datei zurück (oder None).
    """
    try:
        if path.stat().st_size == 0:
            return None
    except OSError:
        return None
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    target = path.with_name(f"{path.stem}-{stamp}{path.suffix}")
    n = 1
    while target.exists():
        target = path.with_name(f"{path.stem}-{stamp}-{n}{path.suffix}")
        n += 1
    try:
        os.replace(path, target)
    except OSError:
        return None  # z. B. unter Windows noch geöffnet – dann überschreibt QEMU eben
    # die gerade rotierte Datei bleibt immer; von den übrigen die neuesten keep-1
    others = sorted((f for f in path.parent.glob(f"{path.stem}-*{path.suffix}") if f != target),
                    key=lambda f: (f.stat().st_mtime, f.name))
    for f in others[:max(len(others) - (keep - 1), 0)]:
        f.unlink(missing_ok=True)
    return target


def _wait_port_free(port: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while not remote.port_free(port):
        if time.time() > deadline:
            return False
        time.sleep(0.3)
    return True


def _wait_for_port(port: int, timeout: float = 8.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.3)


# ---------- Sammlung ----------
@dataclass
class MissingVM:
    """Ein bekannter Agent-PC, dessen Laufwerk gerade nicht da ist."""

    name: str
    path: Path

    def status(self) -> str:
        return "nicht verfügbar"


def _scan(library: Path) -> list[Path]:
    try:
        return sorted(p for p in library.iterdir() if (p / "vm.json").is_file())
    except OSError:
        return []


def list_vms() -> list[VM]:
    """Alle erreichbaren Agent-PCs aus allen Speicherorten."""
    found: dict[str, VM] = {}
    for lib in storage.libraries():
        for p in _scan(lib):
            try:
                machine = VM(p)
            except (OSError, ValueError, TypeError):
                continue  # beschädigte vm.json überspringen
            if machine.name not in found:
                found[machine.name] = machine
    known = storage.load_settings()["known"]
    for name, machine in found.items():
        if known.get(name) != str(machine.path):
            storage.remember(name, machine.path)  # z. B. neuer Laufwerksbuchstabe
    return sorted(found.values(), key=lambda m: m.name.lower())


def list_all() -> list[VM | MissingVM]:
    """Wie list_vms(), plus bekannte Agent-PCs auf gerade fehlenden Laufwerken."""
    present = list_vms()
    names = {m.name for m in present}
    missing = [MissingVM(n, Path(p)) for n, p in storage.load_settings()["known"].items() if n not in names]
    return sorted([*present, *missing], key=lambda m: m.name.lower())


def get(name: str) -> VM:
    for m in list_vms():
        if m.name == name:
            return m
    known = storage.load_settings()["known"].get(name)
    if known:
        raise KeyError(f"Agent-PC '{name}' ist nicht verfügbar – liegt auf {known}. Ist das Laufwerk eingesteckt?")
    raise KeyError(f"Agent-PC '{name}' gibt es nicht")


def forget_missing(name: str) -> None:
    """Fehlenden Agent-PC aus der Liste nehmen (löscht nichts auf dem Laufwerk)."""
    storage.forget(name)


def import_path(path: Path) -> list[VM]:
    """Vorhandene Agent-PCs hinzufügen: einen VM-Ordner oder einen ganzen Speicherort."""
    path = Path(path)
    if (path / "vm.json").is_file():
        library = path.parent
    elif _scan(path):
        library = path
    else:
        raise ValueError(f"In {path} wurde kein Agent-PC gefunden (keine vm.json).")
    storage.add_location(library)
    storage.invalidate_cache()
    added = [VM(p) for p in _scan(library)]
    for m in added:
        storage.remember(m.name, m.path)
    return added


def _same_device(a: Path, b: Path) -> bool:
    return os.stat(a).st_dev == os.stat(b).st_dev


def move(name: str, target_library: Path, progress: ProgressFn | None = None) -> VM:
    """Agent-PC an einen anderen Speicherort verschieben (muss ausgeschaltet sein)."""
    machine = get(name)
    if machine.is_running():
        raise RuntimeError("Bitte den Agent-PC zuerst herunterfahren.")
    machine._check_usable()
    backing = machine.backing_file()
    target_library = Path(target_library)
    dest = target_library / machine.name
    if dest.resolve() == machine.path.resolve():
        return machine
    if dest.exists():
        raise FileExistsError(f"Im Ziel gibt es schon einen Ordner {dest}")
    need_gb = max(1, -(-machine.size_on_disk() // storage.GB))
    chk = storage.check_location(target_library, 0, create=True, min_free_gb=0)
    if not chk.ok:
        raise RuntimeError(" ".join(chk.errors))

    # Gleiches Laufwerk: einfach umbenennen – dauert keine Sekunde.
    if _same_device(machine.path, target_library):
        os.replace(machine.path, dest)
        if backing is not None:
            # Verweis auf die Vorlage ist relativ gespeichert – an den neuen Ort anpassen
            qemu.rebase(qemu.find_binary("qemu-img", host.detect().os), dest / "disk.qcow2", backing, unsafe=True)
        storage.add_location(target_library)
        storage.remember(machine.name, dest)
        storage.invalidate_cache()
        if progress:
            progress("done", 1.0, f"Verschoben nach {dest}")
        return VM(dest)

    # Verknüpft und anderes Laufwerk: die Vorlage bleibt zurück – Festplatte als unabhängige Kopie schreiben.
    template_size = backing.stat().st_size if backing is not None else 0
    if shutil.disk_usage(target_library).free < machine.size_on_disk() + template_size + 256 * 1024 * 1024:
        raise RuntimeError(f"Zu wenig Platz im Ziel: der Agent-PC belegt {need_gb} GB"
                           + (" (plus die Daten der Vorlage)." if backing is not None else "."))

    files = [f for f in machine.path.rglob("*") if f.is_file() and f.name not in ("qemu.pid", "runtime.json")]
    disk_share = 0
    if backing is not None:
        files = [f for f in files if f != machine.disk]
        disk_share = template_size + machine.disk.stat().st_size
    total = (sum(f.stat().st_size for f in files) + disk_share) or 1
    done = 0
    tmp = target_library / f".{machine.name}.verschieben"
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        if backing is not None:

            def flat(frac: float) -> None:
                if progress:
                    progress("move", frac * disk_share / total,
                             "Schreibe unabhängige Kopie der Festplatte (Vorlage bleibt auf dem alten Laufwerk) …")

            qemu.convert_disk(qemu.find_binary("qemu-img", host.detect().os), machine.disk,
                              tmp / "disk.qcow2", progress=flat)
            done = disk_share
        for f in files:
            out = tmp / f.relative_to(machine.path)
            out.parent.mkdir(parents=True, exist_ok=True)
            with f.open("rb") as src, out.open("wb") as dst:
                while chunk := src.read(8 * 1024 * 1024):
                    dst.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress("move", done / total, f"Kopiere {done // host.MB} / {total // host.MB} MB …")
            if out.stat().st_size != f.stat().st_size:
                raise OSError(f"Kopie von {f.name} unvollständig")
        os.replace(tmp, dest)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    shutil.rmtree(machine.path, ignore_errors=True)
    storage.add_location(target_library)
    storage.remember(machine.name, dest)
    storage.invalidate_cache()
    if progress:
        note = " – jetzt als unabhängige Kopie (die Vorlage liegt auf einem anderen Laufwerk)" if backing else ""
        progress("done", 1.0, f"Verschoben nach {dest}{note}")
    return VM(dest)


def move_makes_independent(machine: VM, target_library: Path) -> bool:
    """Wird ein verknüpfter Agent-PC beim Verschieben nach ``target_library`` unabhängig?"""
    if not machine.is_linked():
        return False
    probe = storage._existing_parent(Path(target_library))
    try:
        return not _same_device(machine.path, probe)
    except OSError:
        return True


def create(
    name: str,
    password: str,
    *,
    cpus: int | None = None,
    ram_mb: int | None = None,
    disk_gb: int | None = None,
    username: str = "agent",
    app_ids: list[str] | None = None,
    keyboard: str = "de",
    timezone_name: str = "Europe/Berlin",
    location: Path | None = None,
    progress: ProgressFn | None = None,
    template: str | None = None,
    desktop: str = desktops.DEFAULT,
    linked: bool | None = None,
) -> VM:
    """Neuen Agent-PC anlegen – neu installiert (Debian-Image + Einrichtung) oder aus einer Vorlage.

    Aus einer Vorlage: ``linked`` True = verknüpft (Festplatte baut auf der Vorlage auf, nur auf
    demselben Laufwerk), False = unabhängige Kopie, None = verknüpft, wenn möglich. Benutzer und
    Apps kommen dann aus der Vorlage.
    """
    def report(phase: str, frac: float, msg: str) -> None:
        if progress:
            progress(phase, frac, msg)

    if not NAME_RE.match(name):
        raise ValueError("Name: 1–40 Zeichen, nur Buchstaben, Ziffern, - und _")
    if template is not None:
        return _create_from_template(name, password, template, linked=linked, cpus=cpus, ram_mb=ram_mb,
                                     disk_gb=disk_gb, keyboard=keyboard, location=location, report=report)
    disk_gb = DEFAULT_DISK_GB if disk_gb is None else disk_gb
    desktops.get(desktop)
    if not re.match(r"^[a-z_][a-z0-9_-]{0,31}$", username):
        raise ValueError("Benutzername: kleingeschrieben, beginnt mit Buchstabe")
    if len(password) < 4:
        raise ValueError("Passwort: mindestens 4 Zeichen")
    check_disk_gb(disk_gb)
    if any(m.name == name for m in list_all()):
        raise FileExistsError(f"Agent-PC '{name}' existiert bereits")
    library = Path(location) if location else storage.preferred_library()
    path = library / name
    if path.exists():
        raise FileExistsError(f"Ordner {path} existiert bereits")

    info = host.detect()
    app_specs = apps.resolve(app_ids if app_ids is not None else apps.default_app_ids())
    qemu_img = qemu.find_binary("qemu-img", info.os)
    qemu.find_binary(qemu.ARCH_BINARY[info.arch], info.os)  # früh prüfen

    cfg = VMConfig(
        name=name, arch=info.arch,
        cpus=max(1, min(cpus or info.default_vm_cpus, info.cpus)),
        ram_mb=max(host.MIN_VM_RAM_MB, ram_mb or info.default_vm_ram_mb),
        disk_gb=disk_gb, username=username,
        apps=[a.id for a in app_specs], keyboard=keyboard, timezone=timezone_name,
        desktop=desktop, first_boot_pending=True,
    )

    chk = storage.check_location(library, cfg.disk_gb, create=True)
    if not chk.ok:
        raise RuntimeError(" ".join(chk.errors))

    base = images.debian_image(info.arch)
    report("download", 0.0, f"Lade {base.name} …")

    def dl(done: int, total: int) -> None:
        frac = done / total if total else 0.0
        report("download", frac, f"{base.name}: {done // host.MB} / {total // host.MB} MB")

    # Bild-Cache am Ziel-Speicherort – vorhandene Kopien von anderen Orten werden wiederverwendet.
    other_caches = [lib / IMAGES_DIRNAME for lib in storage.libraries() if lib != library]
    base_path = images.ensure_image(base, library / IMAGES_DIRNAME, dl, reuse_from=other_caches)

    path.mkdir(parents=True)
    try:
        report("disk", 0.0, f"Erstelle {cfg.disk_gb}-GB-Festplatte …")
        qemu.create_disk(qemu_img, base_path, path / "disk.qcow2", cfg.disk_gb)
        report("seed", 0.0, "Schreibe Einrichtungsdaten …")
        guest = cloudinit.GuestConfig(
            hostname=name.lower().replace("_", "-"), username=username, password=password,
            apps=app_specs, keyboard=keyboard, timezone=timezone_name, desktop=desktop,
        )
        cloudinit.write_seed_iso(path / "seed.iso", guest, instance_id=f"bonys-{uuid.uuid4()}")
        (path / "vm.json").write_text(json.dumps(asdict(cfg), indent=2), "utf-8")
    except Exception:
        shutil.rmtree(path, ignore_errors=True)
        raise
    if library != storage.default_library():
        storage.add_location(library)
    storage.remember(name, path)
    storage.invalidate_cache()
    machine = VM(path)
    machine.ensure_remote_ports()  # feste Ports für RDP/SPICE gleich beim Anlegen
    report("done", 1.0, f"Agent-PC angelegt in {path}")
    return machine


def _create_from_template(name: str, password: str, template_name: str, *, linked: bool | None,
                          cpus: int | None, ram_mb: int | None, disk_gb: int | None, keyboard: str,
                          location: Path | None, report: ProgressFn) -> VM:
    """Agent-PC aus einer Vorlage: nur Festplatte (verknüpft oder kopiert) und ein kleines Seed."""
    from bonys_agents import templates

    t0 = time.monotonic()
    if len(password) < 4:
        raise ValueError("Passwort: mindestens 4 Zeichen")
    tpl = templates.get(template_name)
    info = host.detect()
    if tpl.arch != info.arch:
        raise ValueError(f"Die Vorlage „{tpl.name}“ ist für {tpl.arch}, dieser Rechner ist {info.arch}.")
    disk_gb = tpl.disk_gb if disk_gb is None else disk_gb
    check_disk_gb(disk_gb)
    if disk_gb < tpl.disk_gb:
        raise ValueError(f"Festplatte: mindestens so groß wie die Vorlage ({format_gb(tpl.disk_gb)}).")
    if any(m.name == name for m in list_all()):
        raise FileExistsError(f"Agent-PC '{name}' existiert bereits")
    library = Path(location) if location else storage.preferred_library()
    path = library / name
    if path.exists():
        raise FileExistsError(f"Ordner {path} existiert bereits")
    chk = storage.check_location(library, disk_gb, create=True, min_free_gb=1)
    if not chk.ok:
        raise RuntimeError(" ".join(chk.errors))
    same = templates.same_drive(tpl, library)
    if linked is None:
        linked = same
    if linked and not same:
        raise ValueError("„Schnell (verknüpft)“ geht nur, wenn der Agent-PC auf demselben Laufwerk liegt wie die "
                         f"Vorlage ({tpl.library}). Sonst „Unabhängig (vollständige Kopie)“ wählen.")
    if not linked and shutil.disk_usage(library).free < tpl.size * 3 + storage.GB:
        raise RuntimeError(f"Zu wenig Platz für eine vollständige Kopie der Vorlage ({tpl.size / storage.GB:.1f} GB "
                           "komprimiert, entpackt deutlich mehr).")
    qemu_img = qemu.find_binary("qemu-img", info.os)
    qemu.find_binary(qemu.ARCH_BINARY[info.arch], info.os)

    cfg = VMConfig(
        name=name, arch=info.arch,
        cpus=max(1, min(cpus or info.default_vm_cpus, info.cpus)),
        ram_mb=max(host.MIN_VM_RAM_MB, ram_mb or info.default_vm_ram_mb),
        disk_gb=disk_gb, username=tpl.username, apps=list(tpl.apps),
        keyboard=tpl.keyboard or keyboard, timezone=tpl.timezone or "Europe/Berlin",
        desktop=tpl.desktop, extra_desktops=list(tpl.extra_desktops),
        provisioned=False, first_boot_pending=False, template=tpl.name,
    )
    path.mkdir(parents=True)
    try:
        if linked:
            report("disk", 0.0, f"Verknüpfe mit Vorlage „{tpl.name}“ …")
            qemu.create_overlay(qemu_img, tpl.disk, path / "disk.qcow2", disk_gb, relative=True)
        else:
            def copy(frac: float) -> None:
                report("disk", frac, f"Kopiere Vorlage „{tpl.name}“ … {frac * 100:.0f} %")

            report("disk", 0.0, f"Kopiere Vorlage „{tpl.name}“ …")
            qemu.convert_disk(qemu_img, tpl.disk, path / "disk.qcow2", progress=copy)
            if disk_gb * storage.GB > qemu.virtual_size(qemu_img, path / "disk.qcow2"):
                qemu.resize_disk(qemu_img, path / "disk.qcow2", disk_gb)
        report("seed", 0.0, "Schreibe Rechnername und Passwort …")
        cloudinit.write_clone_seed_iso(path / "seed.iso", hostname=name.lower().replace("_", "-"),
                                       username=tpl.username, password=password,
                                       instance_id=f"bonys-{uuid.uuid4()}")
        (path / "vm.json").write_text(json.dumps(asdict(cfg), indent=2), "utf-8")
    except Exception:
        shutil.rmtree(path, ignore_errors=True)
        raise
    if library != storage.default_library():
        storage.add_location(library)
    storage.remember(name, path)
    storage.invalidate_cache()
    machine = VM(path)
    machine.ensure_remote_ports()
    kind = "verknüpft" if linked else "unabhängige Kopie"
    report("done", 1.0, f"Agent-PC aus Vorlage „{tpl.name}“ angelegt ({kind}, {time.monotonic() - t0:.0f} s) "
                        f"in {path}")
    return machine
