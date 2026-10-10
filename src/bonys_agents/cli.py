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
    APP_NAME, __version__, apps, deps, desktops, host, procutil, qemu, remote, screen, storage, vm, vpnlink,
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
    print(f"{APP_NAME} {__version__}")
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
    desk = desktops.get(args.desktop)
    _warn_ram(desk.id, args.ram)
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
    )
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


def _warn_ram(desktop_id: str, ram_mb: int | None) -> None:
    ram = ram_mb or host.detect().default_vm_ram_mb
    warning = desktops.ram_warning(desktop_id, ram)
    if warning:
        print(f"⚠ {warning}")


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
                        template=tpl.name, linked=linked, vpn=vpn)
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
    print(f"Apps:    {', '.join(c.apps)}\nOrdner:  {m.path}")
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
    if r["spice_port"]:
        where = "aus dem Heimnetz (mit Passwort)" if r["spice_lan"] else "nur an diesem Rechner"
        print(f"  SPICE spice://127.0.0.1:{r['spice_port']} – {where}")
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
    m.delete()
    print(f"'{args.name}' gelöscht.")
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


def cmd_apps(args) -> int:
    for title, cat in (("Programme", apps.PROGRAM), ("KI-Werkzeuge (--agents)", apps.AGENT)):
        print(f"{title}:")
        for a in apps.APPS.values():
            if a.category == cat:
                std = "  [Standard]" if a.default else ""
                print(f"  {a.id:12} {a.name:18} {a.description}{std}")
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
    spec = apps.APPS.get(args.app)
    if spec is None:
        raise ValueError(f"Unbekannte App '{args.app}'. Verfügbar: {', '.join(apps.APPS)}")
    print(f"Installiere {spec.name} in „{m.name}“ per SSH – ssh fragt ggf. nach dem Passwort des Agent-PCs.")
    m.install_app(args.app)
    print(f"Fertig: {spec.name} ist installiert. Das Symbol liegt auf dem Schreibtisch des Agent-PCs.")
    return 0


def _print_vpn(st: dict) -> None:
    print(vpnlink.summary(st))
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
    if value and args.action in ("status", "ip"):
        raise ValueError(f"„{args.action}“ erwartet keine weitere Angabe.")
    tunnel = args.tunnel or (value if args.action in ("up", "down") else None)
    state = {"an": "on", "aus": "off"}.get(value or "", value)
    if args.action == "status":
        st = vpnlink.status(m, **kw)
        if args.json:
            print(json.dumps(st, ensure_ascii=False, indent=2))
        else:
            _print_vpn(st)
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
        for item in cloudinit.PERSONAL_DATA:
            print(f"  • {item.title}")
            for path in item.paths:
                print(f"      /home/{m.config.username}/{path}{item.note()}")
    else:
        print("  • Persönliche Daten bleiben ERHALTEN (--keep-personal-data) – Vorlage nicht weitergeben!")
        if vpnlink.APP_ID in m.config.apps:
            print(f"  ⚠ {vpnlink.CLONE_WARNING}")
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
    from bonys_agents import templates

    print(f"Hinweis: {templates.EXPORT_WARNING}")
    out = templates.export(args.name, Path(args.file), progress=_template_progress)
    print(f"\nExportiert: {out}")
    return 0


def cmd_template_import(args) -> int:
    from bonys_agents import templates

    t = templates.import_file(Path(args.file), location=Path(args.location) if args.location else None,
                              name=args.name, progress=_template_progress)
    print(f"\nVorlage „{t.name}“ importiert: {t.path}")
    return 0


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


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bonys-agents", description=f"{APP_NAME} – virtuelle Agent-PCs")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
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
    sub.add_parser("apps", help="Verfügbare Apps anzeigen").set_defaults(func=cmd_apps)
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
    te = tsub.add_parser("export", help="Vorlage als eine Datei (.bonys-template) speichern")
    te.add_argument("name")
    te.add_argument("file", metavar="DATEI")
    te.set_defaults(func=cmd_template_export)
    ti = tsub.add_parser("import", help="Vorlage aus einer .bonys-template-Datei hinzufügen")
    ti.add_argument("file", metavar="DATEI")
    ti.add_argument("--name", help="Unter anderem Namen ablegen")
    ti.add_argument("--location", metavar="ORDNER", help="Speicherort (Standard: der bevorzugte)")
    ti.set_defaults(func=cmd_template_import)
    tr = tsub.add_parser("rename", help="Vorlage umbenennen")
    tr.add_argument("name")
    tr.add_argument("new_name", metavar="NEUER-NAME")
    tr.set_defaults(func=cmd_template_rename)
    tdesc = tsub.add_parser("describe", help="Beschreibung ändern")
    tdesc.add_argument("name")
    tdesc.add_argument("text")
    tdesc.set_defaults(func=cmd_template_describe)
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
    ins = sub.add_parser("install", help="App nachträglich in einen laufenden Agent-PC installieren (per SSH)")
    ins.add_argument("name")
    ins.add_argument("app", help=f"z. B. {', '.join(apps.APPS)}")
    ins.set_defaults(func=cmd_install)
    vp = sub.add_parser("vpn", help="Bony's VPN im laufenden Agent-PC: Status, verbinden, trennen, importieren",
                        description="status [--json] | up [TUNNEL] | down [TUNNEL] | import DATEI | "
                                    "killswitch on|off | autostart on|off | ip")
    vp.add_argument("name")
    vp.add_argument("action", choices=["status", "up", "down", "import", "killswitch", "autostart", "ip"])
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
