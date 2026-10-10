# SPDX-License-Identifier: GPL-3.0-or-later
"""Vorlagen: fertig eingerichtete Agent-PCs, aus denen neue in Sekunden entstehen.

Eine Vorlage liegt neben den Agent-PCs eines Speicherorts::

    <Speicherort>/_templates/<name>/disk.qcow2     komprimierte, verallgemeinerte Festplatte
    <Speicherort>/_templates/<name>/template.json  Name, Beschreibung, Apps …

Erstellen, ohne das Original anzufassen: Über die (ausgeschaltete) Festplatte des Agent-PCs kommt
eine Überlagerung (qcow2 mit Backing-File). Nur diese Kopie startet – mit abgeschottetem Netz –,
wird im Gast verallgemeinert und heruntergefahren. Daraus entsteht per ``qemu-img convert -c`` die
Vorlage, danach wird die Überlagerung gelöscht. Das Original wird dabei nur gelesen.

Verknüpfte Agent-PCs („Schnell“) bauen per Backing-File (relativer Pfad) auf der Vorlage auf;
unabhängige sind eine vollständige Kopie.
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import tarfile
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path

from bonys_agents import cloudinit, host, qemu, storage, vm

TEMPLATES_DIRNAME = "_templates"
FILE_SUFFIX = ".bonys-template"
FORMAT = 1
NAME_RE = vm.NAME_RE
EXPORT_WARNING = ("Prüfe vor der Weitergabe, dass keine persönlichen Daten enthalten sind – "
                  "vor allem, wenn die Vorlage mit „Persönliche Daten behalten“ erstellt wurde.")

GUEST_AGENT_WAIT = 300      # Sekunden, bis der Gast-Agent der Arbeitskopie antworten muss
GENERALIZE_TIMEOUT = 3600   # Nullen des freien Platzes kann bei großen Platten dauern

# Anteile am Gesamtfortschritt beim Erstellen
_PHASES = {"overlay": (0.0, 0.02), "boot": (0.02, 0.15), "generalize": (0.15, 0.3), "shutdown": (0.3, 0.35),
           "convert": (0.35, 0.95), "check": (0.95, 1.0)}

ProgressFn = Callable[[str, float, str], None]


@dataclass
class Template:
    path: Path
    name: str
    description: str = ""
    created: str = ""
    debian: str = ""
    arch: str = ""
    apps: list[str] = field(default_factory=list)
    size: int = 0                 # Bytes der komprimierten Festplatte
    disk_gb: int = vm.DEFAULT_DISK_GB
    source: str = ""              # ursprünglicher Agent-PC
    username: str = "agent"
    keyboard: str = "de"
    timezone: str = "Europe/Berlin"
    personal_data_removed: bool = True
    desktop: str = "cinnamon"
    extra_desktops: list[str] = field(default_factory=list)
    format: int = FORMAT

    @property
    def disk(self) -> Path:
        return self.path / "disk.qcow2"

    @property
    def library(self) -> Path:
        """Speicherort, zu dem die Vorlage gehört."""
        return self.path.parent.parent

    def to_json(self) -> dict:
        d = asdict(self)
        d.pop("path")
        return d

    def save(self) -> None:
        tmp = self.path / "template.json.tmp"
        tmp.write_text(json.dumps(self.to_json(), indent=2, ensure_ascii=False), "utf-8")
        os.replace(tmp, self.path / "template.json")

    @classmethod
    def load(cls, path: Path) -> Template:
        data = json.loads((path / "template.json").read_text("utf-8"))
        known = {f.name for f in fields(cls)} - {"path"}
        return cls(path=path, **{k: v for k, v in data.items() if k in known})

    def created_local(self) -> str:
        try:
            return datetime.fromisoformat(self.created).astimezone().strftime("%d.%m.%Y %H:%M")
        except ValueError:
            return self.created

    def linked_vms(self) -> list[vm.VM]:
        """Agent-PCs, deren Festplatte auf dieser Vorlage aufbaut (nur die gerade erreichbaren)."""
        out = []
        for m in vm.list_vms():
            b = m.backing_file()
            try:
                if b is not None and b.exists() and os.path.samefile(b, self.disk):
                    out.append(m)
            except OSError:
                continue
        return out


def check_name(name: str) -> None:
    if not NAME_RE.match(name):
        raise ValueError("Name der Vorlage: 1–40 Zeichen, nur Buchstaben, Ziffern, - und _")


def templates_dir(library: Path) -> Path:
    return Path(library) / TEMPLATES_DIRNAME


def list_templates() -> list[Template]:
    """Alle Vorlagen auf allen erreichbaren Speicherorten (auch Wechsellaufwerken)."""
    found: dict[str, Template] = {}
    for lib in storage.libraries():
        try:
            dirs = sorted(templates_dir(lib).iterdir())
        except OSError:
            continue
        for d in dirs:
            if d.name.startswith(".") or not (d / "template.json").is_file():
                continue
            try:
                t = Template.load(d)
            except (OSError, ValueError, TypeError):
                continue
            found.setdefault(t.name, t)
    return sorted(found.values(), key=lambda t: t.name.lower())


def get(name: str) -> Template:
    for t in list_templates():
        if t.name == name:
            return t
    raise KeyError(f"Vorlage '{name}' gibt es nicht (oder ihr Laufwerk ist nicht eingesteckt)")


def same_drive(t: Template, library: Path) -> bool:
    """Liegt ``library`` auf demselben Laufwerk wie die Vorlage? (Voraussetzung für „verknüpft“)"""
    try:
        return os.stat(t.disk).st_dev == os.stat(storage._existing_parent(Path(library))).st_dev
    except OSError:
        return False


def _exists(name: str) -> bool:
    return any(t.name == name for t in list_templates())


def _report(progress: ProgressFn | None, phase: str, frac: float, msg: str) -> None:
    if progress:
        lo, hi = _PHASES.get(phase, (0.0, 1.0))
        progress(phase, lo + (hi - lo) * min(max(frac, 0.0), 1.0), msg)


# ---------------------------------------------------------------- Arbeitskopie
class _WorkVM(vm.VM):
    """Überlagerung eines Agent-PCs zum Verallgemeinern: ohne Internet, ohne Remmina-Profile."""

    restrict_net = True
    zero_unmap = True

    def sync_remmina(self) -> None:
        pass


def _start_work_copy(machine: vm.VM, work: Path) -> _WorkVM:
    """Überlagerung der Festplatte anlegen und unsichtbar starten (das Original bleibt unverändert)."""
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    qemu.create_overlay(qemu.find_binary("qemu-img", host.detect().os), machine.disk, work / "disk.qcow2")
    cfg = asdict(machine.config)
    cfg.update(remote_permanent=False, display="qemu", first_boot_pending=False, provisioned=True)
    (work / "vm.json").write_text(json.dumps(cfg, indent=2), "utf-8")
    copy = _WorkVM(work)
    copy.start(headless=True)
    return copy


def _wait_guest_agent(copy: _WorkVM, progress: ProgressFn | None, timeout: float = GUEST_AGENT_WAIT) -> bool:
    """Bis der Gast-Agent antwortet. False = kein Gast-Agent (dann SSH)."""
    deadline = time.time() + timeout
    t0 = time.time()
    while time.time() < deadline:
        if not copy.is_running():
            err = copy.qemu_log.read_text("utf-8", errors="replace")[-1500:] if copy.qemu_log.exists() else ""
            raise RuntimeError("Die Arbeitskopie hat sich beim Starten beendet.\n" + err)
        try:
            with qemu.GuestAgent(copy.runtime().get("qga_port") or 0, timeout=3) as ga:
                ga.execute("guest-ping")
                return True
        except (qemu.GuestAgentError, RuntimeError):
            pass
        _report(progress, "boot", (time.time() - t0) / 60, "Arbeitskopie startet (ohne Netz) …")
        time.sleep(2)
    return False


def _run_in_copy(copy: _WorkVM, script: str, password: str | None, has_agent: bool, timeout: float) -> str:
    if has_agent:
        with qemu.GuestAgent(copy.runtime()["qga_port"], timeout=10) as ga:
            rc, out = ga.run(script, timeout=timeout, shell="/bin/bash")
        if rc != 0:
            raise RuntimeError(f"Verallgemeinern fehlgeschlagen (Code {rc}): {out.strip()[-600:]}")
        return out
    if not password:
        raise vm.NeedsPassword("Der Gast-Agent antwortet nicht – für SSH wird das Passwort des Agent-PCs gebraucht.")
    lines: list[str] = []
    rc = copy._ssh(vm.SSH_SUDO_SCRIPT, script, password, lines.append)
    if rc == 255:
        raise RuntimeError("SSH-Verbindung oder Anmeldung fehlgeschlagen – stimmt das Passwort?")
    if rc != 0:
        raise RuntimeError(f"Verallgemeinern fehlgeschlagen (Code {rc}): {chr(10).join(lines)[-600:]}")
    return "\n".join(lines)


class _SourceLock:
    """Sperrt den Agent-PC (Start, Löschen, Verschieben), solange seine Festplatte als Grundlage dient."""

    def __init__(self, machine: vm.VM):
        self.file = machine.path / vm.TEMPLATE_LOCK

    def __enter__(self):
        self.file.write_text(str(os.getpid()))
        return self

    def __exit__(self, *exc):
        self.file.unlink(missing_ok=True)


def _source_vm(vm_name: str) -> vm.VM:
    machine = vm.get(vm_name)
    if machine.template_lock_pid() is not None:
        raise RuntimeError(f"Aus „{machine.name}“ wird schon eine Vorlage erstellt.")
    if machine.config.first_boot_pending or not machine.progress().ready:
        raise RuntimeError(f"„{machine.name}“ ist noch nicht fertig eingerichtet – nur fertige Agent-PCs "
                           "können zur Vorlage werden.")
    if machine.is_running():
        raise RuntimeError(f"Bitte „{machine.name}“ zuerst herunterfahren – die Vorlage entsteht aus einer Kopie "
                           "der ausgeschalteten Festplatte, damit am Original nichts verändert wird.")
    machine._check_usable()
    return machine


def preview(vm_name: str, remove_personal: bool = True, password: str | None = None,
            progress: ProgressFn | None = None) -> str:
    """Probelauf: Arbeitskopie starten und auflisten, was gelöscht würde – ohne etwas zu löschen."""
    machine = _source_vm(vm_name)
    work = templates_dir(machine.location) / f".{machine.name}.probelauf"
    with _SourceLock(machine):
        copy = None
        try:
            _report(progress, "overlay", 0, "Lege Arbeitskopie an …")
            copy = _start_work_copy(machine, work)
            has_agent = _wait_guest_agent(copy, progress)
            _report(progress, "generalize", 0, "Sehe im Agent-PC nach …")
            script = cloudinit.generalize_script(machine.config.username, remove_personal, dry_run=True)
            out = _run_in_copy(copy, script, password, has_agent, timeout=300)
        finally:
            if copy is not None:
                copy.power_off()
            shutil.rmtree(work, ignore_errors=True)
    _report(progress, "check", 1, "Probelauf fertig.")
    return "\n".join(line for line in out.splitlines() if not line.startswith("BONYS-DEBIAN"))


def create(vm_name: str, name: str, description: str = "", remove_personal: bool = True,
           location: Path | None = None, password: str | None = None,
           progress: ProgressFn | None = None, log: Callable[[str], None] | None = None) -> Template:
    """Vorlage aus einem fertig eingerichteten, ausgeschalteten Agent-PC erstellen."""
    check_name(name)
    if _exists(name):
        raise FileExistsError(f"Vorlage '{name}' gibt es schon")
    machine = _source_vm(vm_name)
    library = Path(location) if location else machine.location
    base = templates_dir(library)
    target = base / name
    if target.exists():
        raise FileExistsError(f"Ordner {target} existiert bereits")
    base.mkdir(parents=True, exist_ok=True)
    used = machine.disk.stat().st_size
    if shutil.disk_usage(base).free < used + 2 * storage.GB:
        raise RuntimeError(f"Zu wenig Platz in {library}: gebraucht werden etwa {used / storage.GB + 2:.0f} GB "
                           "(Arbeitskopie und Vorlage).")
    qemu_img = qemu.find_binary("qemu-img", host.detect().os)
    work = base / f".{name}.arbeitskopie"
    part = base / f".{name}.teil"
    emit = log or (lambda line: None)
    with _SourceLock(machine):
        copy = None
        try:
            _report(progress, "overlay", 0, "Lege Arbeitskopie an (das Original bleibt unverändert) …")
            copy = _start_work_copy(machine, work)
            has_agent = _wait_guest_agent(copy, progress)
            _report(progress, "generalize", 0, "Verallgemeinere: persönliche Daten, Schlüssel, Protokolle, "
                                               "freien Platz nullen …" if remove_personal else
                    "Verallgemeinere: Schlüssel, Protokolle, freien Platz nullen …")
            script = cloudinit.generalize_script(machine.config.username, remove_personal)
            out = _run_in_copy(copy, script, password, has_agent, timeout=GENERALIZE_TIMEOUT)
            for line in out.splitlines():
                emit(line)
            if "BONYS-GENERALIZED" not in out:
                raise RuntimeError("Verallgemeinern nicht vollständig – siehe Ausgabe.")
            debian = next((ln.split(" ", 1)[1].strip() for ln in out.splitlines()
                           if ln.startswith("BONYS-DEBIAN ")), "")
            _report(progress, "shutdown", 0, "Fahre Arbeitskopie herunter …")
            copy.stop(timeout=120)
            copy = None

            shutil.rmtree(part, ignore_errors=True)
            part.mkdir()

            def conv(frac: float) -> None:
                _report(progress, "convert", frac, f"Komprimiere Festplatte zur Vorlage … {frac * 100:.0f} %")

            conv(0)
            qemu.convert_disk(qemu_img, work / "disk.qcow2", part / "disk.qcow2", compress=True, progress=conv)
            _report(progress, "check", 0, "Prüfe die Vorlage (qemu-img check) …")
            qemu.check_disk(qemu_img, part / "disk.qcow2")
            tpl = Template(
                path=part, name=name, description=description,
                created=datetime.now(timezone.utc).isoformat(timespec="seconds"), debian=debian,
                arch=machine.config.arch, apps=list(machine.config.apps),
                size=(part / "disk.qcow2").stat().st_size, disk_gb=machine.config.disk_gb,
                source=machine.name, username=machine.config.username, keyboard=machine.config.keyboard,
                timezone=machine.config.timezone, personal_data_removed=remove_personal,
                desktop=machine.config.desktop, extra_desktops=list(machine.config.extra_desktops),
            )
            tpl.save()
            os.replace(part, target)
            tpl.path = target
        except BaseException:
            shutil.rmtree(part, ignore_errors=True)
            raise
        finally:
            if copy is not None:
                copy.power_off()
            shutil.rmtree(work, ignore_errors=True)
    storage.add_location(library)
    _report(progress, "check", 1, f"Vorlage „{name}“ fertig ({tpl.size / storage.GB:.1f} GB).")
    return tpl


# ---------------------------------------------------------------- Verwalten
def set_description(name: str, description: str) -> Template:
    t = get(name)
    t.description = description
    t.save()
    return t


def rename(name: str, new_name: str) -> Template:
    """Umbenennen. Verknüpfte Agent-PCs (müssen ausgeschaltet sein) zeigen danach auf den neuen Ort."""
    check_name(new_name)
    t = get(name)
    if new_name == name:
        return t
    if _exists(new_name):
        raise FileExistsError(f"Vorlage '{new_name}' gibt es schon")
    linked = t.linked_vms()
    running = [m.name for m in linked if m.is_running()]
    if running:
        raise RuntimeError("Verknüpfte Agent-PCs laufen gerade: " + ", ".join(running) + " – bitte herunterfahren.")
    dest = t.path.parent / new_name
    os.replace(t.path, dest)
    t.path = dest
    t.name = new_name
    t.save()
    qemu_img = qemu.find_binary("qemu-img", host.detect().os)
    for m in linked:
        qemu.rebase(qemu_img, m.disk, t.disk, unsafe=True)
        m.config.template = new_name
        m.save()
    return t


def delete(name: str) -> None:
    """Löschen – gesperrt, solange verknüpfte Agent-PCs darauf aufbauen."""
    t = get(name)
    linked = t.linked_vms()
    if linked:
        raise LinkedVMsError(t, linked)
    shutil.rmtree(t.path)


class LinkedVMsError(RuntimeError):
    def __init__(self, template: Template, machines: list[vm.VM]):
        self.template = template
        self.machines = machines
        names = ", ".join(m.name for m in machines)
        super().__init__(f"Die Vorlage „{template.name}“ wird noch von verknüpften Agent-PCs gebraucht: {names}. "
                         "Erst diese zu unabhängigen Kopien machen (oder löschen).")


# ---------------------------------------------------------------- Export / Import
class _Reader:
    """Datei-Wrapper, der beim Lesen den Fortschritt meldet."""

    def __init__(self, f, cb: Callable[[int], None]):
        self.f, self.cb = f, cb

    def read(self, n: int = -1) -> bytes:
        data = self.f.read(n)
        self.cb(len(data))
        return data


def export(name: str, file: Path, progress: ProgressFn | None = None) -> Path:
    """Vorlage als eine Datei (.bonys-template = tar mit template.json und disk.qcow2)."""
    t = get(name)
    file = Path(file)
    if file.suffix != FILE_SUFFIX:
        file = file.with_name(file.name + FILE_SUFFIX)
    total = t.disk.stat().st_size or 1
    done = 0

    def tick(n: int) -> None:
        nonlocal done
        done += n
        if progress:
            progress("export", done / total, f"Exportiere … {done // host.MB} / {total // host.MB} MB")

    tmp = file.with_name(file.name + ".teil")
    try:
        with tarfile.open(tmp, "w", format=tarfile.PAX_FORMAT) as tar:
            data = json.dumps(t.to_json(), indent=2, ensure_ascii=False).encode("utf-8")
            info = tarfile.TarInfo("template.json")
            info.size, info.mtime, info.mode = len(data), int(time.time()), 0o644
            tar.addfile(info, io.BytesIO(data))
            info = tar.gettarinfo(str(t.disk), arcname="disk.qcow2")
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            with t.disk.open("rb") as f:
                tar.addfile(info, _Reader(f, tick))
        os.replace(tmp, file)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return file


def read_export_info(file: Path) -> Template:
    """template.json aus einer .bonys-template-Datei lesen (ohne zu entpacken)."""
    with tarfile.open(file, "r:") as tar:
        _check_members(tar)
        data = json.loads(tar.extractfile("template.json").read().decode("utf-8"))
    known = {f.name for f in fields(Template)} - {"path"}
    return Template(path=Path(file), **{k: v for k, v in data.items() if k in known})


def _check_members(tar: tarfile.TarFile) -> dict[str, tarfile.TarInfo]:
    members = {m.name: m for m in tar.getmembers()}
    if set(members) != {"template.json", "disk.qcow2"} or not all(m.isfile() for m in members.values()):
        raise ValueError("Keine gültige Vorlagen-Datei (erwartet: template.json und disk.qcow2).")
    return members


def import_file(file: Path, location: Path | None = None, name: str | None = None,
                progress: ProgressFn | None = None) -> Template:
    """.bonys-template-Datei als Vorlage an einem Speicherort ablegen und prüfen."""
    file = Path(file)
    info = read_export_info(file)
    name = name or info.name
    check_name(name)
    if _exists(name):
        raise FileExistsError(f"Vorlage '{name}' gibt es schon – beim Importieren einen anderen Namen wählen.")
    if info.arch and info.arch != host.detect().arch:
        raise ValueError(f"Die Vorlage ist für {info.arch}, dieser Rechner ist {host.detect().arch}.")
    library = Path(location) if location else storage.preferred_library()
    base = templates_dir(library)
    target = base / name
    if target.exists():
        raise FileExistsError(f"Ordner {target} existiert bereits")
    base.mkdir(parents=True, exist_ok=True)
    with tarfile.open(file, "r:") as tar:
        disk = _check_members(tar)["disk.qcow2"]
        if shutil.disk_usage(base).free < disk.size + storage.GB:
            raise RuntimeError(f"Zu wenig Platz in {library} ({disk.size / storage.GB:.1f} GB nötig).")
        part = base / f".{name}.import"
        shutil.rmtree(part, ignore_errors=True)
        part.mkdir()
        try:
            src = tar.extractfile(disk)
            done = 0
            with (part / "disk.qcow2").open("wb") as out:
                while chunk := src.read(8 * 1024 * 1024):
                    out.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress("import", done / max(disk.size, 1),
                                 f"Importiere … {done // host.MB} / {disk.size // host.MB} MB")
            if progress:
                progress("import", 1.0, "Prüfe die Vorlage (qemu-img check) …")
            qemu.check_disk(qemu.find_binary("qemu-img", host.detect().os), part / "disk.qcow2")
            if qemu.backing_file(part / "disk.qcow2") is not None:
                raise ValueError("Die Festplatte in der Vorlagen-Datei ist nicht eigenständig.")
            info.path, info.name = part, name
            info.size = (part / "disk.qcow2").stat().st_size
            info.save()
            os.replace(part, target)
            info.path = target
        except BaseException:
            shutil.rmtree(part, ignore_errors=True)
            raise
    storage.add_location(library)
    return info


def describe(t: Template) -> str:
    """Eine Zeile für Listen: Datum, Debian, Apps, Größe."""
    from bonys_agents import apps as apps_mod

    parts = [t.created_local()]
    from bonys_agents import desktops

    parts.append(desktops.name(t.desktop))
    if t.debian:
        parts.append(f"Debian {t.debian}")
    parts.append(f"{t.size / storage.GB:.1f} GB")
    if t.apps:
        parts.append(", ".join(apps_mod.names(t.apps)))
    return " · ".join(parts)


_SAFE = re.compile(r"[^A-Za-z0-9_-]+")


def suggest_name(vm_name: str) -> str:
    base = _SAFE.sub("-", f"vorlage-{vm_name}")[:40].strip("-") or "vorlage"
    name, n = base, 2
    existing = {t.name for t in list_templates()}
    while name in existing:
        name = f"{base[:36]}-{n}"
        n += 1
    return name
