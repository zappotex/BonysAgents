# SPDX-License-Identifier: GPL-3.0-or-later
"""Kommandozeile: bonys-agents <befehl>."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
import time
from pathlib import Path

from bonys_agents import (
    APP_NAME, __version__, apps, cloudinit, deps, desktops, distros, edition, host, mission_control, n8n, procutil,
    qemu, remote, screen, netz, storage, vm, vpnlink,
)
from bonys_agents import i18n
from bonys_agents import progress as pct
from bonys_agents.i18n import tr


REBOOT_REQUIRED = 3010  # wie bei Windows-Installern üblich


def _disk_gb(text: str) -> int:
    """argparse-Typ für Festplattengrößen: 32 bis 1024 GB."""
    try:
        gb = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(tr("'{inhalt}' ist keine Zahl (Größe in GB, z. B. 64)", inhalt=text)) from None
    try:
        vm.check_disk_gb(gb)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from None
    return gb


def _setup_line(machine: vm.VM, p: vm.Progress) -> str:
    """„42 % · Schritt 2/5 Cinnamon … · noch ca. 12 Min.“"""
    parts = [f"{p.percent:.0f} %"]
    if p.total:
        parts.append(tr("Schritt {schritt}/{gesamt} {titel}", schritt=p.step, gesamt=p.total,
                        titel=cloudinit.schritt_titel(p.title)))
    if p.resumed:
        parts.append(tr("wird nach dem Neustart fortgesetzt"))
    elif p.resume_step:
        parts.append(f"fortgesetzt ab Schritt {p.resume_step}")
    eta = pct.format_eta(machine.eta_seconds(p.percent))
    if eta:
        parts.append(eta)
    return " · ".join(parts)


def _bar(frac: float, width: int = 30) -> str:
    n = int(frac * width)
    return "[" + "#" * n + "-" * (width - n) + f"] {frac * 100:5.1f}%"


def cmd_doctor(args) -> int:
    info = host.detect()
    print(tr("{NAME} {version__} (Edition: {LABEL})", NAME=edition.NAME, version__=__version__, LABEL=edition.LABEL))
    print(tr("System:        {os} / {arch}", os=info.os, arch=info.arch))
    print(tr("CPU-Kerne:     {cpus}", cpus=info.cpus))
    print(tr("RAM:           {ram_mb} MB (für VMs nutzbar: {max_vm_ram_mb} MB)", ram_mb=info.ram_mb,
             max_vm_ram_mb=info.max_vm_ram_mb))
    accel_note = "" if info.accel_is_fast else "  ⚠ keine Hardware-Beschleunigung – VMs laufen sehr langsam"
    print(tr("Beschleuniger: {accel}{accel_note}", accel=info.accel, accel_note=accel_note))
    if info.os == "macos":
        print(tr("Mac:           {wert}", wert=host.macos_chip_name(info.arch)))
        if host.macos_rosetta():
            print(tr("App-Version:   Intel (läuft per Rosetta) – besser die Version für Apple-Chip laden"))
        brew = deps.find_brew(info.arch)
        print(tr("Homebrew:      {wert}",
                 wert='ja – ' + str(brew) if brew else 'nein (nötig für QEMU – siehe https://brew.sh)'))
        print(tr("HVF:           {wert}", wert='ja' if info.accel == 'hvf' else 'nein'))
    ok = True
    for name in (qemu.ARCH_BINARY[info.arch], "qemu-img"):
        try:
            print(f"{name}: {qemu.find_binary(name, info.os)}")
        except qemu.QemuNotFound as e:
            ok = False
            print(tr("{name}: FEHLT\n{e}", name=name, e=e))
    if ok and info.arch == "aarch64":
        try:
            fw = qemu.find_aarch64_firmware(qemu.find_binary(qemu.ARCH_BINARY[info.arch], info.os))
            print(tr("UEFI-Firmware: {fw}", fw=fw))
        except qemu.QemuNotFound as e:
            ok = False
            print(e)
    print(tr("Datenordner:   {wert}", wert=vm.data_dir()))
    old = storage.old_user_install()
    if old:
        print(tr("⚠ Ältere Installation gefunden: {old}\n  Startmenü und Terminal starten womöglich diese alte "
                 "Version statt der aktuellen.\n  Entfernen mit: rm -rf {old} ~/.local/bin/bonys-agents "
                 "~/.local/share/applications/bonys-agents.desktop", old=old))
    report = deps.check(info)
    for issue in report.issues:
        print(f"⚠ {issue.text}")
    if report.ok:
        print(tr("Alles bereit."))
    elif report.fixable:
        print(tr("→ Automatisch beheben mit: bonys-agents setup"))
    return 0 if report.ok else 1


def cmd_selftest(args) -> int:
    """QEMU auf demselben Weg wie die App starten und das Ergebnis klar melden."""
    from bonys_agents import selftest

    print(tr("{APP_NAME} {version__} – Selbsttest", APP_NAME=APP_NAME, version__=__version__))

    def show(c) -> None:
        print(f"  {'OK    ' if c.ok else 'FEHLER'}  {c.name}")
        for line in (c.detail or "").splitlines():
            print(f"          {line}")

    results = selftest.run(log=show, include_qt=not args.no_qt, boot=args.boot)
    ok = selftest.passed(results)
    print(tr("Ergebnis: OK – QEMU startet.") if ok else tr("Ergebnis: FEHLER – siehe oben."))
    return 0 if ok else 1


def cmd_setup(args) -> int:
    """Installiert QEMU & Co. automatisch."""
    info = host.detect()
    report = deps.check(info)
    if report.ok:
        print(tr("Alles ist bereits installiert und bereit."))
        return 0
    print(tr("Folgendes wird eingerichtet:"))
    for issue in report.fixable:
        print(f"  • {issue.text}")
    for issue in report.issues:
        if not issue.fixable:
            print(tr("  ⚠ {inhalt} (muss von Hand behoben werden)", inhalt=issue.text))
    if report.fixable and not args.yes:
        if input("Jetzt automatisch einrichten? (ja/nein) ").strip().lower() not in ("j", "ja", "y", "yes"):
            print(tr("Abgebrochen."))
            return 1
    if any(i.key == "homebrew" for i in report.issues):
        if not _install_homebrew(info, args.yes):
            return 1
        report = deps.check(info)
    result = deps.install(info, report, log=print)
    print(result.message)
    if result.success and result.reboot_required:
        return REBOOT_REQUIRED
    return 0 if result.success else 1


def _install_homebrew(info: host.HostInfo, assume_yes: bool) -> bool:
    """macOS: Homebrew fehlt – erklären, fragen und den offiziellen Installer hier im Terminal starten."""
    print()
    print(deps.homebrew_explanation(in_terminal=True))
    print()
    if not _yes("Homebrew jetzt installieren?", assume_yes):
        print(tr("Abgebrochen. Homebrew lässt sich auch selbst installieren: https://brew.sh – danach: brew install "
                 "qemu"))
        return False
    return deps.run_homebrew_installer_here(info.arch) == 0


def _ensure_ready(assume_yes: bool) -> bool:
    report = deps.check()
    if report.can_run and not report.fixable:
        return True
    if report.fixable:
        print(tr("Es fehlt noch etwas für die Agent-PCs:"))
        for issue in report.fixable:
            print(f"  • {issue.text}")
        if assume_yes or input("Jetzt automatisch einrichten? (ja/nein) ").strip().lower() in ("j", "ja", "y", "yes"):
            if any(i.key == "homebrew" for i in report.issues):
                if not _install_homebrew(host.detect(), assume_yes):
                    return False
                report = deps.check()
            result = deps.install(report=report, log=print)
            print(result.message)
            if result.reboot_required:
                return False
            report = deps.check()
    return report.can_run


def vpn_setup(args) -> vpnlink.VpnSetup | None:
    """--vpn-config & Co. → geprüfte Konfiguration (nur im Speicher). Ohne Datei keine Schalter."""
    if not args.vpn_config:
        if args.vpn_autoconnect or args.killswitch or args.vpn_name:
            raise ValueError(tr("--vpn-autoconnect, --killswitch und --vpn-name gehen nur zusammen mit --vpn-config."))
        return None
    setup = vpnlink.load_conf(args.vpn_config, name=args.vpn_name, autoconnect=args.vpn_autoconnect,
                              killswitch=args.killswitch)
    extra = [x for x, on in (("verbindet sich automatisch", setup.autoconnect), ("Kill-Switch an", setup.killswitch))
             if on]
    print(f"WireGuard: Tunnel „{setup.name}“" + (f" ({', '.join(extra)})" if extra else "")
          + " – die Konfiguration geht nur über das Seed-ISO in den Agent-PC.")
    if setup.killswitch and not setup.autoconnect:
        print(tr("⚠ Kill-Switch ohne automatisches Verbinden: Nach dem Start hat der Agent-PC kein Internet, bis du "
                 "verbindest (bonys-agents vpn {name} up).", name=args.name))
    return setup


def cmd_create(args) -> int:
    if args.template:
        return _create_from_template(args)
    if args.linked or args.full:
        print(tr("--linked und --full gibt es nur zusammen mit --template."), file=sys.stderr)
        return 2
    distro = distros.get(args.distro)
    # Ohne --desktop: der Standard des Grundsystems (Kali: Xfce)
    desk = desktops.get(args.desktop or (distro.desktops or (desktops.DEFAULT,))[0])
    distros.check(distro.id, host.detect().arch, desk.id)
    # Tippfehler melden, bevor nach dem Passwort gefragt wird
    app_ids = app_selection(args.apps, args.agents, distro.id)
    vpn = vpn_setup(args)
    bony_netz = _bony_netz(args)
    _warn_ram(desk.id, args.ram)
    _warn_mission_control(app_ids, desk.id, args.ram, args.disk or vm.DEFAULT_DISK_GB, distro.id)
    if not _ensure_ready(args.yes):
        print(tr("Agent-PC kann noch nicht erstellt werden – siehe oben."))
        return 1
    target = Path(args.location) if args.location else storage.preferred_library()
    chk = storage.check_location(target, args.disk or vm.DEFAULT_DISK_GB)
    for w in chk.warnings:
        print(f"⚠ {w}")
    if not chk.ok:
        print(tr("Speicherort nicht geeignet: {wert}", wert=" ".join(chk.errors)))
        return 1
    print(tr("Speicherort: {target}", target=target))
    password = args.password or _ask_password()

    last_phase = [""]

    def progress(phase: str, frac: float, msg: str) -> None:
        if phase == "download":
            print(f"\r{_bar(frac)} {msg[-40:]:40}", end="", flush=True)
        else:
            if last_phase[0] == "download":
                print()
            print(msg)
        last_phase[0] = phase

    machine = vm.create(
        args.name, password,
        cpus=args.cpus, ram_mb=args.ram, disk_gb=args.disk or vm.DEFAULT_DISK_GB, username=args.user,
        app_ids=app_ids,
        keyboard=args.keyboard, timezone_name=args.timezone, progress=progress,
        location=Path(args.location) if args.location else None, desktop=desk.id, vpn=vpn,
        bony_netz=bony_netz, distro=distro.id, sprache=args.sprache,
    )
    _print_hints(machine)
    c = machine.config
    print(tr("\nAgent-PC '{name}': {wert}, {wert2}, {cpus} CPUs, {ram_mb} MB RAM, {disk_gb} GB, Apps: {wert3}",
             name=c.name, wert=distros.name(c.distro), wert2=desktops.name(c.desktop), cpus=c.cpus, ram_mb=c.ram_mb,
             disk_gb=c.disk_gb, wert3=', '.join(c.apps)))
    if args.no_start:
        print(tr("Starten mit: bonys-agents start {name}", name=c.name))
        return 0
    machine.start(headless=True if args.headless else None)  # Ersteinrichtung ohne Fenster
    print(tr("Gestartet. Der Agent-PC richtet sich im Hintergrund ein – je nach Rechner 15–60 Minuten."))
    if args.wait:
        return _wait_ready(machine, headless=args.headless)
    print(tr("Fortschritt: bonys-agents status {name}", name=c.name))
    return 0


def _bony_netz(args) -> bool:
    if args.bony_netz and not netz.bereit():
        raise ValueError(tr("--bony-netz: Das Bony-Netz ist ausgeschaltet oder es ist keine Instanz angemeldet "
                            "(in der App: Menü → „Bony-Netz …“)."))
    return bool(args.bony_netz)


def _print_hints(machine: vm.VM) -> None:
    for text in machine.hinweise:
        print(f"⚠ {text}")


def _warn_ram(desktop_id: str, ram_mb: int | None) -> None:
    ram = ram_mb or host.detect().default_vm_ram_mb
    warning = desktops.ram_warning(desktop_id, ram)
    if warning:
        print(f"⚠ {warning}")


def _warn_mission_control(app_ids: list[str] | None, desktop_id: str, ram_mb: int | None, disk_gb: int,
                          distro: str = distros.DEFAULT) -> None:
    ids = app_ids if app_ids is not None else apps.default_app_ids(distro)
    if mission_control.APP_ID not in ids:
        return
    deps = apps.dependencies(ids)
    if deps:
        print(tr("Wird mitinstalliert: {wert}", wert=', '.join(apps.names(deps))))
    ram = ram_mb or host.detect().default_vm_ram_mb
    for w in mission_control.resource_warnings(ids, ram, disk_gb, desktops.get(desktop_id).min_ram_mb,
                                               mission_control.requirements()):
        print(tr("⚠ {w} (--ram/--disk)", w=w))


def _ask_password() -> str:
    password = ""
    while not password:
        password = getpass.getpass("Passwort für den Agent-PC: ")
        if password != getpass.getpass("Passwort wiederholen: "):
            print(tr("Passwörter stimmen nicht überein."))
            password = ""
    return password


def _create_from_template(args) -> int:
    from bonys_agents import templates

    if args.desktop:
        print(tr("Bei --template kommt der Desktop aus der Vorlage – --desktop weglassen."), file=sys.stderr)
        return 2
    if args.distro != distros.DEFAULT:
        print(tr("Bei --template kommt das Grundsystem aus der Vorlage – --distro weglassen."), file=sys.stderr)
        return 2
    if args.apps or args.agents:
        print(tr("Bei --template kommen die Programme aus der Vorlage – --apps/--agents weglassen "
                 "(nachrüsten mit: bonys-agents install)."), file=sys.stderr)
        return 2
    tpl = templates.get(args.template)
    vpn = vpn_setup(args)
    bony_netz = _bony_netz(args)
    if not _ensure_ready(args.yes):
        print(tr("Agent-PC kann noch nicht erstellt werden – siehe oben."))
        return 1
    target = Path(args.location) if args.location else storage.preferred_library()
    linked = True if args.linked else False if args.full else None
    print(tr("Vorlage: {name} – {wert}", name=tpl.name, wert=templates.describe(tpl)))
    _warn_ram(tpl.desktop, args.ram)
    print(tr("Speicherort: {target}", target=target))
    password = args.password or _ask_password()
    t0 = time.monotonic()

    def progress(phase: str, frac: float, msg: str) -> None:
        if phase == "disk" and 0 < frac < 1:
            print(f"\r{_bar(frac)} {msg[:40]:40}", end="", flush=True)
        else:
            print(("\n" if phase == "seed" and not linked else "") + msg)

    machine = vm.create(args.name, password, cpus=args.cpus, ram_mb=args.ram, disk_gb=args.disk,
                        location=Path(args.location) if args.location else None, progress=progress,
                        template=tpl.name, linked=linked, vpn=vpn, bony_netz=bony_netz)
    _print_hints(machine)
    c = machine.config
    kind = tr("verknüpft mit") if machine.is_linked() else tr("unabhängige Kopie von")
    print(tr("Agent-PC '{name}' ({kind} „{name2}“): {cpus} CPUs, {ram_mb} MB RAM, {disk_gb} GB, Apps: {wert}",
             name=c.name, kind=kind, name2=tpl.name, cpus=c.cpus, ram_mb=c.ram_mb, disk_gb=c.disk_gb,
             wert=', '.join(c.apps)))
    if args.no_start:
        print(tr("Starten mit: bonys-agents start {name}", name=c.name))
        return 0
    machine.start(headless=True if args.headless else None)
    print(tr("Gestartet – erster Start mit neuem Rechnernamen und Passwort."))
    if args.wait:
        rc = _wait_ready(machine, headless=args.headless)
        if rc == 0:
            print(tr("Bereit nach {wert:.0f} s (ab Beginn des Anlegens).", wert=time.monotonic() - t0))
        return rc
    return 0


def _wait_ready(machine: vm.VM, headless: bool = False, poll: float = 3) -> int:
    """Wartet auf das Ende der Einrichtung und startet den Agent-PC dann mit Fenster neu."""
    while True:
        # neu einlesen: Die Desktop-App kann den Agent-PC inzwischen mit Fenster gestartet haben
        machine = vm.VM(machine.path)
        running = machine.is_running()
        p = machine.progress()
        if p.ready and not machine.config.first_boot_pending:
            print(tr("\nFertig eingerichtet."))
            return 0
        if not running:
            if machine.finish_first_boot(headless=headless):
                print(tr("\nFertig eingerichtet – der Agent-PC startet jetzt mit Desktop."))
                return 0
            print(tr("\n{STATUS_ABORTED}: Der Agent-PC wurde beendet, bevor die Einrichtung fertig war.\nUrsache: "
                     "{wert}\nFortsetzen mit: bonys-agents start {name}", STATUS_ABORTED=vm.STATUS_ABORTED,
                     wert=machine.abort_reason().text(), name=machine.name))
            return 1
        eta = pct.format_eta(machine.eta_seconds(p.percent))
        print(f"\r{_bar(p.percent / 100)} {cloudinit.schritt_titel(p.title)[:32]:32} {eta:18}", end="", flush=True)
        time.sleep(poll)


def cmd_list(args) -> int:
    entries = vm.list_all()
    if not entries:
        print(tr("Noch keine Agent-PCs. Anlegen mit: bonys-agents create <name>"))
        return 0
    print(tr("{wert:20} {wert2:18} {wert3:11} {wert4:>4} {wert5:>8} {wert6:>6}  SPEICHERORT", wert='NAME',
             wert2='STATUS', wert3='DESKTOP', wert4='CPU', wert5='RAM', wert6='DISK'))
    for e in entries:
        if isinstance(e, vm.MissingVM):
            print(f"{e.name:20} {tr(e.status()):18} {'':11} {'':>4} {'':>8} {'':>6}  {e.path.parent}")
            continue
        c = e.config
        print(f"{c.name:20} {tr(e.status()):18} {desktops.name(c.desktop):11} {c.cpus:>4} {c.ram_mb:>6}MB "
              f"{c.disk_gb:>4}GB  {e.location}"
              + ("  " + tr("(verknüpft: {vorlage})", vorlage=c.template or e.backing_file()) if e.is_linked() else ""))
    return 0


def cmd_drives(args) -> int:
    print(tr("{wert:44} {wert2:8} {wert3:>9}  VORSCHLAG FÜR --location", wert='LAUFWERK', wert2='TYP', wert3='FREI'))
    for d in storage.drives():
        tag = " (Hauptsystem)" if d.system else (" (wechselbar)" if d.removable else "")
        note = "  ✕ FAT32 – keine Dateien > 4 GB" if d.is_fat else ""
        print(tr("{wert:44} {wert2:8} {wert3:>7.0f}GB  {library}{note}", wert=(d.label + tag)[:44],
                 wert2=d.fstype[:8], wert3=d.free / storage.GB, library=d.library, note=note))
    print(tr("\nStandard-Speicherort: {wert}", wert=storage.preferred_library()))
    return 0


def cmd_move(args) -> int:
    def progress(phase: str, frac: float, msg: str) -> None:
        print(f"\r{_bar(frac)} {msg[:40]:40}", end="", flush=True)

    moved = vm.move(args.name, Path(args.target), progress=progress)
    print(tr("\n'{name}' liegt jetzt in {path}", name=args.name, path=moved.path))
    return 0


def cmd_import(args) -> int:
    added = vm.import_path(Path(args.path))
    for m in added:
        print(tr("Hinzugefügt: {name}  ({path})", name=m.name, path=m.path))
    return 0


def cmd_default_location(args) -> int:
    if args.path:
        p = Path(args.path)
        chk = storage.check_location(p, vm.DEFAULT_DISK_GB, create=True)
        if not chk.ok:
            print(tr("Nicht geeignet: {wert}", wert=" ".join(chk.errors)))
            return 1
        storage.set_preferred_library(p)
    elif args.reset:
        storage.set_preferred_library(None)
    print(tr("Standard-Speicherort: {wert}", wert=storage.preferred_library()))
    return 0


def cmd_start(args) -> int:
    m = vm.get(args.name)
    m.start(headless=True if args.headless else None)
    if m.config.first_boot_pending:
        step = f" (zuletzt bei Schritt {m.config.setup_step})" if m.config.setup_step else ""
        print(tr("'{name}' gestartet – die Einrichtung läuft im Hintergrund weiter{step}.", name=args.name, step=step))
        if args.wait:
            return _wait_ready(m, headless=args.headless)
    else:
        print(tr("'{name}' gestartet.", name=args.name))
    return 0


def _ram_gb(text: str) -> int:
    """argparse-Typ für Arbeitsspeicher in GB (auch 5,5 oder 5.5) – Ergebnis in MB, auf 512 MB gerundet."""
    try:
        gb = float(text.replace(",", "."))
    except ValueError:
        raise argparse.ArgumentTypeError(tr("'{inhalt}' ist keine Zahl (Arbeitsspeicher in GB, z. B. 6)",
                                            inhalt=text)) from None
    return round(gb * 2) * 512


def cmd_resources(args) -> int:
    m = vm.get(args.name)
    c = m.config
    recommended = min(m.recommended_ram_mb(), host.detect().max_vm_ram_mb)
    if args.cpus is None and args.ram is None:
        print(tr("'{name}': {cpus} Kerne, {wert} RAM (empfohlen: {wert2}).", name=m.name, cpus=c.cpus,
                 wert=desktops.format_ram(c.ram_mb), wert2=desktops.format_ram(recommended)))
        return 0
    cpus = c.cpus if args.cpus is None else args.cpus
    ram_mb = c.ram_mb if args.ram is None else args.ram
    running = m.is_running()
    if running and not args.restart:
        print(tr("'{name}' läuft – zuerst herunterfahren oder mit --restart neu starten lassen.",
                 name=m.name), file=sys.stderr)
        return 1
    if running:
        print(tr("'{name}' wird heruntergefahren …", name=m.name))
        m.stop()
    m.set_resources(cpus, ram_mb)
    print(tr("'{name}': {cpus} Kerne, {wert} RAM.", name=m.name, cpus=cpus, wert=desktops.format_ram(ram_mb)))
    if ram_mb < recommended:
        print(tr("⚠ Weniger als empfohlen ({wert}) – mit Browser, Docker und Agent gleichzeitig kann es eng werden.",
                 wert=desktops.format_ram(recommended)))
    if running:
        m.start()
        print(tr("'{name}' neu gestartet.", name=m.name))
    else:
        print(tr("Gilt ab dem nächsten Start."))
    return 0


def cmd_resize(args) -> int:
    m = vm.get(args.name)
    old = m.config.disk_gb
    m.resize(args.size)
    print(tr("Festplatte von '{name}': {wert} → {wert2}.\nDer Agent-PC nutzt den neuen Platz automatisch beim "
             "nächsten Start.", name=m.name, wert=vm.format_gb(old), wert2=vm.format_gb(args.size)))
    return 0


def cmd_stop(args) -> int:
    m = vm.get(args.name)
    if not m.is_running():
        print(tr("'{name}' läuft nicht.", name=args.name))
        return 0
    if not args.force:
        print(tr("'{name}' wird heruntergefahren … (spätestens nach {STOP_TIMEOUT} s wird hart ausgeschaltet)",
                 name=args.name, STOP_TIMEOUT=vm.STOP_TIMEOUT))
    if m.stop(force=args.force) and not args.force:
        print(tr("'{name}' hat nicht reagiert und wurde hart ausgeschaltet.", name=args.name))
    else:
        print(tr("'{name}' gestoppt.", name=args.name))
    return 0


def cmd_status(args) -> int:
    m = vm.get(args.name)
    c = m.config
    print(tr("Name:    {name}\nStatus:  {wert}\nCPU/RAM: {cpus} / {ram_mb} MB\nDisk:    {disk_gb} GB", name=c.name,
             wert=tr(m.status()), cpus=c.cpus, ram_mb=c.ram_mb, disk_gb=c.disk_gb))
    print(tr("Benutzer: {benutzer}", benutzer=c.username) + f"\nDesktop: {desktops.name(c.desktop)}"
          + (f" (weitere: {', '.join(desktops.name(d) for d in c.extra_desktops)})" if c.extra_desktops else ""))
    if c.distro != distros.DEFAULT:
        print(tr("System:  {wert}", wert=distros.name(c.distro)))
    shown = [a + (f" {(c.app_info.get(a) or {}).get('version')}" if (c.app_info.get(a) or {}).get("version") else "")
             for a in c.apps]
    print(tr("Apps:    {wert}\nOrdner:  {path}", wert=', '.join(shown), path=m.path))
    if c.setup_failed:
        print(tr("Einrichtung mit Fehlern: {wert} – fehlende Programme nachinstallieren mit „bonys-agents install "
                 "{name} APP“, Einzelheiten: bonys-agents logs {name}", wert=', '.join(c.setup_failed), name=c.name))
    if m.is_linked():
        print(tr("Vorlage: {wert} (verknüpft: {wert2})", wert=c.template or '?', wert2=m.backing_file()))
    elif c.template:
        print(tr("Vorlage: {template} (unabhängige Kopie)", template=c.template))
    d = storage.drive_for(m.path)
    if d:
        print(tr("Laufwerk: {wert}", wert=d.describe()))
    if m.is_running():
        rt = m.runtime()
        p = m.progress()
        if not p.ready or c.first_boot_pending:
            print(tr("Einrichtung: {wert}", wert=_setup_line(m, p)))
        print(tr("SSH:     ssh -p {wert} {username}@127.0.0.1", wert=rt.get('ssh_port'), username=c.username))
    elif m.status() == vm.STATUS_ABORTED:
        print(tr("Ursache: {wert}", wert=m.abort_reason().text()))
        print(tr("Fortsetzen mit: bonys-agents start {name}", name=c.name))
    _print_remote(m)
    return 0


def remote_state_text(r: dict) -> str:
    if r["active"]:
        return "an (dauerhaft)" if r["permanent"] else "an (bis zum Herunterfahren)"
    return "aus (wird beim nächsten Start dauerhaft eingeschaltet)" if r["permanent"] else "aus"


def _print_remote(m: vm.VM) -> None:
    r = m.remote_info()
    print(tr("Fernzugriff: {wert}", wert=remote_state_text(r)))
    if r["spice_local"]:
        where = "aus dem Heimnetz (mit Passwort)" if r["spice_lan"] else "nur an diesem Rechner"
        print(tr("  SPICE {wert} – {where}", wert=r['spice_local'], where=where))
    if not r["active"]:
        if not r["rdp_installed"]:
            print(tr("  RDP: xrdp fehlt im Agent-PC (bonys-agents install NAME xrdp)"))
        return
    for addr in r["addresses"] or ["(keine Heimnetz-Adresse gefunden)"]:
        spice = f"  ·  SPICE spice://{addr}:{r['spice_port']}" if r["spice_lan"] else ""
        print(tr("  RDP {addr}:{wert}{spice}", addr=addr, wert=r['rdp_port'], spice=spice))
    print(tr("  Benutzer: {wert} (Passwort des Agent-PCs)", wert=r['username']))
    if r["spice_password"]:
        print(tr("  SPICE-Passwort: {wert}", wert=r['spice_password']))
    if r["needs_restart"]:
        print(tr("  Hinweis: SPICE aus dem Heimnetz erst nach einem Neustart des Agent-PCs – RDP geht sofort."))
    print(f"  {remote.LAN_WARNING}")


def cmd_remote(args) -> int:
    m = vm.get(args.name)
    on = args.state == "on"
    if m.is_running() and on:
        print(tr("Schalte xrdp im Agent-PC ein … (ohne Gast-Agent fragt ssh nach dem Passwort des Agent-PCs)"))
    print(m.set_remote(on, permanent=args.permanent, ssh_prompt=True))
    if on and remote.firewall_needed():
        r = m.remote_info()
        ports = [m.config.rdp_port] + ([m.config.spice_port] if r["spice_lan"] else [])
        q = f"Firewall: Ports {', '.join(map(str, ports))} nur für das Heimnetz freigeben? (ja/nein) "
        if input(q).strip().lower() in ("j", "ja", "y", "yes"):
            print(remote.allow_firewall(m.name, ports)[1])
    _print_remote(m)
    return 0


def cmd_connect(args) -> int:
    m = vm.get(args.name)
    m.connect("SPICE" if args.spice else "RDP")
    print(tr("Verbindung zu '{name}' wird geöffnet …", name=m.name))
    return 0


def cmd_display(args) -> int:
    m = vm.get(args.name)
    m.set_display(args.mode)
    label = "SPICE-Fenster" if args.mode == "spice" else "QEMU-Fenster"
    print(tr("Anzeige von '{name}': {label} (ab dem nächsten Start).", name=m.name, label=label))
    return 0


def cmd_screen(args) -> int:
    m = vm.get(args.name)
    if args.mode is None and args.size is None:
        print(tr("Bildschirm von '{name}': {wert}", name=m.name, wert=screen.label(*m.screen_settings())))
        return 0
    mode = args.mode or m.screen_settings()[0]
    m.set_screen(mode, args.size)
    print(f"Bildschirm von '{m.name}': {screen.label(*m.screen_settings())}"
          + (" (ab dem nächsten Start)." if m.is_running() else "."))
    return 0


def cmd_fullscreen(args) -> int:
    print(vm.get(args.name).fullscreen())
    return 0


def cmd_display_driver(args) -> int:
    m = vm.get(args.name)
    print(tr("Richte den Anzeige-Treiber in '{name}' ein … (ohne Gast-Agent fragt ssh nach dem Passwort)", name=m.name),
          flush=True)
    print(m.update_display_driver(ssh_prompt=True))
    return 0


def cmd_logs(args) -> int:
    print(vm.get(args.name).console_tail(args.lines))
    return 0


def cmd_delete(args) -> int:
    m = vm.get(args.name)
    if not args.yes:
        if input(f"'{args.name}' mit allen Daten löschen? (ja/nein) ").strip().lower() not in ("j", "ja", "y", "yes"):
            print(tr("Abgebrochen."))
            return 1
    hint = netz.loeschen_hinweis(m) if m.template_lock_pid() is None else ""
    m.delete()
    print(tr("'{name}' gelöscht.", name=args.name))
    if hint:
        print(f"⚠ {hint}")
    return 0


def cmd_desktops(args) -> int:
    print(tr("{wert:10} {wert2:12} {wert3:>7}  BESCHREIBUNG", wert='ID', wert2='NAME', wert3=tr('RAM AB')))
    for d in desktops.DESKTOPS.values():
        std = "  " + tr("[Standard]") if d.id == desktops.DEFAULT else ""
        print(f"{d.id:10} {d.name:12} {desktops.format_ram(d.min_ram_mb):>7}  {tr(d.description)}{std}")
    return 0


def cmd_add_desktop(args) -> int:
    m = vm.get(args.name)
    spec = desktops.get(args.desktop)
    print(tr("Installiere {name} in „{name2}“ per SSH – ssh fragt ggf. nach dem Passwort des Agent-PCs.",
             name=spec.name, name2=m.name))
    m.install_desktop(spec.id, make_default=not args.keep_default)
    if args.keep_default:
        print(tr("Fertig: {name} ist installiert und am Anmeldebildschirm wählbar.", name=spec.name))
    else:
        print(tr("Fertig: Ab dem nächsten Start meldet sich „{name}“ automatisch in {name2} an.", name=m.name,
                 name2=spec.name))
    return 0


def _app_line(a: apps.AppSpec, extra: str = "") -> str:
    deps = apps.dependencies([a.id])
    note = "  " + tr("(bringt {programme} mit)", programme=", ".join(apps.names(deps))) if deps else ""
    return f"  {a.id:16} {tr(a.name):22} {tr(a.description)}{note}{extra}"


def cmd_apps(args) -> int:
    if getattr(args, "name", None):
        return _apps_of(vm.get(args.name))
    for title, cat in ((tr("Programme"), apps.PROGRAM), (tr("KI-Werkzeuge (--agents)"), apps.AGENT)):
        print(f"{title}:")
        for a in apps.APPS.values():
            if a.category == cat and not a.hidden:
                print(_app_line(a, "  " + tr("[Standard]") if a.default else ""))
    hidden = [tr(a.name) for a in apps.APPS.values() if a.hidden]
    if hidden:
        print(tr("\nBausteine, die bei Bedarf automatisch mitkommen: {wert}", wert=', '.join(hidden)))
    print(tr("\nMission Control: {wert}.", wert=mission_control.requirement_note()))
    return 0


def _apps_of(m: vm.VM) -> int:
    c = m.config
    print(tr("Installiert in „{name}“:", name=m.name))
    for app_id in c.apps:
        info = c.app_info.get(app_id) or {}
        ver = f"  Version {info['version']}" if info.get("version") else ""
        name = apps.APPS[app_id].name if app_id in apps.APPS else app_id
        print(f"  {app_id:16} {name}{ver}")
    missing = m.missing_apps()
    if missing:
        print(tr("\nVerfügbar (bonys-agents install NAME APP …):"))
        for a in missing:
            print(_app_line(a))
    else:
        print(tr("\nAlle verfügbaren Apps sind installiert."))
    return 0


def app_selection(apps_arg: str | None, agents_arg: str | None,
                  distro: str = distros.DEFAULT) -> list[str] | None:
    """--apps und --agents zu einer App-Liste zusammenführen (None = Standard).

    --agents ersetzt nur die KI-Werkzeuge; „none“ bzw. leer = keins.
    """
    if apps_arg is None and agents_arg is None:
        return None
    ids = [i.strip() for i in (apps_arg.split(",") if apps_arg else apps.default_app_ids(distro)) if i.strip()]
    if agents_arg is not None:
        agents = [i.strip() for i in agents_arg.split(",") if i.strip() and i.strip().lower() not in ("none", "keins")]
        wrong = [i for i in agents if i in apps.APPS and apps.APPS[i].category != apps.AGENT]
        if wrong:
            raise ValueError(tr("--agents ist nur für KI-Werkzeuge ({wert}); {wert2} bitte über --apps angeben.",
                                wert=', '.join(apps.ids_in_category(apps.AGENT)), wert2=', '.join(wrong)))
        agent_ids = set(apps.ids_in_category(apps.AGENT))
        ids = [i for i in ids if i not in agent_ids] + agents
    apps.resolve(ids)  # unbekannte IDs früh melden
    return ids


def cmd_install(args) -> int:
    m = vm.get(args.name)
    plan = m.install_plan(args.apps)
    if not plan:
        print(tr("Schon installiert: {wert}.", wert=', '.join(apps.names(args.apps))))
        return 0
    deps = [i for i in plan if i not in args.apps]
    print(f"Installiere in „{m.name}“: {', '.join(apps.names(plan))}"
          + (f" ({', '.join(apps.names(deps))} wird mitinstalliert)" if deps else ""))
    if mission_control.APP_ID in plan:
        for w in mission_control.resource_warnings(plan, m.config.ram_mb, m.config.disk_gb,
                                                   desktops.get(m.config.desktop).min_ram_mb,
                                                   mission_control.requirements()):
            print(f"⚠ {w}")
    print(tr("Ohne Gast-Agent fragt ssh nach dem Passwort des Agent-PCs. Bricht etwas ab: denselben Befehl erneut "
             "ausführen – fertige Programme werden übersprungen."))

    def step(n: int, total: int, app_id: str) -> None:
        print(f"==> ({n}/{total}) {apps.APPS[app_id].name}")

    m.install_apps(args.apps, ssh_prompt=True, log=print, step=step)
    print(tr("Fertig: {wert} installiert. Die Symbole liegen auf dem Schreibtisch des Agent-PCs.",
             wert=', '.join(apps.names(plan))))
    return 0


def cmd_mission_control(args) -> int:
    m = vm.get(args.name)
    mc = mission_control
    kw = {"ssh_prompt": True}
    if args.action == "status":
        if mc.APP_ID not in m.config.apps:
            print(tr("{NAME} ist in „{name}“ nicht installiert (bonys-agents install {name} {APP_ID}).",
                     NAME=mc.NAME, name=m.name, APP_ID=mc.APP_ID))
            return 1
        st = mc.status(m, **kw) if m.is_running() else None
        print(f"{mc.NAME}: " + (mc.status_text(st) if st else "Agent-PC läuft nicht"))
        if st and st.get("installed"):
            print(tr("  Adresse im Agent-PC: http://127.0.0.1:{wert}/", wert=st.get('port', mc.PORT)))
        if m.config.mc_forward:
            print(tr("  Weiterleitung an diesen Rechner: {wert} (nur 127.0.0.1)", wert=mc.forward_url(m)))
        return 0 if st is None or st.get("healthy") else 1
    if args.action == "open":
        print(mc.open_in_guest(m, **kw))
    elif args.action == "update":
        print(tr("Aktualisiere {NAME} auf {version} … (Einstellungen, Geheimnisse und Daten bleiben)", NAME=mc.NAME,
                 version=args.version))
        print(mc.update(m, version=args.version, log=print, **kw))
    elif args.action == "uninstall":
        if args.purge and not _yes(f"Wirklich ALLE Daten und Einstellungen von {mc.NAME} in „{m.name}“ löschen? "
                                   "Das lässt sich nicht rückgängig machen.", args.yes):
            print(tr("Abgebrochen."))
            return 1
        print(mc.uninstall(m, purge=args.purge, log=print, **kw))
    elif args.action == "forward":
        if args.value not in ("on", "off"):
            print(tr("Bitte „forward on“ oder „forward off“ angeben."), file=sys.stderr)
            return 2
        if args.value == "on":
            print(f"⚠ {mc.FORWARD_WARNING}")
            if not _yes("Weiterleitung einschalten?", args.yes):
                print(tr("Abgebrochen."))
                return 1
        print(mc.set_forward(m, args.value == "on", **kw))
    return 0


def _print_vpn(st: dict, name: str = "NAME") -> None:
    print(vpnlink.summary(st))
    if st.get("compat") in vpnlink.COMPAT_TEXT:
        print(f"  ⚠ {vpnlink.COMPAT_TEXT[st['compat']]}")
        if st["compat"] in ("legacy", "outdated"):
            print(tr("    → bonys-agents vpn {name} update", name=name))
    for t in st.get("tunnels") or []:
        flags = [x for x, on in (("verbunden", t.get("active")), ("automatisch", t.get("autostart"))) if on]
        line = f"  {t['name']}" + (f"  [{', '.join(flags)}]" if flags else "")
        if t.get("active"):
            line += (f"  · Handshake {vpnlink.human_age(t.get('handshake'))}"
                     f"  · empfangen {vpnlink.human_bytes(t.get('rx'))}, gesendet {vpnlink.human_bytes(t.get('tx'))}")
        print(line)
    ks = st.get("killswitch") or {}
    if ks.get("exceptions"):
        print(tr("  Kill-Switch-Ausnahmen: {wert}", wert=', '.join(ks['exceptions'])))


def cmd_vpn(args) -> int:
    m = vm.get(args.name)
    kw = {"ssh_prompt": True}  # ohne Gast-Agent: ssh fragt im Terminal nach dem Passwort
    value = args.value
    if args.action == "import":
        if not value:
            raise ValueError(tr("Datei fehlt: bonys-agents vpn NAME import DATEI.conf"))
        setup = vpnlink.load_conf(value, name=args.tunnel)
        vpnlink.import_conf(m, setup, replace=args.replace, **kw)
        print(tr("„{name}“ ist in „{name2}“ importiert. Verbinden mit: bonys-agents vpn {name2} up", name=setup.name,
                 name2=m.name))
        return 0
    if args.action == "update":
        if value:
            raise ValueError(tr("„update“ erwartet keine weitere Angabe."))
        print(tr("Installiere das neueste Bony's VPN aus dem offiziellen Release ({VPN_REPO_URL}) in „{name}“ – "
                 "Signatur und Prüfsumme werden geprüft, Tunnel und Kill-Switch bleiben …",
                 VPN_REPO_URL=vpnlink.VPN_REPO_URL, name=m.name))
        vpnlink.update_app(m, log=print, **kw)
        st = vpnlink.status(m, **kw)
        print(tr("Fertig: Bony's VPN {wert} ist installiert.", wert=st.get('version', '')))
        return 0
    if value and args.action in ("status", "ip"):
        raise ValueError(tr("„{action}“ erwartet keine weitere Angabe.", action=args.action))
    tunnel = args.tunnel or (value if args.action in ("up", "down") else None)
    state = {"an": "on", "aus": "off"}.get(value or "", value)
    if args.action == "status":
        st = vpnlink.status(m, **kw)
        if args.json:
            print(json.dumps(st, ensure_ascii=False, indent=2))
        else:
            _print_vpn(st, m.name)
        return 0 if st.get("installed", True) else 1
    if args.action == "ip":
        print(vpnlink.public_ip(m, **kw))
        return 0
    if args.action == "up":
        tunnel = tunnel or vpnlink.default_tunnel(vpnlink.status(m, **kw))
        if not tunnel:
            raise ValueError(tr("Welcher Tunnel? bonys-agents vpn NAME up TUNNEL (siehe: vpn NAME status)"))
        vpnlink.up(m, tunnel, **kw)
        print(tr("„{tunnel}“ ist verbunden.", tunnel=tunnel))
    elif args.action == "down":
        vpnlink.down(m, tunnel, **kw)
        print(tr("Getrennt."))
    elif args.action == "killswitch":
        if state not in ("on", "off"):
            raise ValueError(tr("bonys-agents vpn NAME killswitch on|off"))
        vpnlink.set_killswitch(m, state == "on", **kw)
        print("Kill-Switch: " + ("an – ohne Tunnel kein Internet (Steuerung des Agent-PCs geht weiter)"
                                 if state == "on" else "aus"))
    elif args.action == "autostart":
        tunnel = tunnel or vpnlink.default_tunnel(vpnlink.status(m, **kw))
        if state not in ("on", "off") or not tunnel:
            raise ValueError(tr("bonys-agents vpn NAME autostart on|off [--tunnel TUNNEL]"))
        vpnlink.set_autostart(m, tunnel, state == "on", **kw)
        print(tr("„{tunnel}“ verbindet sich {wert}.", tunnel=tunnel,
                 wert='beim Start automatisch' if state == 'on' else 'nicht automatisch'))
    return 0


def _yes(question: str, assume_yes: bool = False) -> bool:
    return assume_yes or input(f"{question} (ja/nein) ").strip().lower() in ("j", "ja", "y", "yes")


def cmd_update(args) -> int:
    """Nach einer neuen Version von Bony's Agents suchen und sie (nach Zustimmung) installieren."""
    from bonys_agents import updates

    st = updates.settings()
    info = updates.check(prereleases=args.pre or st["prereleases"])
    updates.set_setting("last", time.time())
    if info is None:
        print(tr("Keine Updates gefunden – {APP_NAME} {version__} ist aktuell.", APP_NAME=APP_NAME,
                 version__=__version__))
        return 0
    print(tr("Version {version} ist verfügbar (installiert: {version__}).", version=info.version,
             version__=__version__))
    if info.html_url:
        print(tr("Was ist neu: {html_url}", html_url=info.html_url))
    if args.check:
        return 0
    h = host.detect()
    if not updates.can_self_update(h.os):
        print(tr("Bitte die neue Version von der Release-Seite laden: {wert}",
                 wert=info.html_url or updates.release_page()))
        return 0
    if not _yes(f"Jetzt auf {info.version} aktualisieren?", args.yes):
        print(tr("Abgebrochen – es wurde nichts installiert."))
        return 1
    if h.os == "macos":
        try:
            dmg = updates.install_macos(info, h.arch, log=print)
        except updates.UpdateError as e:
            print(tr("Fehler: {e}", e=e), file=sys.stderr)
            return 1
        print(tr("Im Finder-Fenster „{APP_NAME}“ auf „Programme“ ziehen und „Ersetzen“ wählen ({dmg}).",
                 APP_NAME=APP_NAME, dmg=dmg))
        return 0
    running = [m for m in vm.list_vms() if m.is_running()]
    if running:
        names = ", ".join(m.name for m in running)
        print(tr("Laufende Agent-PCs: {names}. Sie laufen beim Update weiter, die App startet aber neu.", names=names))
        if not args.yes and _yes("Vorher herunterfahren?"):
            for m in running:
                print(tr("Fahre „{name}“ herunter …", name=m.name))
                m.stop()
    try:
        if h.os == "linux":
            updates.install_linux(info, h.arch, gui=False, log=print)
            print(tr("Fertig: {APP_NAME} {version} ist installiert. Offene Fenster der App bitte neu starten.",
                     APP_NAME=APP_NAME, version=info.version))
        else:
            updates.install_windows(info, log=print)
            print(tr("Der Installer läuft – er startet die App danach neu."))
    except updates.UpdateError as e:
        print(tr("Fehler: {e}", e=e), file=sys.stderr)
        return 1
    return 0


