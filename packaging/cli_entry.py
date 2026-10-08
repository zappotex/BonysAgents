# SPDX-License-Identifier: GPL-3.0-or-later
"""Einstiegspunkt der Kommandozeile in den fertigen Paketen.

Ohne Argumente öffnet sich die Desktop-App, mit Argumenten arbeitet die Kommandozeile.
"""

from bonys_agents.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
