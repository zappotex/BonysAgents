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
    APP_NAME, __version__, apps, deps, desktops, edition, host, mission_control, n8n, procutil, qemu, remote,
    screen, netz, storage, vm, vpnlink,
)
from bonys_agents import progress as pct


REBOOT_REQUIRED = 3010  # wie bei Windows-Installern üblich


def _disk_gb(text: str) -> int:
    """argparse-Typ für Festplattengrößen: 32 bis 1024 GB."""
    try:
        gb = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{text}' ist keine Zahl (Größe in GB, z. B. 64)") from None
    try:
        vm.check_disk_gb(gb)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from None
    return gb


def _setup_line(machine: vm.VM, p: vm.Progress) -> str:
    """„42 % · Schritt 2/5 Cinnamon … · noch ca. 12 Min.“"""
    parts = [f"{p.percent:.0f} %"]
    if p.total:
        parts.append(f"Schritt {p.step}/{p.total} {p.title}")
    if p.resumed:
        parts.append("wird nach dem Neustart fortgesetzt")
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
    print(f"{edition.NAME} {__version__} (Edition: {edition.LABEL})")
    print(f"System:        {info.os} / {info.arch}")
    print(f"CPU-Kerne:     {info.cpus}")
    print(f"RAM:           {info.ram_mb} MB (für VMs nutzbar: {info.max_vm_ram_mb} MB)")
    accel_note = "" if info.accel_is_fast else "  ⚠ keine Hardware-Beschleunigung – VMs laufen sehr langsam"
    print(f"Beschleuniger: {info.accel}{accel_note}")
    if info.os == "macos":
        print(f"Mac:           {host.macos_chip_name(info.arch)}")
        if host.macos_rosetta():
            print("App-Version:   Intel (läuft per Rosetta) – besser die Version für Apple-Chip laden")
        brew = deps.find_brew(info.arch)
        print(f"Homebrew:      {'ja – ' + str(brew) if brew else 'nein (nötig für QEMU – siehe https://brew.sh)'}")
        print(f"HVF:           {'ja' if info.accel == 'hvf' else 'nein'}")
    ok = True
    for name in (qemu.ARCH_BINARY[info.arch], "qemu-img"):
        try:
            print(f"{name}: {qemu.find_binary(name, info.os)}")
        except qemu.QemuNotFound as e:
            ok = False
            print(f"{name}: FEHLT\n{e}")
    if ok and info.arch == "aarch64":
        try:
            fw = qemu.find_aarch64_firmware(qemu.find_binary(qemu.ARCH_BINARY[info.arch], info.os))
            print(f"UEFI-Firmware: {fw}")
        except qemu.QemuNotFound as e:
            ok = False
            print(e)
    print(f"Datenordner:   {vm.data_dir()}")
    old = storage.old_user_install()
    if old:
        print(f"⚠ Ältere Installation gefunden: {old}\n"
              "  Startmenü und Terminal starten womöglich diese alte Version statt der aktuellen.\n"
              f"  Entfernen mit: rm -rf {old} ~/.local/bin/bonys-agents"
              " ~/.local/share/applications/bonys-agents.desktop")
    report = deps.check(info)
    for issue in report.issues:
        print(f"⚠ {issue.text}")
    if report.ok:
        print("Alles bereit.")
    elif report.fixable:
        print("→ Automatisch beheben mit: bonys-agents setup")
    return 0 if report.ok else 1


def cmd_selftest(args) -> int:
    """QEMU auf demselben Weg wie die App starten und das Ergebnis klar melden."""
    from bonys_agents import selftest

    print(f"{APP_NAME} {__version__} – Selbsttest")

    def show(c) -> None:
        print(f"  {'OK    ' if c.ok else 'FEHLER'}  {c.name}")
        for line in (c.detail or "").splitlines():
            print(f"          {line}")

    results = selftest.run(log=show, include_qt=not args.no_qt, boot=args.boot)
    ok = selftest.passed(results)
    print("Ergebnis: OK – QEMU startet." if ok else "Ergebnis: FEHLER – siehe oben.")
    return 0 if ok else 1


def cmd_setup(args) -> int:
    """Installiert QEMU & Co. automatisch."""
    info = host.detect()
    report = deps.check(info)
    if report.ok:
        print("Alles ist bereits installiert und bereit.")
        return 0
    print("Folgendes wird eingerichtet:")
    for issue in report.fixable:
        print(f"  • {issue.text}")
    for issue in report.issues:
        if not issue.fixable:
            print(f"  ⚠ {issue.text} (muss von Hand behoben werden)")
    if report.fixable and not args.yes:
        if input("Jetzt automatisch einrichten? (ja/nein) ").strip().lower() not in ("j", "ja", "y", "yes"):
            print("Abgebrochen.")
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
        print("Abgebrochen. Homebrew lässt sich auch selbst installieren: https://brew.sh – danach: brew install qemu")
        return False
    return deps.run_homebrew_installer_here(info.arch) == 0


def _ensure_ready(assume_yes: bool) -> bool:
    report = deps.check()
    if report.can_run and not report.fixable:
        return True
    if report.fixable:
        print("Es fehlt noch etwas für die Agent-PCs:")
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
            raise ValueError("--vpn-autoconnect, --killswitch und --vpn-name gehen nur zusammen mit --vpn-config.")
        return None
    setup = vpnlink.load_conf(args.vpn_config, name=args.vpn_name, autoconnect=args.vpn_autoconnect,
                              killswitch=args.killswitch)
    extra = [x for x, on in (("verbindet sich automatisch", setup.autoconnect), ("Kill-Switch an", setup.killswitch))
             if on]
    print(f"WireGuard: Tunnel „{setup.name}“" + (f" ({', '.join(extra)})" if extra else "")
          + " – die Konfiguration geht nur über das Seed-ISO in den Agent-PC.")
    if setup.killswitch and not setup.autoconnect:
        print("⚠ Kill-Switch ohne automatisches Verbinden: Nach dem Start hat der Agent-PC kein Internet, "
              f"bis du verbindest (bonys-agents vpn {args.name} up).")
    return setup


def cmd_create(args) -> int:
    if args.template:
        return _create_from_template(args)
    if args.linked or args.full:
        print("--linked und --full gibt es nur zusammen mit --template.", file=sys.stderr)
        return 2
    app_ids = app_selection(args.apps, args.agents)  # Tippfehler melden, bevor nach dem Passwort gefragt wird
    vpn = vpn_setup(args)
    bony_netz = _bony_netz(args)
    desk = desktops.get(args.desktop)
    _warn_ram(desk.id, args.ram)
    _warn_mission_control(app_ids, desk.id, args.ram, args.disk or vm.DEFAULT_DISK_GB)
    if not _ensure_ready(args.yes):
        print("Agent-PC kann noch nicht erstellt werden – siehe oben.")
        return 1
    target = Path(args.location) if args.location else storage.preferred_library()
    chk = storage.check_location(target, args.disk or vm.DEFAULT_DISK_GB)
    for w in chk.warnings:
        print(f"⚠ {w}")
    if not chk.ok:
        print("Speicherort nicht geeignet: " + " ".join(chk.errors))
        return 1
    print(f"Speicherort: {target}")
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
        bony_netz=bony_netz,
    )
    _print_hints(machine)
    c = machine.config
    print(f"\nAgent-PC '{c.name}': {desktops.name(c.desktop)}, {c.cpus} CPUs, {c.ram_mb} MB RAM, {c.disk_gb} GB, "
          f"Apps: {', '.join(c.apps)}")
    if args.no_start:
        print(f"Starten mit: bonys-agents start {c.name}")
        return 0
    machine.start(headless=True if args.headless else None)  # Ersteinrichtung ohne Fenster
    print("Gestartet. Der Agent-PC richtet sich im Hintergrund ein – je nach Rechner 15–60 Minuten.")
    if args.wait:
        return _wait_ready(machine, headless=args.headless)
    print(f"Fortschritt: bonys-agents status {c.name}")
    return 0


def _bony_netz(args) -> bool:
    if args.bony_netz and not netz.bereit():
        raise ValueError("--bony-netz: Das Bony-Netz ist ausgeschaltet oder es ist keine Instanz angemeldet "
                         "(in der App: Menü → „Bony-Netz …“).")
    return bool(args.bony_netz)


def _print_hints(machine: vm.VM) -> None:
    for text in machine.hinweise:
        print(f"⚠ {text}")


def _warn_ram(desktop_id: str, ram_mb: int | None) -> None:
    ram = ram_mb or host.detect().default_vm_ram_mb
    warning = desktops.ram_warning(desktop_id, ram)
    if warning:
        print(f"⚠ {warning}")