def cmd_upgrade(args) -> int:
    """Agent-PCs aktualisieren (System, Flatpaks, KI-Werkzeuge)."""
    if args.all:
        machines = [m for m in vm.list_vms() if m.is_running() and m.status() == "läuft"]
        if not machines:
            print(tr("Kein laufender, fertig eingerichteter Agent-PC."))
            return 0
    elif args.name:
        machines = [vm.get(args.name)]
    else:
        print(tr("Bitte einen Namen angeben oder --all."), file=sys.stderr)
        return 2
    failed = 0
    for m in machines:
        print(tr("==> Aktualisiere „{name}“ … (ohne Gast-Agent fragt ssh nach dem Passwort des Agent-PCs)",
                 name=m.name),
              flush=True)
        try:
            result = m.upgrade(ssh_prompt=True, log=lambda line: print(line, flush=True))
        except RuntimeError as e:
            print(tr("Fehler bei „{name}“: {e}", name=m.name, e=e), file=sys.stderr)
            failed += 1
            continue
        print(result.message(m.name))
        if result.reboot_required:
            print(tr("   Neustart: bonys-agents stop {name} && bonys-agents start {name}", name=m.name))
        failed += 0 if result.ok else 1
    return 1 if failed else 0


def _template_progress(phase: str, frac: float, msg: str) -> None:
    print(f"\r{_bar(frac)} {msg[:60]:60}", end="", flush=True)


