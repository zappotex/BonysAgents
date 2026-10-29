# SPDX-License-Identifier: GPL-3.0-or-later
"""Kommandozeile der Kursleiter-Funktionen: ``bonys-agents share`` und ``bonys-agents present``.

Nur in „Bony's Agents Kursleiter“ – ``bonys_agents.cli`` hängt die Befehle über ``register()`` ein.
"""

from __future__ import annotations

import contextlib
import signal
import sys

from bonys_agents import vm
from bonys_agents.cli import _print_qr, _template_progress
from bonys_agents.i18n import tr


def _ignore_further_interrupts() -> None:
    """Ein zweites Strg+C mitten im Aufräumen (Server stoppen, mDNS abmelden) brächte halbe Zustände."""
    with contextlib.suppress(ValueError, OSError):
        signal.signal(signal.SIGINT, signal.SIG_IGN)


def register(sub) -> None:
    sh = sub.add_parser("share", help=tr("Schulung: Vorlage im Netzwerk (LAN/VPN) freigeben – Teilnehmer treten mit "
                                         "„join“ bei"))
    sh.add_argument("name", metavar="VORLAGE")
    sh.add_argument("--port", type=int, default=47110, help=tr("Port (Standard: 47110)"))
    sh.add_argument("--timeout", type=int, default=120, metavar="MIN",
                    help=tr("Freigabe endet automatisch nach MIN Minuten (Standard: 120)"))
    sh.add_argument("--max-downloads", type=int, default=4, metavar="N",
                    help=tr("Höchstens N gleichzeitige Downloads, der Rest wartet (Standard: 4)"))
    sh.add_argument("--creator", metavar="TEXT", help=tr("Ersteller (nur beim ersten Erzeugen der Datei)"))
    sh.add_argument("--version", metavar="V", help=tr("Version der Vorlage (nur beim ersten Erzeugen der Datei)"))
    sh.add_argument("--clean", action="store_true", help=tr("Funde der Frisch-Prüfung in der Export-Kopie bereinigen"))
    sh.set_defaults(func=cmd_share)
    pr = sub.add_parser("present", help=tr("Schulung: laufenden Agent-PC live im Browser der Teilnehmer zeigen "
                                           "(nur ansehen)"))
    pr.add_argument("name")
    pr.add_argument("--port", type=int, default=47120, help=tr("Port (Standard: 47120)"))
    pr.add_argument("--timeout", type=int, default=90, metavar="MIN",
                    help=tr("Vorführung endet automatisch nach MIN Minuten (Standard: 90)"))
    pr.add_argument("--max-viewers", type=int, default=30, metavar="N", help=tr("Höchstens N Zuschauer (Standard: 30)"))
    pr.add_argument("--quality", choices=["low", "medium", "high"], default="medium",
                    help=tr("Bildqualität und -rate: low (5 Bilder/s), medium (10, Standard – gut fürs WLAN), high "
                            "(20)"))
    pr.set_defaults(func=cmd_present)


def cmd_share(args) -> int:
    """Vorlage im Netzwerk freigeben (Kursleiter) – läuft, bis Strg+C, Zeit abgelaufen oder zu viele Fehlversuche."""
    from bonys_agents import bonysfile, share, templates
    from bonys_agents.trainer import share_server

    t = templates.get(args.name)
    cached = share_server.cached_bundle(t)
    if cached:
        file, sha = cached
        print(tr("Datei für die Freigabe: {file} (schon erzeugt, Vorlage seitdem unverändert)", file=file))
    else:
        print(tr("Erzeuge die .bonys-Datei für die Freigabe (einmalig, mit Frisch-Prüfung) …"))
        try:
            file = bonysfile.export(t.name, share_server.cache_target(t, args.version or t.version or "1"),
                                    creator=args.creator or "", version=args.version or "", clean=args.clean,
                                    progress=_template_progress)
        except bonysfile.NotFreshError as e:
            print(f"\n{e}", file=sys.stderr)
            if not e.strict:
                print(tr("\nBereinigen (nur in der Export-Kopie): erneut mit --clean."), file=sys.stderr)
            return 1
        print(tr("\nBerechne Prüfsumme …"))
        sha = share_server.remember_cache(t, file)
    s = share_server.Share(file, port=args.port, timeout_min=args.timeout, max_downloads=args.max_downloads, sha256=sha)
    s.start()
    print(tr("\nFreigabe „{name}“ läuft – endet nach {timeout_min} min (Strg+C beendet sofort).\n", name=t.name,
             timeout_min=s.timeout_min))
    print(tr("  Freigabe-Code:     {code}", code=s.code))
    print(tr("  Fingerabdruck:     {wert}  (Teilnehmer vergleichen)", wert=share.short_fingerprint(s.fingerprint)))
    print(f"                     {share.format_fingerprint(s.fingerprint)}")
    for addr in s.addresses():
        kind = share.address_kind(addr)
        print(f"  Adresse ({kind or '?'}):".ljust(21) + f"{addr}:{s.port}")
    print(tr("\n  Teilnehmer: bonys-agents join {wert}:{port} {code} --fingerprint {fingerprint}",
             wert=(s.addresses() or ['ADRESSE'])[0], port=s.port, code=s.code, fingerprint=s.fingerprint))
    print(tr("  oder den Link einfügen: {wert}\n", wert=s.link()))
    _print_qr(s.link())
    print(tr("Firewall: {wert}\n", wert=share_server.firewall_hinweis(s.port)))
    shown = 0
    try:
        while not s.stopped.wait(2):
            with s.lock:
                new_events = s.events[shown:]
                shown = len(s.events)
            for line in new_events:
                print(line)
            busy = [p for p in s.participants.values() if p.status in ("lädt", "wartet")]
            if busy:
                print("   " + " | ".join(f"{p.name}: {p.status}"
                                         + (f" {p.percent:.0f} %" if p.status == "lädt" else f" (Platz {p.queue})")
                                         for p in busy), flush=True)
    except KeyboardInterrupt:
        _ignore_further_interrupts()
        s.stop("Freigabe beendet (Strg+C).")
    for line in s.events[shown:]:
        print(line)
    done = sum(1 for p in s.participants.values() if p.status == "fertig")
    print(tr("Freigabe beendet: {done} Teilnehmer haben die Vorlage geladen.", done=done))
    return 0


def cmd_present(args) -> int:
    """Agent-PC live im Browser der Teilnehmer zeigen (nur ansehen) – bis Strg+C, Zeitablauf oder Ausschalten."""
    from bonys_agents.trainer import present, share_server

    m = vm.get(args.name)
    try:
        p = present.for_vm(m, port=args.port, timeout_min=args.timeout, max_viewers=args.max_viewers,
                           quality=args.quality)
        p.start()
    except present.PresentError as e:
        print(e, file=sys.stderr)
        return 1
    print()
    print(present.describe(p))
    print(tr("\n  Link mit Code (QR-Code): {wert}\n", wert=p.url()))
    _print_qr(p.url())
    print(tr("Firewall: {wert}", wert=share_server.firewall_hinweis(p.port)))
    print(tr("\nStrg+C beendet die Vorführung. Pause: in der Desktop-App („Vorführen …“).\n"))
    shown = 0
    try:
        while not p.stopped.wait(2):
            with p.lock:
                new_events = p.events[shown:]
                shown = len(p.events)
            for line in new_events:
                print(line, flush=True)
    except KeyboardInterrupt:
        _ignore_further_interrupts()
        p.stop("Vorführung beendet (Strg+C).")
    for line in p.events[shown:]:
        print(line)
    return 0