def _warn_mission_control(app_ids: list[str] | None, desktop_id: str, ram_mb: int | None, disk_gb: int) -> None:
    ids = app_ids if app_ids is not None else apps.default_app_ids()
    if mission_control.APP_ID not in ids:
        return
    deps = apps.dependencies(ids)
    if deps:
        print(f"Wird mitinstalliert: {', '.join(apps.names(deps))}")
    ram = ram_mb or host.detect().default_vm_ram_mb
    for w in mission_control.resource_warnings(ids, ram, disk_gb, desktops.get(desktop_id).min_ram_mb,
                                               mission_control.requirements()):
        print(f"⚠ {w} (--ram/--disk)")


def _ask_password() -> str:
    password = ""
    while not password:
        password = getpass.getpass("Passwort für den Agent-PC: ")
        if password != getpass.getpass("Passwort wiederholen: "):
            print("Passwörter stimmen nicht überein.")
            password = ""
    return password


def _create_from_template(args) -> int:
    from bonys_agents import templates

    if args.desktop != desktops.DEFAULT:
        print("Bei --template kommt der Desktop aus der Vorlage – --desktop weglassen.", file=sys.stderr)
        return 2
    if args.apps or args.agents:
        print("Bei --template kommen die Programme aus der Vorlage – --apps/--agents weglassen "
              "(nachrüsten mit: bonys-agents install).", file=sys.stderr)
        return 2
    tpl = templates.get(args.template)
    vpn = vpn_setup(args)
    bony_netz = _bony_netz(args)
    if not _ensure_ready(args.yes):
        print("Agent-PC kann noch nicht erstellt werden – siehe oben.")
        return 1
    target = Path(args.location) if args.location else storage.preferred_library()
    linked = True if args.linked else False if args.full else None
    print(f"Vorlage: {tpl.name} – {templates.describe(tpl)}")
    _warn_ram(tpl.desktop, args.ram)
    print(f"Speicherort: {target}")
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
    kind = "verknüpft mit" if machine.is_linked() else "unabhängige Kopie von"
    print(f"Agent-PC '{c.name}' ({kind} „{tpl.name}“): {c.cpus} CPUs, {c.ram_mb} MB RAM, {c.disk_gb} GB, "
          f"Apps: {', '.join(c.apps)}")
    if args.no_start:
        print(f"Starten mit: bonys-agents start {c.name}")
        return 0
    machine.start(headless=True if args.headless else None)
    print("Gestartet – erster Start mit neuem Rechnernamen und Passwort.")
    if args.wait:
        rc = _wait_ready(machine, headless=args.headless)
        if rc == 0:
            print(f"Bereit nach {time.monotonic() - t0:.0f} s (ab Beginn des Anlegens).")
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
            print("\nFertig eingerichtet.")
            return 0
        if not running:
            if machine.finish_first_boot(headless=headless):
                print("\nFertig eingerichtet – der Agent-PC startet jetzt mit Desktop.")
                return 0
            print(f"\n{vm.STATUS_ABORTED}: Der Agent-PC wurde beendet, bevor die Einrichtung fertig war.\n"
                  f"Ursache: {machine.abort_reason().text()}\n"
                  f"Fortsetzen mit: bonys-agents start {machine.name}")
            return 1
        eta = pct.format_eta(machine.eta_seconds(p.percent))
        print(f"\r{_bar(p.percent / 100)} {p.title[:32]:32} {eta:18}", end="", flush=True)
        time.sleep(poll)


def cmd_list(args) -> int:
    entries = vm.list_all()
    if not entries:
        print("Noch keine Agent-PCs. Anlegen mit: bonys-agents create <name>")
        return 0
    print(f"{'NAME':20} {'STATUS':18} {'DESKTOP':11} {'CPU':>4} {'RAM':>8} {'DISK':>6}  SPEICHERORT")
    for e in entries:
        if isinstance(e, vm.MissingVM):
            print(f"{e.name:20} {e.status():18} {'':11} {'':>4} {'':>8} {'':>6}  {e.path.parent}")
            continue
        c = e.config
        print(f"{c.name:20} {e.status():18} {desktops.name(c.desktop):11} {c.cpus:>4} {c.ram_mb:>6}MB "
              f"{c.disk_gb:>4}GB  {e.location}"
              + (f"  (verknüpft: {c.template or e.backing_file()})" if e.is_linked() else ""))
    return 0


def cmd_drives(args) -> int:
    print(f"{'LAUFWERK':44} {'TYP':8} {'FREI':>9}  VORSCHLAG FÜR --location")
    for d in storage.drives():
        tag = " (Hauptsystem)" if d.system else (" (wechselbar)" if d.removable else "")
        note = "  ✕ FAT32 – keine Dateien > 4 GB" if d.is_fat else ""
        print(f"{(d.label + tag)[:44]:44} {d.fstype[:8]:8} {d.free / storage.GB:>7.0f}GB  {d.library}{note}")
    print(f"\nStandard-Speicherort: {storage.preferred_library()}")
    return 0


def cmd_move(args) -> int:
    def progress(phase: str, frac: float, msg: str) -> None:
        print(f"\r{_bar(frac)} {msg[:40]:40}", end="", flush=True)

    moved = vm.move(args.name, Path(args.target), progress=progress)
    print(f"\n'{args.name}' liegt jetzt in {moved.path}")
    return 0


def cmd_import(args) -> int:
    added = vm.import_path(Path(args.path))
    for m in added:
        print(f"Hinzugefügt: {m.name}  ({m.path})")
    return 0


def cmd_default_location(args) -> int:
    if args.path:
        p = Path(args.path)
        chk = storage.check_location(p, vm.DEFAULT_DISK_GB, create=True)
        if not chk.ok:
            print("Nicht geeignet: " + " ".join(chk.errors))
            return 1
        storage.set_preferred_library(p)
    elif args.reset:
        storage.set_preferred_library(None)
    print(f"Standard-Speicherort: {storage.preferred_library()}")
    return 0


def cmd_start(args) -> int:
    m = vm.get(args.name)
    m.start(headless=True if args.headless else None)
    if m.config.first_boot_pending:
        step = f" (zuletzt bei Schritt {m.config.setup_step})" if m.config.setup_step else ""
        print(f"'{args.name}' gestartet – die Einrichtung läuft im Hintergrund weiter{step}.")
        if args.wait:
            return _wait_ready(m, headless=args.headless)
    else:
        print(f"'{args.name}' gestartet.")
    return 0


def _ram_gb(text: str) -> int:
    """argparse-Typ für Arbeitsspeicher in GB (auch 5,5 oder 5.5) – Ergebnis in MB, auf 512 MB gerundet."""
    try:
        gb = float(text.replace(",", "."))
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{text}' ist keine Zahl (Arbeitsspeicher in GB, z. B. 6)") from None
    return round(gb * 2) * 512


def cmd_resources(args) -> int:
    m = vm.get(args.name)
    c = m.config
    recommended = min(m.recommended_ram_mb(), host.detect().max_vm_ram_mb)
    if args.cpus is None and args.ram is None:
        print(f"'{m.name}': {c.cpus} Kerne, {desktops.format_ram(c.ram_mb)} RAM "
              f"(empfohlen: {desktops.format_ram(recommended)}).")
        return 0
    cpus = c.cpus if args.cpus is None else args.cpus
    ram_mb = c.ram_mb if args.ram is None else args.ram
    running = m.is_running()
    if running and not args.restart:
        print(f"'{m.name}' läuft – zuerst herunterfahren oder mit --restart neu starten lassen.", file=sys.stderr)
        return 1
    if running:
        print(f"'{m.name}' wird heruntergefahren …")
        m.stop()
    m.set_resources(cpus, ram_mb)
    print(f"'{m.name}': {cpus} Kerne, {desktops.format_ram(ram_mb)} RAM.")
    if ram_mb < recommended:
        print(f"⚠ Weniger als empfohlen ({desktops.format_ram(recommended)}) – mit Browser, Docker und Agent "
              "gleichzeitig kann es eng werden.")
    if running:
        m.start()
        print(f"'{m.name}' neu gestartet.")
    else:
        print("Gilt ab dem nächsten Start.")
    return 0


def cmd_resize(args) -> int:
    m = vm.get(args.name)
    old = m.config.disk_gb
    m.resize(args.size)
    print(f"Festplatte von '{m.name}': {vm.format_gb(old)} → {vm.format_gb(args.size)}.\n"
          "Der Agent-PC nutzt den neuen Platz automatisch beim nächsten Start.")
    return 0


def cmd_stop(args) -> int:
    m = vm.get(args.name)
    if not m.is_running():
        print(f"'{args.name}' läuft nicht.")
        return 0
    if not args.force:
        print(f"'{args.name}' wird heruntergefahren … (spätestens nach {vm.STOP_TIMEOUT} s wird hart ausgeschaltet)")
    if m.stop(force=args.force) and not args.force:
        print(f"'{args.name}' hat nicht reagiert und wurde hart ausgeschaltet.")
    else:
        print(f"'{args.name}' gestoppt.")
    return 0