def cmd_template_create(args) -> int:
    from bonys_agents import cloudinit, templates

    m = vm.get(args.vm)
    remove = not args.keep_personal_data
    print(tr("Vorlage „{name}“ aus „{name2}“. Das Original bleibt unverändert: Verallgemeinert wird eine Kopie "
             "seiner Festplatte (ohne Netz).\n", name=args.name, name2=m.name))
    print(tr("In der Vorlage wird gelöscht bzw. zurückgesetzt:"))
    if remove:
        print(f"  • {tr(vpnlink.FRESH_CLEANUP)}")
        print(f"  • {tr(mission_control.FRESH_CLEANUP)}")
        if n8n.APP_ID in m.config.apps:
            print(f"  • {tr(n8n.FRESH_CLEANUP)}")
        for item in cloudinit.PERSONAL_DATA:
            print(f"  • {tr(item.title)}")
            for path in item.paths:
                print(tr("      /home/{username}/{path}{wert}", username=m.config.username, path=path,
                         wert=item.note()))
    else:
        print(tr("  • Persönliche Daten bleiben ERHALTEN (--keep-personal-data) – Vorlage nicht weitergeben!"))
        if vpnlink.APP_ID in m.config.apps:
            print(f"  ⚠ {tr(vpnlink.CLONE_WARNING)}")
        if mission_control.APP_ID in m.config.apps:
            print(f"  ⚠ {tr(mission_control.CLONE_NOTE)}")
    for line in cloudinit.SYSTEM_CLEANUP:
        print(f"  • {line}")
    print()
    if m.is_running():
        if not _yes(f"„{m.name}“ läuft. Jetzt herunterfahren?", args.yes):
            print(tr("Abgebrochen."))
            return 1
        print(tr("Fahre „{name}“ herunter …", name=m.name))
        m.stop()
    if args.dry_run:
        print(tr("Probelauf: Arbeitskopie startet und sieht nach, was es im Agent-PC tatsächlich gibt …"))
        out = templates.preview(m.name, remove, progress=_template_progress)
        print("\n" + out)
        return 0
    if not _yes("Vorlage jetzt erstellen?", args.yes):
        print(tr("Abgebrochen."))
        return 1
    t0 = time.monotonic()
    tpl = templates.create(m.name, args.name, args.description or "", remove_personal=remove,
                           location=Path(args.location) if args.location else None,
                           progress=_template_progress,
                           log=(lambda line: print("\n  " + line, end="")) if args.verbose else None)
    print(tr("\nVorlage „{name}“ erstellt in {wert:.0f} s: {path} ({wert2:.1f} GB)", name=tpl.name,
             wert=time.monotonic() - t0, path=tpl.path, wert2=tpl.size / storage.GB))
    print(tr("Neuer Agent-PC daraus: bonys-agents create NAME --template {name}", name=tpl.name))
    return 0


