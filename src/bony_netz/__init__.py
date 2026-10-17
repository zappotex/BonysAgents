# SPDX-License-Identifier: GPL-3.0-or-later
"""bony_netz – gemeinsamer Baustein von Bony's Agents und Bony's VPN.

Spricht mit der Zentrale eines Bony-Netz-Servers und merkt sich die Anmeldung.
Benutzt nur die Python-Standardbibliothek.

Kurzbeispiel:

    from bony_netz import Konto, Zentrale

    konto = Konto.laden()                       # gespeicherte Anmeldung oder leer
    zentrale = Zentrale(konto.server)
    if not konto.angemeldet:
        konto.uebernehmen(zentrale.instanz_registrieren())
        konto.speichern()
    zentrale.token = konto.token
    print(zentrale.geraete())
"""

from .agentenpc import erstbeitritt_skript, geraetename
from .fehler import NetzFehler, ZentraleFehler
from .konto import STANDARD_SERVER, Konto
from .zentrale import Zentrale

__all__ = [
    "Konto", "Zentrale", "ZentraleFehler", "NetzFehler",
    "STANDARD_SERVER", "erstbeitritt_skript", "geraetename",
]
__version__ = "0.1.1"