def cmd_status(args) -> int:
    m = vm.get(args.name)
    c = m.config
    print(f"Name:    {c.name}\nStatus:  {m.status()}\nCPU/RAM: {c.cpus} / {c.ram_mb} MB\nDisk:    {c.disk_gb} GB")
    print(f"Benutzer: {c.username}\nDesktop: {desktops.name(c.desktop)}"
          + (f" (weitere: {', '.join(desktops.name(d) for d in c.extra_desktops)})" if c.extra_desktops else ""))
    shown = [a + (f" {(c.app_info.get(a) or {}).get('version')}" if (c.app_info.get(a) or {}).get("version") else "")
             for a in c.apps]
    print(f"Apps:    {', '.join(shown)}\nOrdner:  {m.path}")
    if c.setup_failed:
        print(f"Einrichtung mit Fehlern: {', '.join(c.setup_failed)} – fehlende Programme nachinstallieren mit "
              f"„bonys-agents install {c.name} APP“, Einzelheiten: bonys-agents logs {c.name}")
    if m.is_linked():
        print(f"Vorlage: {c.template or '?'} (verknüpft: {m.backing_file()})")
    elif c.template:
        print(f"Vorlage: {c.template} (unabhängige Kopie)")
    d = storage.drive_for(m.path)
    if d:
        print(f"Laufwerk: {d.describe()}")
    if m.is_running():
        rt = m.runtime()
        p = m.progress()
        if not p.ready or c.first_boot_pending:
            print(f"Einrichtung: {_setup_line(m, p)}")
        print(f"SSH:     ssh -p {rt.get('ssh_port')} {c.username}@127.0.0.1")
    elif m.status() == vm.STATUS_ABORTED:
        print(f"Ursache: {m.abort_reason().text()}")
        print(f"Fortsetzen mit: bonys-agents start {c.name}")
    _print_remote(m)
    return 0


def remote_state_text(r: dict) -> str:
    if r["active"]:
        return "an (dauerhaft)" if r["permanent"] else "an (bis zum Herunterfahren)"
    return "aus (wird beim nächsten Start dauerhaft eingeschaltet)" if r["permanent"] else "aus"


def _print_remote(m: vm.VM) -> None:
    r = m.remote_info()
    print(f"Fernzugriff: {remote_state_text(r)}")
    if r["spice_local"]:
        where = "aus dem Heimnetz (mit Passwort)" if r["spice_lan"] else "nur an diesem Rechner"
        print(f"  SPICE {r['spice_local']} – {where}")
    if not r["active"]:
        if not r["rdp_installed"]:
            print("  RDP: xrdp fehlt im Agent-PC (bonys-agents install NAME xrdp)")
        return
    for addr in r["addresses"] or ["(keine Heimnetz-Adresse gefunden)"]:
        spice = f"  ·  SPICE spice://{addr}:{r['spice_port']}" if r["spice_lan"] else ""
        print(f"  RDP {addr}:{r['rdp_port']}{spice}")
    print(f"  Benutzer: {r['username']} (Passwort des Agent-PCs)")
    if r["spice_password"]:
        print(f"  SPICE-Passwort: {r['spice_password']}")
    if r["needs_restart"]:
        print("  Hinweis: SPICE aus dem Heimnetz erst nach einem Neustart des Agent-PCs – RDP geht sofort.")
    print(f"  {remote.LAN_WARNING}")


def cmd_remote(args) -> int:
    m = vm.get(args.name)
    on = args.state == "on"
    if m.is_running() and on:
        print("Schalte xrdp im Agent-PC ein … (ohne Gast-Agent fragt ssh nach dem Passwort des Agent-PCs)")
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
    print(f"Verbindung zu '{m.name}' wird geöffnet …")
    return 0


def cmd_display(args) -> int:
    m = vm.get(args.name)
    m.set_display(args.mode)
    label = "SPICE-Fenster" if args.mode == "spice" else "QEMU-Fenster"
    print(f"Anzeige von '{m.name}': {label} (ab dem nächsten Start).")
    return 0