def cmd_template_list(args) -> int:
    from bonys_agents import templates

    items = templates.list_templates()
    if not items:
        print(tr("Noch keine Vorlagen. Erstellen mit: bonys-agents template create AGENT-PC NAME"))
        return 0
    print(tr("{wert:24} {wert2:>8} {wert3:17} {wert4:>9}  SPEICHERORT", wert='NAME', wert2=tr('GRÖSSE'),
             wert3=tr('ERSTELLT'), wert4=tr('VERKNÜPFT')))
    for t in items:
        print(tr("{name:24} {wert:>6.1f}GB {wert2:17} {wert3:>9}  {library}", name=t.name, wert=t.size / storage.GB,
                 wert2=t.created_local(), wert3=len(t.linked_vms()), library=t.library))
        extra = [t.description] if t.description else []
        extra.append(tr("aus {quelle}, Debian {debian}, {arch}, Apps: {programme}", quelle=t.source,
                        debian=t.debian or "?", arch=t.arch, programme=", ".join(apps.names(t.apps)))
                     + ("" if t.personal_data_removed else ", " + tr("MIT persönlichen Daten")))
        for line in extra:
            print(f"    {line}")
    return 0


def cmd_template_delete(args) -> int:
    from bonys_agents import templates

    t = templates.get(args.name)
    linked = t.linked_vms()
    if linked:
        names = ", ".join(m.name for m in linked)
        print(tr("Verknüpfte Agent-PCs bauen auf „{name}“ auf: {names}", name=t.name, names=names))
        if not args.make_independent:
            print(tr("Löschen gesperrt. Erst mit --make-independent zu unabhängigen Kopien machen."), file=sys.stderr)
            return 1
        for m in linked:
            if m.is_running():
                print(tr("„{name}“ läuft – bitte erst herunterfahren.", name=m.name), file=sys.stderr)
                return 1
        for m in linked:
            print(tr("Mache „{name}“ unabhängig …", name=m.name))
            m.make_independent(progress=lambda f: print(f"\r{_bar(f)}", end="", flush=True))
            print()
    if not _yes(f"Vorlage „{t.name}“ ({t.size / storage.GB:.1f} GB) löschen?", args.yes):
        print(tr("Abgebrochen."))
        return 1
    templates.delete(t.name)
    print(tr("Vorlage „{name}“ gelöscht.", name=t.name))
    return 0


