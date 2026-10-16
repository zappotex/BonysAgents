# SPDX-License-Identifier: GPL-3.0-or-later
"""Unerwartete Fehler der Desktop-App protokollieren (``fehler.log`` im Datenordner).

Die fertigen Programme haben kein Konsolenfenster – ohne Protokoll verschwänden Fehler still (ein Knopf tut
nichts, die App startet nicht). Das Protokoll enthält nur Programmversion, System und den Ablauf des Fehlers –
keine Passwörter, keine Inhalte von Agent-PCs.
"""

from __future__ import annotations

import platform
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path

from bonys_agents import __version__, storage

MAX_BYTES = 512 * 1024   # danach nur die zweite Hälfte behalten


def log_file() -> Path:
    return storage.data_dir() / "fehler.log"


def write(exc_type, exc, tb, where: str = "") -> Path | None:
    """Fehler anhängen. Gibt den Pfad zurück (None, wenn nicht einmal das ging)."""
    f = log_file()
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    head = (f"==== {datetime.now().isoformat(timespec='seconds')} · Bony's Agents {__version__} · "
            f"{platform.system()} {platform.release()} · Python {platform.python_version()}"
            + (f" · {where}" if where else ""))
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        if f.exists() and f.stat().st_size > MAX_BYTES:
            data = f.read_bytes()
            f.write_bytes(data[len(data) // 2:])
        with f.open("a", encoding="utf-8") as out:
            out.write(f"{head}\n{text}\n")
    except OSError:
        return None
    if sys.__stderr__:
        try:
            sys.__stderr__.write(text)
        except (OSError, ValueError):
            pass
    return f


def short(exc) -> str:
    """Eine Zeile für die Meldung – die Einzelheiten stehen im Protokoll."""
    text = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
    return text[:300]


def install(show=None) -> None:
    """``sys.excepthook``/``threading.excepthook`` setzen. ``show(text)`` zeigt eine Meldung (nur im Hauptthread)."""
    busy = {"on": False}

    def hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        path = write(exc_type, exc, tb)
        if show is None or busy["on"] or threading.current_thread() is not threading.main_thread():
            return
        busy["on"] = True   # keine Flut von Meldungen, wenn derselbe Fehler immer wieder auftritt
        try:
            show(f"Ein unerwarteter Fehler ist aufgetreten:\n{short(exc)}\n\n"
                 + (f"Einzelheiten stehen im Fehlerprotokoll:\n{path}\n\n" if path else "")
                 + "Bitte beim Melden des Fehlers dieses Protokoll mitschicken.")
        except Exception:  # noqa: BLE001 – die Meldung selbst darf nicht wieder hierher führen
            pass
        finally:
            busy["on"] = False

    def thread_hook(args):
        if args.exc_type is SystemExit:
            return
        write(args.exc_type, args.exc_value, args.exc_traceback,
              where=f"Thread {args.thread.name if args.thread else '?'}")

    sys.excepthook = hook
    threading.excepthook = thread_hook
