# SPDX-License-Identifier: GPL-3.0-or-later
"""Warum ist QEMU während der Einrichtung beendet worden? – verständlich erklärt.

Ausgewertet werden das Protokoll von QEMU (qemu.log), das Kernel-Protokoll des Hosts
(Speichermangel), die Startzeit des Hosts (Neustart) und eigene Markierungen in runtime.json.
``explain_abort`` ist eine reine Funktion und lässt sich so ohne echtes System testen.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass

from bonys_agents.procutil import clean_env, no_window_flags

_SIGNAL = re.compile(r"terminating on signal (\d+)(?: from pid (\d+)(?: \(([^)]*)\))?)?")
_SIGNAL_NAMES = {1: "SIGHUP", 2: "SIGINT", 9: "SIGKILL", 15: "SIGTERM"}
_OOM = re.compile(r"Out of memory: Kill(?:ed)? process (\d+) \(([^)]*)\)|oom-kill:.*task=([^,\s]+),pid=(\d+)")


@dataclass
class AbortInfo:
    reason: str
    detail: str = ""

    def text(self) -> str:
        return f"{self.reason}\n{self.detail}" if self.detail else self.reason


def oom_killed(kernel_log: str, pid: int | None) -> bool:
    """Steht im Kernel-Protokoll, dass QEMU wegen Speichermangels beendet wurde?"""
    for m in _OOM.finditer(kernel_log):
        killed_pid = m.group(1) or m.group(4)
        name = m.group(2) or m.group(3) or ""
        if (pid and killed_pid and int(killed_pid) == pid) or "qemu" in name:
            return True
    # systemd-oomd beendet ganze Programmgruppen (z. B. die App samt QEMU) bei Speicherdruck
    return any("systemd-oomd" in line and "Killed" in line and "memory pressure" in line
               for line in kernel_log.splitlines())


def explain_abort(
    qemu_log: str = "",
    kernel_log: str = "",
    pid: int | None = None,
    started: float | None = None,
    boot_time: float | None = None,
    powered_off: bool = False,
    stop_requested: bool = False,
    console: str = "",
) -> AbortInfo:
    """Wahrscheinlichste Ursache, warum der Agent-PC vor dem Ende der Einrichtung aus war."""
    if powered_off:
        return AbortInfo("Der Agent-PC wurde hart ausgeschaltet („Sofort ausschalten“ bzw. „stop --force“).")
    if started and boot_time and started < boot_time:
        return AbortInfo("Der Rechner wurde neu gestartet, während die Einrichtung lief.",
                         "Agent-PCs laufen nicht über einen Neustart des Rechners hinweg weiter.")
    if oom_killed(kernel_log, pid):
        return AbortInfo(
            "QEMU wurde beendet – vermutlich zu wenig Arbeitsspeicher.",
            "Das System hat QEMU wegen Speichermangels geschlossen. Andere Programme schließen oder "
            "dem Agent-PC weniger Arbeitsspeicher geben.",
        )
    signals = list(_SIGNAL.finditer(qemu_log))
    if signals:
        sig = signals[-1]
        num = int(sig.group(1))
        who = f" von „{sig.group(3)}“" if sig.group(3) else (f" von Prozess {sig.group(2)}" if sig.group(2) else "")
        name = _SIGNAL_NAMES.get(num, f"Signal {num}")
        return AbortInfo(f"QEMU wurde von außen beendet ({name}{who}).",
                         "Zum Beispiel beim Abmelden, durch einen Task-Manager oder ein anderes Programm.")
    if stop_requested:
        return AbortInfo("Der Agent-PC wurde während der Einrichtung heruntergefahren.")
    if re.search(r"reboot: Power down|Power-Off|System halted", console):
        return AbortInfo("Der Agent-PC hat sich selbst ausgeschaltet, bevor die Einrichtung fertig war.")
    errors = [line.strip() for line in qemu_log.splitlines() if line.strip()]
    if errors:
        return AbortInfo("QEMU wurde mit einer Fehlermeldung beendet.", "\n".join(errors[-3:]))
    return AbortInfo("QEMU wurde unerwartet beendet – die Ursache ist nicht bekannt.",
                     "Möglich sind z. B. Speichermangel oder ein Absturz. „Protokolle öffnen“ zeigt Details.")


def kernel_log(since: float | None) -> str:
    """Kernel-Meldungen (und systemd-oomd) seit ``since`` – leer, wenn nicht lesbar."""
    journalctl = shutil.which("journalctl")
    if not journalctl:
        return ""
    since_arg = [f"--since=@{int(since)}"] if since else ["-b"]
    out = []
    for extra, prefix in ((["-k"], ""), (["-u", "systemd-oomd"], "systemd-oomd: ")):
        try:
            r = subprocess.run([journalctl, *extra, *since_arg, "-q", "--no-pager", "-o", "cat"],
                               capture_output=True, text=True, timeout=15, errors="replace",
                               creationflags=no_window_flags(), env=clean_env())
        except (OSError, subprocess.SubprocessError):
            continue
        out += [prefix + line for line in r.stdout.splitlines()]
    return "\n".join(out)