def cmd_template_export(args) -> int:
    from bonys_agents import bonysfile, templates

    t = templates.get(args.name)
    removed = apps.not_redistributable(t.apps)
    print(tr("Export von „{name}“ als .bonys-Datei. Die Vorlage bleibt unverändert: Geprüft und bereinigt wird eine "
             "Kopie (ohne Netz).", name=t.name))
    if removed:
        print(tr("Nicht frei weitergebbar, wird aus der Kopie entfernt: {wert} – der Empfänger installiert es aus "
                 "der offiziellen Quelle neu.", wert=', '.join(apps.names(removed))))
    if not t.personal_data_removed and not args.clean:
        print(tr("Diese Vorlage enthält persönliche Daten (Klon). Export nur „frisch gemacht“: mit --clean werden die "
                 "persönlichen Daten in der Export-Kopie entfernt."), file=sys.stderr)
        return 1
    try:
        out = bonysfile.export(t.name, Path(args.file) if args.file else None, creator=args.creator or "",
                               version=args.version or "", clean=args.clean,
                               preview=Path(args.preview) if args.preview else None,
                               progress=_template_progress,
                               log=(lambda line: print("\n  " + line, end="")) if args.verbose else None)
    except bonysfile.NotFreshError as e:
        print(f"\n{e}", file=sys.stderr)
        if not e.strict:
            print(tr("\nBereinigen (nur in der Export-Kopie, die Vorlage bleibt): erneut mit "
                     "--clean."), file=sys.stderr)
        return 1
    print(tr("\nExportiert: {out} ({wert:.2f} GB)", out=out, wert=out.stat().st_size / storage.GB))
    print(bonysfile.describe_manifest(bonysfile.read_manifest(out)))
    return 0


def cmd_template_import(args) -> int:
    from bonys_agents import bonysfile

    file = Path(args.file)
    if not bonysfile.is_bonys(file):
        if args.recipe or args.create:
            print(tr("--create/--recipe gibt es nur für .bonys-Dateien."), file=sys.stderr)
            return 2
        t = bonysfile.import_any(file, location=Path(args.location) if args.location else None, name=args.name,
                                 progress=_template_progress)
        print(tr("\nVorlage „{name}“ importiert (altes Format): {path}", name=t.name, path=t.path))
        return 0
    return _import_bonys(file, args)