def cmd_screen(args) -> int:
    m = vm.get(args.name)
    if args.mode is None and args.size is None:
        print(f"Bildschirm von '{m.name}': {screen.label(*m.screen_settings())}")
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
    print(f"Richte den Anzeige-Treiber in '{m.name}' ein … (ohne Gast-Agent fragt ssh nach dem Passwort)",
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
            print("Abgebrochen.")
            return 1
    hint = netz.loeschen_hinweis(m) if m.template_lock_pid() is None else ""
    m.delete()
    print(f"'{args.name}' gelöscht.")
    if hint:
        print(f"⚠ {hint}")
    return 0


def cmd_desktops(args) -> int:
    print(f"{'ID':10} {'NAME':12} {'RAM AB':>7}  BESCHREIBUNG")
    for d in desktops.DESKTOPS.values():
        std = "  [Standard]" if d.id == desktops.DEFAULT else ""
        print(f"{d.id:10} {d.name:12} {desktops.format_ram(d.min_ram_mb):>7}  {d.description}{std}")
    return 0


def cmd_add_desktop(args) -> int:
    m = vm.get(args.name)
    spec = desktops.get(args.desktop)
    print(f"Installiere {spec.name} in „{m.name}“ per SSH – ssh fragt ggf. nach dem Passwort des Agent-PCs.")
    m.install_desktop(spec.id, make_default=not args.keep_default)
    if args.keep_default:
        print(f"Fertig: {spec.name} ist installiert und am Anmeldebildschirm wählbar.")
    else:
        print(f"Fertig: Ab dem nächsten Start meldet sich „{m.name}“ automatisch in {spec.name} an.")
    return 0


def _app_line(a: apps.AppSpec, extra: str = "") -> str:
    deps = apps.dependencies([a.id])
    note = f"  (bringt {', '.join(apps.names(deps))} mit)" if deps else ""
    return f"  {a.id:16} {a.name:22} {a.description}{note}{extra}"


def cmd_apps(args) -> int:
    if getattr(args, "name", None):
        return _apps_of(vm.get(args.name))
    for title, cat in (("Programme", apps.PROGRAM), ("KI-Werkzeuge (--agents)", apps.AGENT)):
        print(f"{title}:")
        for a in apps.APPS.values():
            if a.category == cat and not a.hidden:
                print(_app_line(a, "  [Standard]" if a.default else ""))
    hidden = [a.name for a in apps.APPS.values() if a.hidden]
    if hidden:
        print(f"\nBausteine, die bei Bedarf automatisch mitkommen: {', '.join(hidden)}")
    print(f"\nMission Control: {mission_control.requirement_note()}.")
    return 0


def _apps_of(m: vm.VM) -> int:
    c = m.config
    print(f"Installiert in „{m.name}“:")
    for app_id in c.apps:
        info = c.app_info.get(app_id) or {}
        ver = f"  Version {info['version']}" if info.get("version") else ""
        name = apps.APPS[app_id].name if app_id in apps.APPS else app_id
        print(f"  {app_id:16} {name}{ver}")
    missing = m.missing_apps()
    if missing:
        print("\nVerfügbar (bonys-agents install NAME APP …):")
        for a in missing:
            print(_app_line(a))
    else:
        print("\nAlle verfügbaren Apps sind installiert.")
    return 0


def app_selection(apps_arg: str | None, agents_arg: str | None) -> list[str] | None:
    """--apps und --agents zu einer App-Liste zusammenführen (None = Standard).

    --agents ersetzt nur die KI-Werkzeuge; „none“ bzw. leer = keins.
    """
    if apps_arg is None and agents_arg is None:
        return None
    ids = [i.strip() for i in (apps_arg.split(",") if apps_arg else apps.default_app_ids()) if i.strip()]
    if agents_arg is not None:
        agents = [i.strip() for i in agents_arg.split(",") if i.strip() and i.strip().lower() not in ("none", "keins")]
        wrong = [i for i in agents if i in apps.APPS and apps.APPS[i].category != apps.AGENT]
        if wrong:
            raise ValueError(f"--agents ist nur für KI-Werkzeuge ({', '.join(apps.ids_in_category(apps.AGENT))}); "
                             f"{', '.join(wrong)} bitte über --apps angeben.")
        agent_ids = set(apps.ids_in_category(apps.AGENT))
        ids = [i for i in ids if i not in agent_ids] + agents
    apps.resolve(ids)  # unbekannte IDs früh melden
    return ids


def cmd_install(args) -> int:
    m = vm.get(args.name)
    plan = m.install_plan(args.apps)
    if not plan:
        print(f"Schon installiert: {', '.join(apps.names(args.apps))}.")
        return 0
    deps = [i for i in plan if i not in args.apps]
    print(f"Installiere in „{m.name}“: {', '.join(apps.names(plan))}"
          + (f" ({', '.join(apps.names(deps))} wird mitinstalliert)" if deps else ""))
    if mission_control.APP_ID in plan:
        for w in mission_control.resource_warnings(plan, m.config.ram_mb, m.config.disk_gb,
                                                   desktops.get(m.config.desktop).min_ram_mb,
                                                   mission_control.requirements()):
            print(f"⚠ {w}")
    print("Ohne Gast-Agent fragt ssh nach dem Passwort des Agent-PCs. Bricht etwas ab: denselben Befehl erneut "
          "ausführen – fertige Programme werden übersprungen.")

    def step(n: int, total: int, app_id: str) -> None:
        print(f"==> ({n}/{total}) {apps.APPS[app_id].name}")

    m.install_apps(args.apps, ssh_prompt=True, log=print, step=step)
    print(f"Fertig: {', '.join(apps.names(plan))} installiert. Die Symbole liegen auf dem Schreibtisch des Agent-PCs.")
    return 0


def cmd_mission_control(args) -> int:
    m = vm.get(args.name)
    mc = mission_control
    kw = {"ssh_prompt": True}
    if args.action == "status":
        if mc.APP_ID not in m.config.apps:
            print(f"{mc.NAME} ist in „{m.name}“ nicht installiert (bonys-agents install {m.name} {mc.APP_ID}).")
            return 1
        st = mc.status(m, **kw) if m.is_running() else None
        print(f"{mc.NAME}: " + (mc.status_text(st) if st else "Agent-PC läuft nicht"))
        if st and st.get("installed"):
            print(f"  Adresse im Agent-PC: http://127.0.0.1:{st.get('port', mc.PORT)}/")
        if m.config.mc_forward:
            print(f"  Weiterleitung an diesen Rechner: {mc.forward_url(m)} (nur 127.0.0.1)")
        return 0 if st is None or st.get("healthy") else 1
    if args.action == "open":
        print(mc.open_in_guest(m, **kw))
    elif args.action == "update":
        print(f"Aktualisiere {mc.NAME} auf {args.version} … (Einstellungen, Geheimnisse und Daten bleiben)")
        print(mc.update(m, version=args.version, log=print, **kw))
    elif args.action == "uninstall":
        if args.purge and not _yes(f"Wirklich ALLE Daten und Einstellungen von {mc.NAME} in „{m.name}“ löschen? "
                                   "Das lässt sich nicht rückgängig machen.", args.yes):
            print("Abgebrochen.")
            return 1
        print(mc.uninstall(m, purge=args.purge, log=print, **kw))
    elif args.action == "forward":
        if args.value not in ("on", "off"):
            print("Bitte „forward on“ oder „forward off“ angeben.", file=sys.stderr)
            return 2
        if args.value == "on":
            print(f"⚠ {mc.FORWARD_WARNING}")
            if not _yes("Weiterleitung einschalten?", args.yes):
                print("Abgebrochen.")
                return 1
        print(mc.set_forward(m, args.value == "on", **kw))
    return 0


def _print_vpn(st: dict, name: str = "NAME") -> None:
    print(vpnlink.summary(st))
    if st.get("compat") in vpnlink.COMPAT_TEXT:
        print(f"  ⚠ {vpnlink.COMPAT_TEXT[st['compat']]}")
        if st["compat"] in ("legacy", "outdated"):
            print(f"    → bonys-agents vpn {name} update")
    for t in st.get("tunnels") or []:
        flags = [x for x, on in (("verbunden", t.get("active")), ("automatisch", t.get("autostart"))) if on]
        line = f"  {t['name']}" + (f"  [{', '.join(flags)}]" if flags else "")
        if t.get("active"):
            line += (f"  · Handshake {vpnlink.human_age(t.get('handshake'))}"
                     f"  · empfangen {vpnlink.human_bytes(t.get('rx'))}, gesendet {vpnlink.human_bytes(t.get('tx'))}")
        print(line)
    ks = st.get("killswitch") or {}
    if ks.get("exceptions"):
        print(f"  Kill-Switch-Ausnahmen: {', '.join(ks['exceptions'])}")


def cmd_vpn(args) -> int:
    m = vm.get(args.name)
    kw = {"ssh_prompt": True}  # ohne Gast-Agent: ssh fragt im Terminal nach dem Passwort
    value = args.value
    if args.action == "import":
        if not value:
            raise ValueError("Datei fehlt: bonys-agents vpn NAME import DATEI.conf")
        setup = vpnlink.load_conf(value, name=args.tunnel)
        vpnlink.import_conf(m, setup, replace=args.replace, **kw)
        print(f"„{setup.name}“ ist in „{m.name}“ importiert. Verbinden mit: bonys-agents vpn {m.name} up")
        return 0
    if args.action == "update":
        if value:
            raise ValueError("„update“ erwartet keine weitere Angabe.")
        print(f"Installiere das neueste Bony's VPN aus dem offiziellen Release ({vpnlink.VPN_REPO_URL}) in "
              f"„{m.name}“ – Signatur und Prüfsumme werden geprüft, Tunnel und Kill-Switch bleiben …")
        vpnlink.update_app(m, log=print, **kw)
        st = vpnlink.status(m, **kw)
        print(f"Fertig: Bony's VPN {st.get('version', '')} ist installiert.")
        return 0
    if value and args.action in ("status", "ip"):
        raise ValueError(f"„{args.action}“ erwartet keine weitere Angabe.")
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
            raise ValueError("Welcher Tunnel? bonys-agents vpn NAME up TUNNEL (siehe: vpn NAME status)")
        vpnlink.up(m, tunnel, **kw)
        print(f"„{tunnel}“ ist verbunden.")
    elif args.action == "down":
        vpnlink.down(m, tunnel, **kw)
        print("Getrennt.")
    elif args.action == "killswitch":
        if state not in ("on", "off"):
            raise ValueError("bonys-agents vpn NAME killswitch on|off")
        vpnlink.set_killswitch(m, state == "on", **kw)
        print("Kill-Switch: " + ("an – ohne Tunnel kein Internet (Steuerung des Agent-PCs geht weiter)"
                                 if state == "on" else "aus"))
    elif args.action == "autostart":
        tunnel = tunnel or vpnlink.default_tunnel(vpnlink.status(m, **kw))
        if state not in ("on", "off") or not tunnel:
            raise ValueError("bonys-agents vpn NAME autostart on|off [--tunnel TUNNEL]")
        vpnlink.set_autostart(m, tunnel, state == "on", **kw)
        print(f"„{tunnel}“ verbindet sich {'beim Start automatisch' if state == 'on' else 'nicht automatisch'}.")
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
        print(f"Keine Updates gefunden – {APP_NAME} {__version__} ist aktuell.")
        return 0
    print(f"Version {info.version} ist verfügbar (installiert: {__version__}).")
    if info.html_url:
        print(f"Was ist neu: {info.html_url}")
    if args.check:
        return 0
    h = host.detect()
    if not updates.can_self_update(h.os):
        print(f"Bitte die neue Version von der Release-Seite laden: {info.html_url or updates.release_page()}")
        return 0
    if not _yes(f"Jetzt auf {info.version} aktualisieren?", args.yes):
        print("Abgebrochen – es wurde nichts installiert.")
        return 1
    if h.os == "macos":
        try:
            dmg = updates.install_macos(info, h.arch, log=print)
        except updates.UpdateError as e:
            print(f"Fehler: {e}", file=sys.stderr)
            return 1
        print(f"Im Finder-Fenster „{APP_NAME}“ auf „Programme“ ziehen und „Ersetzen“ wählen ({dmg}).")
        return 0
    running = [m for m in vm.list_vms() if m.is_running()]
    if running:
        names = ", ".join(m.name for m in running)
        print(f"Laufende Agent-PCs: {names}. Sie laufen beim Update weiter, die App startet aber neu.")
        if not args.yes and _yes("Vorher herunterfahren?"):
            for m in running:
                print(f"Fahre „{m.name}“ herunter …")
                m.stop()
    try:
        if h.os == "linux":
            updates.install_linux(info, h.arch, gui=False, log=print)
            print(f"Fertig: {APP_NAME} {info.version} ist installiert. Offene Fenster der App bitte neu starten.")
        else:
            updates.install_windows(info, log=print)
            print("Der Installer läuft – er startet die App danach neu.")
    except updates.UpdateError as e:
        print(f"Fehler: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_upgrade(args) -> int:
    """Agent-PCs aktualisieren (System, Flatpaks, KI-Werkzeuge)."""
    if args.all:
        machines = [m for m in vm.list_vms() if m.is_running() and m.status() == "läuft"]
        if not machines:
            print("Kein laufender, fertig eingerichteter Agent-PC.")
            return 0
    elif args.name:
        machines = [vm.get(args.name)]
    else:
        print("Bitte einen Namen angeben oder --all.", file=sys.stderr)
        return 2
    failed = 0
    for m in machines:
        print(f"==> Aktualisiere „{m.name}“ … (ohne Gast-Agent fragt ssh nach dem Passwort des Agent-PCs)",
              flush=True)
        try:
            result = m.upgrade(ssh_prompt=True, log=lambda line: print(line, flush=True))
        except RuntimeError as e:
            print(f"Fehler bei „{m.name}“: {e}", file=sys.stderr)
            failed += 1
            continue
        print(result.message(m.name))
        if result.reboot_required:
            print(f"   Neustart: bonys-agents stop {m.name} && bonys-agents start {m.name}")
        failed += 0 if result.ok else 1
    return 1 if failed else 0


def _template_progress(phase: str, frac: float, msg: str) -> None:
    print(f"\r{_bar(frac)} {msg[:60]:60}", end="", flush=True)


def cmd_template_create(args) -> int:
    from bonys_agents import cloudinit, templates

    m = vm.get(args.vm)
    remove = not args.keep_personal_data
    print(f"Vorlage „{args.name}“ aus „{m.name}“. Das Original bleibt unverändert: Verallgemeinert wird eine "
          "Kopie seiner Festplatte (ohne Netz).\n")
    print("In der Vorlage wird gelöscht bzw. zurückgesetzt:")
    if remove:
        print(f"  • {vpnlink.FRESH_CLEANUP}")
        print(f"  • {mission_control.FRESH_CLEANUP}")
        if n8n.APP_ID in m.config.apps:
            print(f"  • {n8n.FRESH_CLEANUP}")
        for item in cloudinit.PERSONAL_DATA:
            print(f"  • {item.title}")
            for path in item.paths:
                print(f"      /home/{m.config.username}/{path}{item.note()}")
    else:
        print("  • Persönliche Daten bleiben ERHALTEN (--keep-personal-data) – Vorlage nicht weitergeben!")
        if vpnlink.APP_ID in m.config.apps:
            print(f"  ⚠ {vpnlink.CLONE_WARNING}")
        if mission_control.APP_ID in m.config.apps:
            print(f"  ⚠ {mission_control.CLONE_NOTE}")
    for line in cloudinit.SYSTEM_CLEANUP:
        print(f"  • {line}")
    print()
    if m.is_running():
        if not _yes(f"„{m.name}“ läuft. Jetzt herunterfahren?", args.yes):
            print("Abgebrochen.")
            return 1
        print(f"Fahre „{m.name}“ herunter …")
        m.stop()
    if args.dry_run:
        print("Probelauf: Arbeitskopie startet und sieht nach, was es im Agent-PC tatsächlich gibt …")
        out = templates.preview(m.name, remove, progress=_template_progress)
        print("\n" + out)
        return 0
    if not _yes("Vorlage jetzt erstellen?", args.yes):
        print("Abgebrochen.")
        return 1
    t0 = time.monotonic()
    tpl = templates.create(m.name, args.name, args.description or "", remove_personal=remove,
                           location=Path(args.location) if args.location else None,
                           progress=_template_progress,
                           log=(lambda line: print("\n  " + line, end="")) if args.verbose else None)
    print(f"\nVorlage „{tpl.name}“ erstellt in {time.monotonic() - t0:.0f} s: {tpl.path} "
          f"({tpl.size / storage.GB:.1f} GB)")
    print(f"Neuer Agent-PC daraus: bonys-agents create NAME --template {tpl.name}")
    return 0


def cmd_template_list(args) -> int:
    from bonys_agents import templates

    items = templates.list_templates()
    if not items:
        print("Noch keine Vorlagen. Erstellen mit: bonys-agents template create AGENT-PC NAME")
        return 0
    print(f"{'NAME':24} {'GRÖSSE':>8} {'ERSTELLT':17} {'VERKNÜPFT':>9}  SPEICHERORT")
    for t in items:
        print(f"{t.name:24} {t.size / storage.GB:>6.1f}GB {t.created_local():17} {len(t.linked_vms()):>9}  "
              f"{t.library}")
        extra = [t.description] if t.description else []
        extra.append(f"aus {t.source}, Debian {t.debian or '?'}, {t.arch}, Apps: {', '.join(apps.names(t.apps))}"
                     + ("" if t.personal_data_removed else ", MIT persönlichen Daten"))
        for line in extra:
            print(f"    {line}")
    return 0


def cmd_template_delete(args) -> int:
    from bonys_agents import templates

    t = templates.get(args.name)
    linked = t.linked_vms()
    if linked:
        names = ", ".join(m.name for m in linked)
        print(f"Verknüpfte Agent-PCs bauen auf „{t.name}“ auf: {names}")
        if not args.make_independent:
            print("Löschen gesperrt. Erst mit --make-independent zu unabhängigen Kopien machen.", file=sys.stderr)
            return 1
        for m in linked:
            if m.is_running():
                print(f"„{m.name}“ läuft – bitte erst herunterfahren.", file=sys.stderr)
                return 1
        for m in linked:
            print(f"Mache „{m.name}“ unabhängig …")
            m.make_independent(progress=lambda f: print(f"\r{_bar(f)}", end="", flush=True))
            print()
    if not _yes(f"Vorlage „{t.name}“ ({t.size / storage.GB:.1f} GB) löschen?", args.yes):
        print("Abgebrochen.")
        return 1
    templates.delete(t.name)
    print(f"Vorlage „{t.name}“ gelöscht.")
    return 0


def cmd_template_export(args) -> int:
    from bonys_agents import bonysfile, templates

    t = templates.get(args.name)
    removed = apps.not_redistributable(t.apps)
    print(f"Export von „{t.name}“ als .bonys-Datei. Die Vorlage bleibt unverändert: Geprüft und bereinigt wird "
          "eine Kopie (ohne Netz).")
    if removed:
        print(f"Nicht frei weitergebbar, wird aus der Kopie entfernt: {', '.join(apps.names(removed))} – der "
              "Empfänger installiert es aus der offiziellen Quelle neu.")
    if not t.personal_data_removed and not args.clean:
        print("Diese Vorlage enthält persönliche Daten (Klon). Export nur „frisch gemacht“: mit --clean werden die "
              "persönlichen Daten in der Export-Kopie entfernt.", file=sys.stderr)
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
            print("\nBereinigen (nur in der Export-Kopie, die Vorlage bleibt): erneut mit --clean.", file=sys.stderr)
        return 1
    print(f"\nExportiert: {out} ({out.stat().st_size / storage.GB:.2f} GB)")
    print(bonysfile.describe_manifest(bonysfile.read_manifest(out)))
    return 0


def cmd_template_import(args) -> int:
    from bonys_agents import bonysfile

    file = Path(args.file)
    if not bonysfile.is_bonys(file):
        if args.recipe or args.create:
            print("--create/--recipe gibt es nur für .bonys-Dateien.", file=sys.stderr)
            return 2
        t = bonysfile.import_any(file, location=Path(args.location) if args.location else None, name=args.name,
                                 progress=_template_progress)
        print(f"\nVorlage „{t.name}“ importiert (altes Format): {t.path}")
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
        print("⚠ " + bonysfile.SLOW_ARCH_WARNING.format(tpl=m["arch"], host=bonysfile.arch_name(host_arch)))
        print(f"   Rezept: bonys-agents template import {file} --recipe NAME")
        if args.create and not args.foreign_arch:
            print("Trotzdem aus der Vorlage erstellen: --foreign-arch", file=sys.stderr)
            return 1
    password = None
    if args.create:
        if any(m2.name == args.create for m2 in vm.list_all()):
            raise FileExistsError(f"Agent-PC '{args.create}' existiert bereits")
        password = args.password or _ask_password()
    t = bonysfile.import_bundle(file, location=Path(args.location) if args.location else None, name=args.name,
                                progress=_template_progress)
    print(f"\nVorlage „{t.name}“ importiert (Prüfsumme stimmt): {t.path}")
    if not args.create:
        print(f"Neuer Agent-PC daraus: bonys-agents create NAME --template {t.name}")
        _print_reinstall_hint("NAME", t.reinstall)
        return 0
    rec = m.get("recommended", {})
    machine = vm.create(args.create, password, template=t.name, cpus=args.cpus or rec.get("cpus"),
                        ram_mb=args.ram or rec.get("ram_mb"), linked=False if args.full else None,
                        location=Path(args.vm_location) if args.vm_location else None,
                        foreign_arch=args.foreign_arch,
                        progress=lambda phase, frac, msg: print(f"\r{_bar(frac)} {msg[:50]:50}", end="", flush=True))
    c = machine.config
    print(f"\nAgent-PC '{c.name}' aus „{t.name}“: {c.cpus} CPUs, {c.ram_mb} MB RAM, {c.disk_gb} GB")
    print("Beim ersten Start bekommt er eine neue Maschinen-ID, neue SSH-Hostschlüssel und neue Geheimnisse.")
    print(f"Starten mit: bonys-agents start {c.name}")
    _print_reinstall_hint(c.name, t.reinstall)
    return 0


def _print_reinstall_hint(vm_name: str, ids: list[str]) -> None:
    ids = [i for i in ids if i in apps.APPS]
    if ids:
        print(f"Nicht mitgeliefert (Lizenz): {', '.join(apps.names(ids))}. Aus der offiziellen Quelle installieren, "
              f"wenn der Agent-PC läuft: bonys-agents install {vm_name} {' '.join(ids)}")


def _create_from_recipe(args, m: dict) -> int:
    """Rezept: dieselbe Ausstattung mit dem passenden Debian-Image neu einrichten (ohne die Festplatte)."""
    from bonys_agents import bonysfile

    r = bonysfile.recipe(m)
    print(f"Rezept: {desktops.name(r['desktop'])} mit {', '.join(apps.names(r['app_ids'])) or 'ohne Apps'} wird "
          "hier neu eingerichtet (Debian-Image für diesen Rechner, Downloads aus den offiziellen Quellen).")
    if m.get("extra_desktops"):
        print("Zusätzliche Desktops kommen nicht mit – nachrüsten mit „Desktop hinzufügen …“.")
    if not _ensure_ready(args.yes):
        print("Agent-PC kann noch nicht erstellt werden – siehe oben.")
        return 1
    password = args.password or _ask_password()
    machine = vm.create(args.recipe, password, cpus=args.cpus or r["cpus"], ram_mb=args.ram or r["ram_mb"],
                        disk_gb=r["disk_gb"] or vm.DEFAULT_DISK_GB, username=r["username"], app_ids=r["app_ids"],
                        keyboard=r["keyboard"], timezone_name=r["timezone_name"], desktop=r["desktop"],
                        location=Path(args.vm_location) if args.vm_location else None,
                        progress=lambda phase, frac, msg: print(f"\r{_bar(frac)} {msg[:50]:50}", end="", flush=True))
    print(f"\nAgent-PC '{machine.name}' angelegt. Starten (richtet sich dann ein): bonys-agents start {machine.name}")
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
            print(f"  Eigenes Bild – {c}")
        return 0
    s = wallpaper.update(m, force=args.force, ssh_prompt=True)
    print(wallpaper.describe(s))
    if s.done == "nachfragen":
        print(f"Nichts geändert. Trotzdem auf das neue Standardbild umstellen: bonys-agents wallpaper {m.name} --force")
        return 1
    return 0


def cmd_join(args) -> int:
    """Einer Schulung beitreten: Vorlage vom Kursleiter-Rechner laden (setzt fort), prüfen, importieren."""
    from bonys_agents import bonysfile, share

    if not args.address:
        print("Suche Freigaben im Netz (mDNS) …")
        found = [f for f in share.discover() if f.txt.get("kind") != "present"]
        if not found:
            print("Keine Freigabe gefunden. In VPN-Netzen geht die Suche nicht – dann Adresse und Code angeben: "
                  "bonys-agents join ADRESSE CODE", file=sys.stderr)
            return 1
        for f in found:
            print(f"  {f.address}  {f.txt.get('name', '?')} {f.txt.get('version', '')} "
                  f"von {f.txt.get('creator') or '?'}  (Fingerabdruck {share.short_fingerprint(f.txt.get('fp', ''))})")
        if len(found) > 1:
            print("Mehrere Freigaben – bitte eine Adresse angeben.", file=sys.stderr)
            return 1
        args.address = found[0].address  # Fingerabdruck aus mDNS ist fälschbar – unten trotzdem vergleichen lassen
    target = share.parse_target(args.address, args.code or "", args.fingerprint or "")
    if not target.code:
        target.code = share.normalize_code(input("Freigabe-Code (z. B. 4711-BONY): "))
    try:
        info = share.fetch_info(target)
    except share.IsPresentation as e:
        print(f"Unter {target.netloc} läuft keine Freigabe, sondern die Vorführung „{e.title}“ – im Browser öffnen:")
        print(f"  {e.url()}")
        print(f"  Fingerabdruck zum Vergleichen: {share.short_fingerprint(e.fingerprint)}")
        return 0
    print(f"Verbunden mit {target.netloc}. Fingerabdruck: {share.short_fingerprint(info.fingerprint)}")
    if not target.fingerprint:
        print(f"   ganz: {share.format_fingerprint(info.fingerprint)}")
        if not _yes("Stimmt er mit dem auf dem Bildschirm des Kursleiters überein?", args.yes):
            print("Abgebrochen – nichts geladen.")
            return 1
    print()
    print(bonysfile.describe_manifest(info.manifest, info.size))
    print()
    dest = Path(args.dir) if args.dir else share.downloads_dir()
    file = share.download(info, dest, progress=lambda phase, frac, msg: print(f"\r{_bar(frac)} {msg[:60]:60}",
                                                                                end="", flush=True))
    print(f"\nGeladen: {file}\n")
    return _import_bonys(file, args)


def cmd_template_rename(args) -> int:
    from bonys_agents import templates

    t = templates.rename(args.name, args.new_name)
    print(f"Vorlage heißt jetzt „{t.name}“.")
    return 0


def cmd_template_describe(args) -> int:
    from bonys_agents import templates

    templates.set_description(args.name, args.text)
    print("Beschreibung gespeichert.")
    return 0


def cmd_make_independent(args) -> int:
    m = vm.get(args.name)
    if not m.is_linked():
        print(f"„{m.name}“ ist bereits unabhängig.")
        return 0
    print(f"Übernehme die Daten der Vorlage in „{m.name}“ …")
    m.make_independent(progress=lambda f: print(f"\r{_bar(f)}", end="", flush=True))
    print(f"\n„{m.name}“ ist jetzt eine unabhängige Kopie.")
    return 0


def cmd_gui(args) -> int:
    from bonys_agents.gui.app import run
    return run()


def _import_options(p) -> None:
    """Gemeinsame Optionen von „template import“ und „join“."""
    p.add_argument("--name", help="Unter anderem Namen ablegen")
    p.add_argument("--location", metavar="ORDNER", help="Speicherort der Vorlage (Standard: der bevorzugte)")
    p.add_argument("--create", metavar="AGENT-PC", help="Gleich einen Agent-PC daraus erstellen (unabhängige "
                                                        "Kopie, wenn --full; sonst verknüpft, wenn möglich)")
    p.add_argument("--recipe", metavar="AGENT-PC",
                   help="Nur das Rezept nutzen: Desktop und Apps hier neu einrichten (z. B. andere Architektur)")
    p.add_argument("--full", action="store_true", help="Mit --create: unabhängige Kopie")
    p.add_argument("--vm-location", metavar="ORDNER", help="Mit --create/--recipe: Speicherort des Agent-PCs")
    p.add_argument("--ram", type=int, metavar="MB", help="Mit --create/--recipe: RAM (Standard: Empfehlung)")
    p.add_argument("--cpus", type=int, help="Mit --create/--recipe: CPUs (Standard: Empfehlung)")
    p.add_argument("--password", help=argparse.SUPPRESS)
    p.add_argument("--foreign-arch", action="store_true",
                   help="Andere Architektur trotzdem nutzen (Emulation, sehr langsam)")
    p.add_argument("-y", "--yes", action="store_true")


def _course_commands(sub) -> None:
    """Kursleiter-Befehle (share, present) – in der Anwender-Version nur mit verständlicher Meldung."""
    if edition.IS_TRAINER:
        from bonys_agents.trainer import cli as trainer_cli

        trainer_cli.register(sub)
        return
    for name, what in (("share", "Vorlagen im Netzwerk freigeben"), ("present", "Vorführen")):
        s = sub.add_parser(name, help=f"Schulung: {what} (nur in {edition.NAMES[edition.KURSLEITER]})",
                           add_help=False)
        s.add_argument("rest", nargs=argparse.REMAINDER)
        s.set_defaults(func=lambda _args, what=what: _trainer_only(what))


def _trainer_only(what: str) -> int:
    print(edition.require_trainer(what), file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bonys-agents", description=f"{APP_NAME} – virtuelle Agent-PCs")
    p.add_argument("--version", action="version", version=f"%(prog)s {edition.version_text(__version__)}")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("doctor", help="System prüfen (QEMU, Beschleuniger, Ressourcen)").set_defaults(func=cmd_doctor)
    st = sub.add_parser("setup", help="QEMU und Beschleunigung automatisch installieren")
    st.add_argument("-y", "--yes", action="store_true", help="Ohne Rückfrage")
    st.set_defaults(func=cmd_setup)
    stt = sub.add_parser("selftest", help="Prüfen, ob QEMU auf diesem System startet (wie in der App)")
    stt.add_argument("--no-qt", action="store_true", help="Bibliotheken der Desktop-App nicht prüfen")
    stt.add_argument("--boot", action="store_true",
                     help="zusätzlich einen Agent-PC (leere Platte) mit Firmware starten, bis QEMU läuft")
    stt.set_defaults(func=cmd_selftest)
    up = sub.add_parser("update", help=f"Nach einer neuen Version von {APP_NAME} suchen und aktualisieren")
    up.add_argument("--check", action="store_true", help="Nur suchen, nichts installieren")
    up.add_argument("--pre", action="store_true", help="Auch Testversionen anbieten")
    up.add_argument("-y", "--yes", action="store_true", help="Ohne Rückfrage installieren")
    up.set_defaults(func=cmd_update)
    ug = sub.add_parser("upgrade", help="Agent-PC aktualisieren (apt, Flatpak, KI-Werkzeuge) – muss laufen")
    ug.add_argument("name", nargs="?")
    ug.add_argument("--all", action="store_true", help="Alle laufenden Agent-PCs")
    ug.set_defaults(func=cmd_upgrade)
    ap = sub.add_parser("apps", help="Verfügbare Apps anzeigen – mit NAME: installierte und noch verfügbare")
    ap.add_argument("name", nargs="?", metavar="NAME", help="Agent-PC")
    ap.set_defaults(func=cmd_apps)
    sub.add_parser("desktops", help="Verfügbare Desktops mit RAM-Empfehlung anzeigen").set_defaults(func=cmd_desktops)
    ad = sub.add_parser("add-desktop", help="Weiteren Desktop in einen laufenden Agent-PC installieren (per SSH)")
    ad.add_argument("name")
    ad.add_argument("desktop", choices=list(desktops.DESKTOPS))
    ad.add_argument("--keep-default", action="store_true",
                    help="Automatische Anmeldung beim bisherigen Desktop lassen")
    ad.set_defaults(func=cmd_add_desktop)
    sub.add_parser("gui", help="Desktop-App öffnen").set_defaults(func=cmd_gui)
    sub.add_parser("list", help="Alle Agent-PCs anzeigen").set_defaults(func=cmd_list)

    c = sub.add_parser("create", help="Neuen Agent-PC anlegen und starten")
    c.add_argument("name")
    c.add_argument("--cpus", type=int, help="Standard: alle Kerne des Hosts")
    c.add_argument("--ram", type=int, help="RAM in MB (Standard: Host-RAM minus Reserve)")
    c.add_argument("--disk", type=_disk_gb, metavar="GB",
                   help=f"Festplatte in GB, {vm.MIN_DISK_GB}–{vm.MAX_DISK_GB} (Standard: {vm.DEFAULT_DISK_GB}, "
                        "bei --template die Größe der Vorlage)")
    c.add_argument("--template", metavar="VORLAGE",
                   help="Aus einer Vorlage statt neu installieren (siehe: template list)")
    kind = c.add_mutually_exclusive_group()
    kind.add_argument("--linked", action="store_true",
                      help="Schnell: verknüpft mit der Vorlage (Standard, wenn auf demselben Laufwerk)")
    kind.add_argument("--full", action="store_true", help="Unabhängige, vollständige Kopie der Vorlage")
    c.add_argument("--location", metavar="ORDNER",
                   help="Speicherort, z. B. E:\\BonysAgents oder /media/ich/SSD/BonysAgents (siehe: drives)")
    c.add_argument("--user", default="agent", help="Benutzername im Gast (Standard: agent)")
    c.add_argument("--password", help="Passwort (sonst wird nachgefragt)")
    c.add_argument("--apps", help=f"Kommagetrennt, Standard: {','.join(apps.default_app_ids())} (siehe: apps)")
    c.add_argument("--agents", metavar="LISTE",
                   help=f"Nur die KI-Werkzeuge wählen, z. B. hermes,openclaw,claude-code oder none "
                        f"(verfügbar: {','.join(apps.ids_in_category(apps.AGENT))})")
    c.add_argument("--desktop", default=desktops.DEFAULT, choices=list(desktops.DESKTOPS),
                   help=f"Desktop-Umgebung (Standard: {desktops.DEFAULT}; siehe: desktops)")
    c.add_argument("--keyboard", default="de")
    c.add_argument("--timezone", default="Europe/Berlin")
    c.add_argument("--no-start", action="store_true", help="Nur anlegen, nicht starten")
    c.add_argument("--headless", action="store_true", help="Ohne Fenster starten (auch nach der Einrichtung)")
    c.add_argument("--wait", action="store_true", help="Warten, bis die Einrichtung fertig ist")
    c.add_argument("-y", "--yes", action="store_true", help="Fehlende Software ohne Rückfrage installieren")
    c.add_argument("--vpn-config", metavar="DATEI",
                   help="WireGuard-Konfiguration (.conf) mitgeben – installiert Bony's VPN, die Datei geht nur in "
                        "den Agent-PC")
    c.add_argument("--vpn-name", metavar="TUNNEL", help="Name des Tunnels (Standard: Dateiname)")
    c.add_argument("--vpn-autoconnect", action="store_true", help="Tunnel bei jedem Start automatisch verbinden")
    c.add_argument("--killswitch", action="store_true",
                   help="Kill-Switch: ohne Tunnel kein Internet (Steuerung des Agent-PCs geht weiter)")
    c.add_argument("--bony-netz", action="store_true",
                   help="Beim ersten Start dem Bony-Netz beitreten (Bony-Netz an, Instanz angemeldet)")
    c.set_defaults(func=cmd_create)

    tp = sub.add_parser("template", help="Vorlagen: aus einem fertigen Agent-PC neue in Sekunden erstellen")
    tsub = tp.add_subparsers(dest="template_cmd", required=True)
    tc = tsub.add_parser("create", help="Vorlage aus einem fertig eingerichteten Agent-PC erstellen")
    tc.add_argument("vm", metavar="AGENT-PC")
    tc.add_argument("name", metavar="NAME")
    tc.add_argument("--description", "-d", metavar="TEXT", help="Beschreibung der Vorlage")
    tc.add_argument("--keep-personal-data", action="store_true",
                    help="Anmeldungen, API-Schlüssel usw. NICHT entfernen (Vorlage dann nicht weitergeben)")
    tc.add_argument("--location", metavar="ORDNER", help="Speicherort (Standard: der des Agent-PCs)")
    tc.add_argument("--dry-run", action="store_true",
                    help="Nur nachsehen, was gelöscht würde (startet eine Kopie, ändert nichts)")
    tc.add_argument("-v", "--verbose", action="store_true", help="Gelöschte Pfade anzeigen")
    tc.add_argument("-y", "--yes", action="store_true", help="Ohne Rückfrage (fährt den Agent-PC ggf. herunter)")
    tc.set_defaults(func=cmd_template_create)
    tsub.add_parser("list", help="Vorlagen anzeigen").set_defaults(func=cmd_template_list)
    td = tsub.add_parser("delete", help="Vorlage löschen (gesperrt, solange verknüpfte Agent-PCs existieren)")
    td.add_argument("name")
    td.add_argument("--make-independent", action="store_true",
                    help="Verknüpfte Agent-PCs vorher zu unabhängigen Kopien machen")
    td.add_argument("-y", "--yes", action="store_true")
    td.set_defaults(func=cmd_template_delete)
    te = tsub.add_parser("export", help="Vorlage zum Weitergeben als eine Datei (.bonys) speichern – mit "
                                        "Frisch-Prüfung, ohne nicht weitergebbare Programme")
    te.add_argument("name")
    te.add_argument("file", metavar="DATEI", nargs="?",
                    help="Zieldatei oder Ordner (Standard: Persönlicher Ordner, NAME-VERSION.bonys)")
    te.add_argument("--creator", metavar="TEXT", help="Ersteller (z. B. Name des Kursleiters)")
    te.add_argument("--version", metavar="V", help="Version der Vorlage (Standard: 1)")
    te.add_argument("--preview", metavar="BILD", help="Vorschaubild (PNG oder JPEG, höchstens 5 MB)")
    te.add_argument("--clean", action="store_true",
                    help="Funde der Frisch-Prüfung in der Export-Kopie bereinigen (die Vorlage bleibt unverändert)")
    te.add_argument("-v", "--verbose", action="store_true", help="Ausgabe aus der Export-Kopie anzeigen")
    te.set_defaults(func=cmd_template_export)
    ti = tsub.add_parser("import", help="Vorlage aus einer .bonys-Datei (oder .bonys-template) hinzufügen")
    ti.add_argument("file", metavar="DATEI")
    _import_options(ti)
    ti.set_defaults(func=cmd_template_import)
    tr = tsub.add_parser("rename", help="Vorlage umbenennen")
    tr.add_argument("name")
    tr.add_argument("new_name", metavar="NEUER-NAME")
    tr.set_defaults(func=cmd_template_rename)
    tdesc = tsub.add_parser("describe", help="Beschreibung ändern")
    tdesc.add_argument("name")
    tdesc.add_argument("text")
    tdesc.set_defaults(func=cmd_template_describe)
    _course_commands(sub)
    jn = sub.add_parser("join", help="Schulung beitreten: Vorlage vom Kursleiter laden und importieren "
                                     "(ohne Adresse: im Netz suchen)")
    jn.add_argument("address", metavar="ADRESSE", nargs="?",
                    help="z. B. 192.168.1.5:47110 oder der Link bonys://… (aus dem QR-Code)")
    jn.add_argument("code", metavar="CODE", nargs="?", help="Freigabe-Code, z. B. 4711-BONY")
    jn.add_argument("--fingerprint", metavar="FP", help="Fingerabdruck des Zertifikats (sonst Rückfrage)")
    jn.add_argument("--dir", metavar="ORDNER", help="Wohin laden (Standard: Datenordner/schulung)")
    _import_options(jn)
    jn.set_defaults(func=cmd_join)
    wp = sub.add_parser("wallpaper", help="Neues Standard-Hintergrundbild in einen laufenden Agent-PC bringen "
                                          "(nur, wenn noch das alte aktiv ist)")
    wp.add_argument("name")
    wp.add_argument("--force", action="store_true", help="Auch umstellen, wenn ein eigenes Bild gewählt ist")
    wp.add_argument("--check", action="store_true", help="Nur anzeigen, welches Bild aktiv ist")
    wp.set_defaults(func=cmd_wallpaper)
    mi = sub.add_parser("make-independent", help="Verknüpften Agent-PC in eine unabhängige Kopie umwandeln")
    mi.add_argument("name")
    mi.set_defaults(func=cmd_make_independent)

    sub.add_parser("drives", help="Laufwerke und freien Platz anzeigen").set_defaults(func=cmd_drives)
    mv = sub.add_parser("move", help="Agent-PC auf ein anderes Laufwerk/in einen anderen Ordner verschieben")
    mv.add_argument("name")
    mv.add_argument("target", metavar="ORDNER")
    mv.set_defaults(func=cmd_move)
    im = sub.add_parser("import", help="Vorhandene Agent-PCs (z. B. von einer SSD) hinzufügen")
    im.add_argument("path", metavar="ORDNER")
    im.set_defaults(func=cmd_import)
    ins = sub.add_parser("install", help="Apps nachträglich in einen laufenden Agent-PC installieren "
                                          "(Abhängigkeiten kommen mit; erneut aufrufen setzt nach Abbruch fort)")
    ins.add_argument("name")
    ins.add_argument("apps", nargs="+", metavar="APP", help=f"z. B. {', '.join(apps.visible_ids())}")
    ins.set_defaults(func=cmd_install)
    mcp = sub.add_parser("mission-control", help="Mission Control im Agent-PC: Status, öffnen, aktualisieren, "
                                                 "deinstallieren, Weiterleitung",
                         description="status | open | update [--version X] | uninstall [--purge] | forward on|off")
    mcp.add_argument("name")
    mcp.add_argument("action", choices=["status", "open", "update", "uninstall", "forward"])
    mcp.add_argument("value", nargs="?", metavar="WERT", help="bei forward: on oder off")
    mcp.add_argument("--version", default="latest",
                     help=f"bei update: Release, z. B. {mission_control.VERSION} (Standard: latest = neuestes)")
    mcp.add_argument("--purge", action="store_true",
                     help="bei uninstall: auch Einstellungen, Geheimnisse und Daten löschen (nicht umkehrbar)")
    mcp.add_argument("-y", "--yes", action="store_true", help="Ohne Rückfrage")
    mcp.set_defaults(func=cmd_mission_control)
    vp = sub.add_parser("vpn", help="Bony's VPN im laufenden Agent-PC: Status, verbinden, trennen, importieren",
                        description="status [--json] | up [TUNNEL] | down [TUNNEL] | import DATEI | "
                                    "killswitch on|off | autostart on|off | ip | update (VPN-App aktualisieren)")
    vp.add_argument("name")
    vp.add_argument("action", choices=["status", "up", "down", "import", "killswitch", "autostart", "ip", "update"])
    vp.add_argument("value", nargs="?", metavar="WERT",
                    help="import: die .conf-Datei · up/down: der Tunnel · killswitch/autostart: on oder off")
    vp.add_argument("--tunnel", metavar="TUNNEL", help="Tunnelname (bei import: statt des Dateinamens)")
    vp.add_argument("--replace", action="store_true", help="bei import: vorhandenen Tunnel ersetzen")
    vp.add_argument("--json", action="store_true", help="bei status: maschinenlesbar")
    vp.set_defaults(func=cmd_vpn)
    rm = sub.add_parser("remote", help="Fernzugriff (RDP aus dem Heimnetz) an/aus – wirkt sofort")
    rm.add_argument("name")
    rm.add_argument("state", choices=["on", "off"])
    rm.add_argument("--permanent", action="store_true",
                    help="Dauerhaft, auch nach Neustarts (sonst nur bis zum Herunterfahren)")
    rm.set_defaults(func=cmd_remote)
    co = sub.add_parser("connect", help="Verbindung öffnen (Remmina, Remotedesktop oder remote-viewer)")
    co.add_argument("name")
    proto = co.add_mutually_exclusive_group()
    proto.add_argument("--rdp", action="store_true", help="per RDP (Standard)")
    proto.add_argument("--spice", action="store_true", help="per SPICE")
    co.set_defaults(func=cmd_connect)
    di = sub.add_parser("display", help="Anzeige wählen: QEMU-Fenster oder SPICE-Fenster")
    di.add_argument("name")
    di.add_argument("mode", choices=["qemu", "spice"])
    di.set_defaults(func=cmd_display)
    sc = sub.add_parser("screen", help="Bildschirm: Auflösung folgt dem Fenster, Bild skalieren oder feste Auflösung")
    sc.add_argument("name")
    sc.add_argument("mode", nargs="?", choices=list(screen.MODES),
                    help="auto = folgt dem Fenster (Standard), scale = Bild skalieren, fixed = feste Auflösung")
    sc.add_argument("--size", metavar="BxH", help=f"Auflösung für scale/fixed, z. B. {screen.DEFAULT_SIZE}")
    sc.set_defaults(func=cmd_screen)
    fs = sub.add_parser("fullscreen", help="QEMU-Fenster in den Vollbildmodus schalten bzw. zurück (Strg+Alt+F)")
    fs.add_argument("name")
    fs.set_defaults(func=cmd_fullscreen)
    dd = sub.add_parser("display-driver", help="Anzeige-Treiber im laufenden Agent-PC einrichten/erneuern "
                                               "(Auflösung folgt dem Fenster)")
    dd.add_argument("name")
    dd.set_defaults(func=cmd_display_driver)
    rs = sub.add_parser("resize", help="Festplatte eines Agent-PCs vergrößern (muss ausgeschaltet sein)")
    rs.add_argument("name")
    rs.add_argument("size", type=_disk_gb, metavar="GRÖSSE", help="Neue Größe in GB, z. B. 128")
    rs.set_defaults(func=cmd_resize)
    rc = sub.add_parser("resources", help="CPU-Kerne und Arbeitsspeicher anzeigen oder ändern (ohne Angaben: "
                                          "aktuelle Werte und Empfehlung)")
    rc.add_argument("name")
    rc.add_argument("--cpus", type=int, metavar="N", help="Anzahl CPU-Kerne")
    rc.add_argument("--ram", type=_ram_gb, metavar="GB", help="Arbeitsspeicher in GB, z. B. 6")
    rc.add_argument("--restart", action="store_true", help="Läuft der Agent-PC, ihn dafür neu starten")
    rc.set_defaults(func=cmd_resources)
    dl = sub.add_parser("default-location", help="Standard-Speicherort anzeigen oder ändern")
    dl.add_argument("path", nargs="?", metavar="ORDNER")
    dl.add_argument("--reset", action="store_true", help="Zurück zum Hauptsystem")
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
            s.add_argument("--wait", action="store_true", help="Bei laufender Einrichtung warten, bis sie fertig ist")
        if name == "stop":
            s.add_argument("--force", action="store_true", help="Sofort ausschalten")
        if name == "logs":
            s.add_argument("-n", "--lines", type=int, default=100)
        if name == "delete":
            s.add_argument("-y", "--yes", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    procutil.add_homebrew_to_path()
    args = build_parser().parse_args(argv)
    if not getattr(args, "func", None):
        # Ohne Befehl: Desktop-App öffnen (Doppelklick-Verhalten).
        return cmd_gui(args)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nAbgebrochen.")
        return 130
    except (ValueError, KeyError, FileExistsError, RuntimeError, qemu.QemuNotFound, OSError) as e:
        msg = e.args[0] if isinstance(e, KeyError) and e.args else e
        print(f"Fehler: {msg}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