def _import_bonys(file: Path, args) -> int:
    """.bonys importieren – mit Anzeige des Inhalts, Architektur-Prüfung, --create/--recipe (template import, join)."""
    from bonys_agents import bonysfile

    m = bonysfile.read_manifest(file)
    print(bonysfile.describe_manifest(m, file.stat().st_size))
    print()
    host_arch = host.detect().arch
    if args.recipe:
        return _create_from_recipe(args, m)
    if not bonysfile.arch_matches(m):
        print("⚠ " + tr(bonysfile.SLOW_ARCH_WARNING, tpl=m["arch"], host=bonysfile.arch_name(host_arch)))
        print(tr("   Rezept: bonys-agents template import {file} --recipe NAME", file=file))
        if args.create and not args.foreign_arch:
            print(tr("Trotzdem aus der Vorlage erstellen: --foreign-arch"), file=sys.stderr)
            return 1
    password = None
    if args.create:
        if any(m2.name == args.create for m2 in vm.list_all()):
            raise FileExistsError(tr("Agent-PC '{create}' existiert bereits", create=args.create))
        password = args.password or _ask_password()
    t = bonysfile.import_bundle(file, location=Path(args.location) if args.location else None, name=args.name,
                                progress=_template_progress)
    print(tr("\nVorlage „{name}“ importiert (Prüfsumme stimmt): {path}", name=t.name, path=t.path))
    if not args.create:
        print(tr("Neuer Agent-PC daraus: bonys-agents create NAME --template {name}", name=t.name))
        _print_reinstall_hint("NAME", t.reinstall)
        return 0
    rec = m.get("recommended", {})
    machine = vm.create(args.create, password, template=t.name, cpus=args.cpus or rec.get("cpus"),
                        ram_mb=args.ram or rec.get("ram_mb"), linked=False if args.full else None,
                        location=Path(args.vm_location) if args.vm_location else None,
                        foreign_arch=args.foreign_arch,
                        progress=lambda phase, frac, msg: print(f"\r{_bar(frac)} {msg[:50]:50}", end="", flush=True))
    c = machine.config
    print(tr("\nAgent-PC '{name}' aus „{name2}“: {cpus} CPUs, {ram_mb} MB RAM, {disk_gb} GB", name=c.name,
             name2=t.name, cpus=c.cpus, ram_mb=c.ram_mb, disk_gb=c.disk_gb))
    print(tr("Beim ersten Start bekommt er eine neue Maschinen-ID, neue SSH-Hostschlüssel und neue Geheimnisse."))
    print(tr("Starten mit: bonys-agents start {name}", name=c.name))
    _print_reinstall_hint(c.name, t.reinstall)
    return 0


def _print_reinstall_hint(vm_name: str, ids: list[str]) -> None:
    ids = [i for i in ids if i in apps.APPS]
    if ids:
        print(tr("Nicht mitgeliefert (Lizenz): {wert}. Aus der offiziellen Quelle installieren, wenn der Agent-PC "
                 "läuft: bonys-agents install {vm_name} {wert2}", wert=', '.join(apps.names(ids)), vm_name=vm_name,
                 wert2=' '.join(ids)))


def _create_from_recipe(args, m: dict) -> int:
    """Rezept: dieselbe Ausstattung mit dem passenden Cloud-Image neu einrichten (ohne die Festplatte)."""
    from bonys_agents import bonysfile

    r = bonysfile.recipe(m)
    print(tr("Rezept: {wert} mit {wert2} wird hier neu eingerichtet ({wert3} für diesen Rechner, Downloads aus den "
             "offiziellen Quellen).", wert=desktops.name(r['desktop']),
             wert2=', '.join(apps.names(r['app_ids'])) or 'ohne Apps', wert3=distros.name(r['distro'])))
    if m.get("extra_desktops"):
        print(tr("Zusätzliche Desktops kommen nicht mit – nachrüsten mit „Desktop hinzufügen …“."))
    if not _ensure_ready(args.yes):
        print(tr("Agent-PC kann noch nicht erstellt werden – siehe oben."))
        return 1
    password = args.password or _ask_password()
    machine = vm.create(args.recipe, password, cpus=args.cpus or r["cpus"], ram_mb=args.ram or r["ram_mb"],
                        disk_gb=r["disk_gb"] or vm.DEFAULT_DISK_GB, username=r["username"], app_ids=r["app_ids"],
                        keyboard=r["keyboard"], timezone_name=r["timezone_name"], desktop=r["desktop"],
                        distro=r["distro"], location=Path(args.vm_location) if args.vm_location else None,
                        progress=lambda phase, frac, msg: print(f"\r{_bar(frac)} {msg[:50]:50}", end="", flush=True))
    print(tr("\nAgent-PC '{name}' angelegt. Starten (richtet sich dann ein): bonys-agents start {name}",
             name=machine.name))
    return 0


def _print_qr(text: str) -> None:
    try:
        import qrcode
    except ImportError:
        return
    qr = qrcode.QRCode(border=1)
    qr.add_data(text)
    try:
        qr.print_ascii(invert=True)
    except (UnicodeEncodeError, OSError):
        pass


def cmd_wallpaper(args) -> int:
    """Neues Standard-Hintergrundbild in einen laufenden Agent-PC bringen – eigene Bilder nur mit --force."""
    from bonys_agents import wallpaper

    m = vm.get(args.name)
    if args.check:
        s = wallpaper.check(m, ssh_prompt=True)
        print({wallpaper.CURRENT: "Neues Standardbild aktiv.", wallpaper.OLD: "Noch das alte Standardbild.",
               wallpaper.FOREIGN: "Die Bilddatei ist keines unserer Standardbilder.",
               wallpaper.MISSING: "Kein Standardbild vorhanden."}.get(s.state, s.state))
        for c in s.custom:
            print(tr("  Eigenes Bild – {c}", c=c))
        return 0
    s = wallpaper.update(m, force=args.force, ssh_prompt=True)
    print(wallpaper.describe(s))
    if s.done == "nachfragen":
        print(tr("Nichts geändert. Trotzdem auf das neue Standardbild umstellen: bonys-agents wallpaper {name} "
                 "--force", name=m.name))
        return 1
    return 0


def cmd_join(args) -> int:
    """Einer Schulung beitreten: Vorlage vom Kursleiter-Rechner laden (setzt fort), prüfen, importieren."""
    from bonys_agents import bonysfile, share

    if not args.address:
        print(tr("Suche Freigaben im Netz (mDNS) …"))
        found = [f for f in share.discover() if f.txt.get("kind") != "present"]
        if not found:
            print(tr("Keine Freigabe gefunden. In VPN-Netzen geht die Suche nicht – dann Adresse und Code angeben: "
                     "bonys-agents join ADRESSE CODE"), file=sys.stderr)
            return 1
        for f in found:
            print(tr("  {address}  {wert} {wert2} von {wert3}  (Fingerabdruck {wert4})", address=f.address,
                     wert=f.txt.get('name', '?'), wert2=f.txt.get('version', ''), wert3=f.txt.get('creator') or '?',
                     wert4=share.short_fingerprint(f.txt.get('fp', ''))))
        if len(found) > 1:
            print(tr("Mehrere Freigaben – bitte eine Adresse angeben."), file=sys.stderr)
            return 1
        args.address = found[0].address  # Fingerabdruck aus mDNS ist fälschbar – unten trotzdem vergleichen lassen
    target = share.parse_target(args.address, args.code or "", args.fingerprint or "")
    if not target.code:
        target.code = share.normalize_code(input("Freigabe-Code (z. B. 4711-BONY): "))
    try:
        info = share.fetch_info(target)
    except share.IsPresentation as e:
        print(tr("Unter {netloc} läuft keine Freigabe, sondern die Vorführung „{title}“ – im Browser öffnen:",
                 netloc=target.netloc, title=e.title))
        print(f"  {e.url()}")
        print(tr("  Fingerabdruck zum Vergleichen: {wert}", wert=share.short_fingerprint(e.fingerprint)))
        return 0
    print(tr("Verbunden mit {netloc}. Fingerabdruck: {wert}", netloc=target.netloc,
             wert=share.short_fingerprint(info.fingerprint)))
    if not target.fingerprint:
        print(tr("   ganz: {wert}", wert=share.format_fingerprint(info.fingerprint)))
        if not _yes("Stimmt er mit dem auf dem Bildschirm des Kursleiters überein?", args.yes):
            print(tr("Abgebrochen – nichts geladen."))
            return 1
    print()
    print(bonysfile.describe_manifest(info.manifest, info.size))
    print()
    dest = Path(args.dir) if args.dir else share.downloads_dir()
    file = share.download(info, dest, progress=lambda phase, frac, msg: print(f"\r{_bar(frac)} {msg[:60]:60}",
                                                                                end="", flush=True))
    print(tr("\nGeladen: {file}\n", file=file))
    return _import_bonys(file, args)


def cmd_template_rename(args) -> int:
    from bonys_agents import templates

    t = templates.rename(args.name, args.new_name)
    print(tr("Vorlage heißt jetzt „{name}“.", name=t.name))
    return 0


def cmd_template_describe(args) -> int:
    from bonys_agents import templates

    templates.set_description(args.name, args.text)
    print(tr("Beschreibung gespeichert."))
    return 0


def cmd_make_independent(args) -> int:
    m = vm.get(args.name)
    if not m.is_linked():
        print(tr("„{name}“ ist bereits unabhängig.", name=m.name))
        return 0
    print(tr("Übernehme die Daten der Vorlage in „{name}“ …", name=m.name))
    m.make_independent(progress=lambda f: print(f"\r{_bar(f)}", end="", flush=True))
    print(tr("\n„{name}“ ist jetzt eine unabhängige Kopie.", name=m.name))
    return 0


def cmd_gui(args) -> int:
    from bonys_agents.gui.app import run
    return run()


def _import_options(p) -> None:
    """Gemeinsame Optionen von „template import“ und „join“."""
    p.add_argument("--name", help=tr("Unter anderem Namen ablegen"))
    p.add_argument("--location", metavar="ORDNER", help=tr("Speicherort der Vorlage (Standard: der bevorzugte)"))
    p.add_argument("--create", metavar="AGENT-PC", help=tr("Gleich einen Agent-PC daraus erstellen (unabhängige "
                                                           "Kopie, wenn --full; sonst verknüpft, wenn möglich)"))
    p.add_argument("--recipe", metavar="AGENT-PC",
                   help=tr("Nur das Rezept nutzen: Desktop und Apps hier neu einrichten (z. B. andere Architektur)"))
    p.add_argument("--full", action="store_true", help=tr("Mit --create: unabhängige Kopie"))
    p.add_argument("--vm-location", metavar="ORDNER", help=tr("Mit --create/--recipe: Speicherort des Agent-PCs"))
    p.add_argument("--ram", type=int, metavar="MB", help=tr("Mit --create/--recipe: RAM (Standard: Empfehlung)"))
    p.add_argument("--cpus", type=int, help=tr("Mit --create/--recipe: CPUs (Standard: Empfehlung)"))
    p.add_argument("--password", help=argparse.SUPPRESS)
    p.add_argument("--foreign-arch", action="store_true",
                   help=tr("Andere Architektur trotzdem nutzen (Emulation, sehr langsam)"))
    p.add_argument("-y", "--yes", action="store_true")


def _course_commands(sub) -> None:
    """Kursleiter-Befehle (share, present) – in der Anwender-Version nur mit verständlicher Meldung."""
    if edition.IS_TRAINER:
        from bonys_agents.trainer import cli as trainer_cli

        trainer_cli.register(sub)
        return
    for name, what in (("share", "Vorlagen im Netzwerk freigeben"), ("present", "Vorführen")):
        s = sub.add_parser(name, help=tr("Schulung: {what} (nur in {wert})", what=what,
                                         wert=edition.NAMES[edition.KURSLEITER]),
                           add_help=False)
        s.add_argument("rest", nargs=argparse.REMAINDER)
        s.set_defaults(func=lambda _args, what=what: _trainer_only(what))


def _trainer_only(what: str) -> int:
    print(edition.require_trainer(what), file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bonys-agents", description=tr("{APP_NAME} – virtuelle Agent-PCs",
                                                                    APP_NAME=APP_NAME))
    p.add_argument("--version", action="version", version=f"%(prog)s {edition.version_text(__version__)}")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("doctor", help=tr("System prüfen (QEMU, Beschleuniger, Ressourcen)")).set_defaults(func=cmd_doctor)
    st = sub.add_parser("setup", help=tr("QEMU und Beschleunigung automatisch installieren"))
    st.add_argument("-y", "--yes", action="store_true", help=tr("Ohne Rückfrage"))
    st.set_defaults(func=cmd_setup)
    stt = sub.add_parser("selftest", help=tr("Prüfen, ob QEMU auf diesem System startet (wie in der App)"))
    stt.add_argument("--no-qt", action="store_true", help=tr("Bibliotheken der Desktop-App nicht prüfen"))
    stt.add_argument("--boot", action="store_true",
                     help=tr("zusätzlich einen Agent-PC (leere Platte) mit Firmware starten, bis QEMU läuft"))
    stt.set_defaults(func=cmd_selftest)
    up = sub.add_parser("update", help=tr("Nach einer neuen Version von {APP_NAME} suchen und aktualisieren",
                                          APP_NAME=APP_NAME))
    up.add_argument("--check", action="store_true", help=tr("Nur suchen, nichts installieren"))
    up.add_argument("--pre", action="store_true", help=tr("Auch Testversionen anbieten"))
    up.add_argument("-y", "--yes", action="store_true", help=tr("Ohne Rückfrage installieren"))
    up.set_defaults(func=cmd_update)
    ug = sub.add_parser("upgrade", help=tr("Agent-PC aktualisieren (apt, Flatpak, KI-Werkzeuge) – muss laufen"))
    ug.add_argument("name", nargs="?")
    ug.add_argument("--all", action="store_true", help=tr("Alle laufenden Agent-PCs"))
    ug.set_defaults(func=cmd_upgrade)
    ap = sub.add_parser("apps", help=tr("Verfügbare Apps anzeigen – mit NAME: installierte und noch verfügbare"))
    ap.add_argument("name", nargs="?", metavar="NAME", help=tr("Agent-PC"))
    ap.set_defaults(func=cmd_apps)
    sub.add_parser("desktops", help=tr("Verfügbare Desktops mit RAM-Empfehlung "
                                       "anzeigen")).set_defaults(func=cmd_desktops)
    ad = sub.add_parser("add-desktop", help=tr("Weiteren Desktop in einen laufenden Agent-PC installieren (per SSH)"))
    ad.add_argument("name")
    ad.add_argument("desktop", choices=list(desktops.DESKTOPS))
    ad.add_argument("--keep-default", action="store_true",
                    help=tr("Automatische Anmeldung beim bisherigen Desktop lassen"))
    ad.set_defaults(func=cmd_add_desktop)
    sub.add_parser("gui", help=tr("Desktop-App öffnen")).set_defaults(func=cmd_gui)
    sub.add_parser("list", help=tr("Alle Agent-PCs anzeigen")).set_defaults(func=cmd_list)

    c = sub.add_parser("create", help=tr("Neuen Agent-PC anlegen und starten"))
    c.add_argument("name")
    c.add_argument("--cpus", type=int, help=tr("Standard: alle Kerne des Hosts"))
    c.add_argument("--ram", type=int, help=tr("RAM in MB (Standard: Host-RAM minus Reserve)"))
    c.add_argument("--disk", type=_disk_gb, metavar="GB",
                   help=tr("Festplatte in GB, {MIN_DISK_GB}–{MAX_DISK_GB} (Standard: {DEFAULT_DISK_GB}, bei "
                           "--template die Größe der Vorlage)", MIN_DISK_GB=vm.MIN_DISK_GB,
                           MAX_DISK_GB=vm.MAX_DISK_GB, DEFAULT_DISK_GB=vm.DEFAULT_DISK_GB))
    c.add_argument("--template", metavar="VORLAGE",
                   help=tr("Aus einer Vorlage statt neu installieren (siehe: template list)"))
    kind = c.add_mutually_exclusive_group()
    kind.add_argument("--linked", action="store_true",
                      help=tr("Schnell: verknüpft mit der Vorlage (Standard, wenn auf demselben Laufwerk)"))
    kind.add_argument("--full", action="store_true", help=tr("Unabhängige, vollständige Kopie der Vorlage"))
    c.add_argument("--location", metavar="ORDNER",
                   help=tr("Speicherort, z. B. E:\\BonysAgents oder /media/ich/SSD/BonysAgents (siehe: drives)"))
    c.add_argument("--user", default="agent", help=tr("Benutzername im Gast (Standard: agent)"))
    c.add_argument("--password", help=tr("Passwort (sonst wird nachgefragt)"))
    c.add_argument("--apps", help=tr("Kommagetrennt, Standard: {wert} (siehe: apps)",
                                     wert=','.join(apps.default_app_ids())))
    c.add_argument("--agents", metavar="LISTE",
                   help=tr("Nur die KI-Werkzeuge wählen, z. B. hermes,openclaw,claude-code oder none (verfügbar: "
                           "{wert})", wert=','.join(apps.ids_in_category(apps.AGENT))))
    c.add_argument("--desktop", choices=list(desktops.DESKTOPS),
                   help=tr("Desktop-Umgebung (Standard: {DEFAULT}, unter Kali xfce; siehe: desktops)",
                           DEFAULT=desktops.DEFAULT))
    c.add_argument("--distro", default=distros.DEFAULT, choices=list(distros.DISTROS),
                   help=tr("Grundsystem: debian (Standard, Debian 13) oder kali (Kali Linux mit Kali-Werkzeugen, "
                           "nur x86_64 und Xfce)"))
    c.add_argument("--sprache", "--language", choices=("de", "en"),
                   help=tr("Sprache im Agent-PC: de oder en (Standard: die von Bony's Agents)"))
    c.add_argument("--keyboard", help=tr("Tastaturbelegung, z. B. de, us, ch (Standard: passend zur Sprache)"))
    c.add_argument("--timezone", default="Europe/Berlin")
    c.add_argument("--no-start", action="store_true", help=tr("Nur anlegen, nicht starten"))
    c.add_argument("--headless", action="store_true", help=tr("Ohne Fenster starten (auch nach der Einrichtung)"))
    c.add_argument("--wait", action="store_true", help=tr("Warten, bis die Einrichtung fertig ist"))
    c.add_argument("-y", "--yes", action="store_true", help=tr("Fehlende Software ohne Rückfrage installieren"))
    c.add_argument("--vpn-config", metavar="DATEI",
                   help=tr("WireGuard-Konfiguration (.conf) mitgeben – installiert Bony's VPN, die Datei geht nur in "
                           "den Agent-PC"))
    c.add_argument("--vpn-name", metavar="TUNNEL", help=tr("Name des Tunnels (Standard: Dateiname)"))
    c.add_argument("--vpn-autoconnect", action="store_true", help=tr("Tunnel bei jedem Start automatisch verbinden"))
    c.add_argument("--killswitch", action="store_true",
                   help=tr("Kill-Switch: ohne Tunnel kein Internet (Steuerung des Agent-PCs geht weiter)"))
    c.add_argument("--bony-netz", action="store_true",
                   help=tr("Beim ersten Start dem Bony-Netz beitreten (Bony-Netz an, Instanz angemeldet)"))
    c.set_defaults(func=cmd_create)

    tp = sub.add_parser("template", help=tr("Vorlagen: aus einem fertigen Agent-PC neue in Sekunden erstellen"))
    tsub = tp.add_subparsers(dest="template_cmd", required=True)
    tc = tsub.add_parser("create", help=tr("Vorlage aus einem fertig eingerichteten Agent-PC erstellen"))
    tc.add_argument("vm", metavar="AGENT-PC")
    tc.add_argument("name", metavar="NAME")
    tc.add_argument("--description", "-d", metavar="TEXT", help=tr("Beschreibung der Vorlage"))
    tc.add_argument("--keep-personal-data", action="store_true",
                    help=tr("Anmeldungen, API-Schlüssel usw. NICHT entfernen (Vorlage dann nicht weitergeben)"))
    tc.add_argument("--location", metavar="ORDNER", help=tr("Speicherort (Standard: der des Agent-PCs)"))
    tc.add_argument("--dry-run", action="store_true",
                    help=tr("Nur nachsehen, was gelöscht würde (startet eine Kopie, ändert nichts)"))
    tc.add_argument("-v", "--verbose", action="store_true", help=tr("Gelöschte Pfade anzeigen"))
    tc.add_argument("-y", "--yes", action="store_true", help=tr("Ohne Rückfrage (fährt den Agent-PC ggf. herunter)"))
    tc.set_defaults(func=cmd_template_create)
    tsub.add_parser("list", help=tr("Vorlagen anzeigen")).set_defaults(func=cmd_template_list)
    td = tsub.add_parser("delete", help=tr("Vorlage löschen (gesperrt, solange verknüpfte Agent-PCs existieren)"))
    td.add_argument("name")
    td.add_argument("--make-independent", action="store_true",
                    help=tr("Verknüpfte Agent-PCs vorher zu unabhängigen Kopien machen"))
    td.add_argument("-y", "--yes", action="store_true")
    td.set_defaults(func=cmd_template_delete)
    te = tsub.add_parser("export", help=tr("Vorlage zum Weitergeben als eine Datei (.bonys) speichern – mit "
                                           "Frisch-Prüfung, ohne nicht weitergebbare Programme"))
    te.add_argument("name")
    te.add_argument("file", metavar="DATEI", nargs="?",
                    help=tr("Zieldatei oder Ordner (Standard: Persönlicher Ordner, NAME-VERSION.bonys)"))
    te.add_argument("--creator", metavar="TEXT", help=tr("Ersteller (z. B. Name des Kursleiters)"))
    te.add_argument("--version", metavar="V", help=tr("Version der Vorlage (Standard: 1)"))
    te.add_argument("--preview", metavar="BILD", help=tr("Vorschaubild (PNG oder JPEG, höchstens 5 MB)"))
    te.add_argument("--clean", action="store_true",
                    help=tr("Funde der Frisch-Prüfung in der Export-Kopie bereinigen (die Vorlage bleibt unverändert)"))
    te.add_argument("-v", "--verbose", action="store_true", help=tr("Ausgabe aus der Export-Kopie anzeigen"))
    te.set_defaults(func=cmd_template_export)
    ti = tsub.add_parser("import", help=tr("Vorlage aus einer .bonys-Datei (oder .bonys-template) hinzufügen"))
    ti.add_argument("file", metavar="DATEI")
    _import_options(ti)
    ti.set_defaults(func=cmd_template_import)
    tren = tsub.add_parser("rename", help=tr("Vorlage umbenennen"))
    tren.add_argument("name")
    tren.add_argument("new_name", metavar="NEUER-NAME")
    tren.set_defaults(func=cmd_template_rename)
    tdesc = tsub.add_parser("describe", help=tr("Beschreibung ändern"))
    tdesc.add_argument("name")
    tdesc.add_argument("text")
    tdesc.set_defaults(func=cmd_template_describe)
    _course_commands(sub)
    jn = sub.add_parser("join", help=tr("Schulung beitreten: Vorlage vom Kursleiter laden und importieren "
                                        "(ohne Adresse: im Netz suchen)"))
    jn.add_argument("address", metavar="ADRESSE", nargs="?",
                    help=tr("z. B. 192.168.1.5:47110 oder der Link bonys://… (aus dem QR-Code)"))
    jn.add_argument("code", metavar="CODE", nargs="?", help=tr("Freigabe-Code, z. B. 4711-BONY"))
    jn.add_argument("--fingerprint", metavar="FP", help=tr("Fingerabdruck des Zertifikats (sonst Rückfrage)"))
    jn.add_argument("--dir", metavar="ORDNER", help=tr("Wohin laden (Standard: Datenordner/schulung)"))
    _import_options(jn)
    jn.set_defaults(func=cmd_join)
    wp = sub.add_parser("wallpaper", help=tr("Neues Standard-Hintergrundbild in einen laufenden Agent-PC bringen "
                                             "(nur, wenn noch das alte aktiv ist)"))
    wp.add_argument("name")
    wp.add_argument("--force", action="store_true", help=tr("Auch umstellen, wenn ein eigenes Bild gewählt ist"))
    wp.add_argument("--check", action="store_true", help=tr("Nur anzeigen, welches Bild aktiv ist"))
    wp.set_defaults(func=cmd_wallpaper)
    mi = sub.add_parser("make-independent", help=tr("Verknüpften Agent-PC in eine unabhängige Kopie umwandeln"))
    mi.add_argument("name")
    mi.set_defaults(func=cmd_make_independent)

    sub.add_parser("drives", help=tr("Laufwerke und freien Platz anzeigen")).set_defaults(func=cmd_drives)
    mv = sub.add_parser("move", help=tr("Agent-PC auf ein anderes Laufwerk/in einen anderen Ordner verschieben"))
    mv.add_argument("name")
    mv.add_argument("target", metavar="ORDNER")
    mv.set_defaults(func=cmd_move)
    im = sub.add_parser("import", help=tr("Vorhandene Agent-PCs (z. B. von einer SSD) hinzufügen"))
    im.add_argument("path", metavar="ORDNER")
    im.set_defaults(func=cmd_import)
    ins = sub.add_parser("install", help=tr("Apps nachträglich in einen laufenden Agent-PC installieren "
                                            "(Abhängigkeiten kommen mit; erneut aufrufen setzt nach Abbruch fort)"))
    ins.add_argument("name")
    ins.add_argument("apps", nargs="+", metavar="APP", help=f"z. B. {', '.join(apps.visible_ids())}")
    ins.set_defaults(func=cmd_install)
    mcp = sub.add_parser("mission-control", help=tr("Mission Control im Agent-PC: Status, öffnen, aktualisieren, "
                                                    "deinstallieren, Weiterleitung"),
                         description=tr("status | open | update [--version X] | uninstall [--purge] | forward on|off"))
    mcp.add_argument("name")
    mcp.add_argument("action", choices=["status", "open", "update", "uninstall", "forward"])
    mcp.add_argument("value", nargs="?", metavar="WERT", help=tr("bei forward: on oder off"))
    mcp.add_argument("--version", default="latest",
                     help=tr("bei update: Release, z. B. {VERSION} (Standard: latest = neuestes)",
                             VERSION=mission_control.VERSION))
    mcp.add_argument("--purge", action="store_true",
                     help=tr("bei uninstall: auch Einstellungen, Geheimnisse und Daten löschen (nicht umkehrbar)"))
    mcp.add_argument("-y", "--yes", action="store_true", help=tr("Ohne Rückfrage"))
    mcp.set_defaults(func=cmd_mission_control)
    vp = sub.add_parser("vpn", help=tr("Bony's VPN im laufenden Agent-PC: Status, verbinden, trennen, importieren"),
                        description=tr("status [--json] | up [TUNNEL] | down [TUNNEL] | import DATEI | "
                                       "killswitch on|off | autostart on|off | ip | update (VPN-App aktualisieren)"))
    vp.add_argument("name")
    vp.add_argument("action", choices=["status", "up", "down", "import", "killswitch", "autostart", "ip", "update"])
    vp.add_argument("value", nargs="?", metavar="WERT",
                    help=tr("import: die .conf-Datei · up/down: der Tunnel · killswitch/autostart: on oder off"))
    vp.add_argument("--tunnel", metavar="TUNNEL", help=tr("Tunnelname (bei import: statt des Dateinamens)"))
    vp.add_argument("--replace", action="store_true", help=tr("bei import: vorhandenen Tunnel ersetzen"))
    vp.add_argument("--json", action="store_true", help=tr("bei status: maschinenlesbar"))
    vp.set_defaults(func=cmd_vpn)
    rm = sub.add_parser("remote", help=tr("Fernzugriff (RDP aus dem Heimnetz) an/aus – wirkt sofort"))
    rm.add_argument("name")
    rm.add_argument("state", choices=["on", "off"])
    rm.add_argument("--permanent", action="store_true",
                    help=tr("Dauerhaft, auch nach Neustarts (sonst nur bis zum Herunterfahren)"))
    rm.set_defaults(func=cmd_remote)
    co = sub.add_parser("connect", help=tr("Verbindung öffnen (Remmina, Remotedesktop oder remote-viewer)"))
    co.add_argument("name")
    proto = co.add_mutually_exclusive_group()
    proto.add_argument("--rdp", action="store_true", help=tr("per RDP (Standard)"))
    proto.add_argument("--spice", action="store_true", help=tr("per SPICE"))
    co.set_defaults(func=cmd_connect)
    di = sub.add_parser("display", help=tr("Anzeige wählen: QEMU-Fenster oder SPICE-Fenster"))
    di.add_argument("name")
    di.add_argument("mode", choices=["qemu", "spice"])
    di.set_defaults(func=cmd_display)
    sc = sub.add_parser("screen", help=tr("Bildschirm: Auflösung folgt dem Fenster, Bild skalieren oder feste "
                                          "Auflösung"))
    sc.add_argument("name")
    sc.add_argument("mode", nargs="?", choices=list(screen.MODES),
                    help=tr("auto = folgt dem Fenster (Standard), scale = Bild skalieren, fixed = feste Auflösung"))
    sc.add_argument("--size", metavar="BxH", help=tr("Auflösung für scale/fixed, z. B. {DEFAULT_SIZE}",
                                                     DEFAULT_SIZE=screen.DEFAULT_SIZE))
    sc.set_defaults(func=cmd_screen)
    fs = sub.add_parser("fullscreen", help=tr("QEMU-Fenster in den Vollbildmodus schalten bzw. zurück (Strg+Alt+F)"))
    fs.add_argument("name")
    fs.set_defaults(func=cmd_fullscreen)
    dd = sub.add_parser("display-driver", help=tr("Anzeige-Treiber im laufenden Agent-PC einrichten/erneuern "
                                                  "(Auflösung folgt dem Fenster)"))
    dd.add_argument("name")
    dd.set_defaults(func=cmd_display_driver)
    rs = sub.add_parser("resize", help=tr("Festplatte eines Agent-PCs vergrößern (muss ausgeschaltet sein)"))
    rs.add_argument("name")
    rs.add_argument("size", type=_disk_gb, metavar="GRÖSSE", help=tr("Neue Größe in GB, z. B. 128"))
    rs.set_defaults(func=cmd_resize)
    rc = sub.add_parser("resources", help=tr("CPU-Kerne und Arbeitsspeicher anzeigen oder ändern (ohne Angaben: "
                                             "aktuelle Werte und Empfehlung)"))
    rc.add_argument("name")
    rc.add_argument("--cpus", type=int, metavar="N", help=tr("Anzahl CPU-Kerne"))
    rc.add_argument("--ram", type=_ram_gb, metavar="GB", help=tr("Arbeitsspeicher in GB, z. B. 6"))
    rc.add_argument("--restart", action="store_true", help=tr("Läuft der Agent-PC, ihn dafür neu starten"))
    rc.set_defaults(func=cmd_resources)
    dl = sub.add_parser("default-location", help=tr("Standard-Speicherort anzeigen oder ändern"))
    dl.add_argument("path", nargs="?", metavar="ORDNER")
    dl.add_argument("--reset", action="store_true", help=tr("Zurück zum Hauptsystem"))
    dl.set_defaults(func=cmd_default_location)

    for name, func, helptext in (
        ("start", cmd_start, "Agent-PC starten"),
        ("stop", cmd_stop, "Agent-PC herunterfahren"),
        ("status", cmd_status, "Details und Fortschritt anzeigen"),
        ("logs", cmd_logs, "Konsolenausgabe des Gasts anzeigen"),
        ("delete", cmd_delete, "Agent-PC löschen"),
    ):
        s = sub.add_parser(name, help=helptext)
        s.add_argument("name")
        s.set_defaults(func=func)
        if name == "start":
            s.add_argument("--headless", action="store_true")
            s.add_argument("--wait", action="store_true", help=tr("Bei laufender Einrichtung warten, bis sie fertig "
                                                                  "ist"))
        if name == "stop":
            s.add_argument("--force", action="store_true", help=tr("Sofort ausschalten"))
        if name == "logs":
            s.add_argument("-n", "--lines", type=int, default=100)
        if name == "delete":
            s.add_argument("-y", "--yes", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    procutil.add_homebrew_to_path()
    i18n.starten()   # vor build_parser: auch die Hilfetexte richten sich nach der Sprache
    args = build_parser().parse_args(argv)
    if not getattr(args, "func", None):
        # Ohne Befehl: Desktop-App öffnen (Doppelklick-Verhalten).
        return cmd_gui(args)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print(tr("\nAbgebrochen."))
        return 130
    except (ValueError, KeyError, FileExistsError, RuntimeError, qemu.QemuNotFound, OSError) as e:
        msg = e.args[0] if isinstance(e, KeyError) and e.args else e
        print(tr("Fehler: {msg}", msg=msg), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
