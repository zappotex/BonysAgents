"""Fehlerarten. Die Meldungen sind auf Deutsch und können direkt angezeigt werden."""


class NetzFehler(Exception):
    """Die Zentrale war nicht erreichbar (kein Internet, Server aus, falsche Adresse)."""


class ZentraleFehler(Exception):
    """Die Zentrale hat die Anfrage abgelehnt.

    status:  HTTP-Statuscode, z. B. 401 (Anmeldung ungültig), 403 (kein Kursleiter),
             404 (nicht gefunden), 409 (Grenze erreicht / falscher Zustand), 429 (zu viele Anmeldungen)
    meldung: Text der Zentrale für den Nutzer
    """

    def __init__(self, status: int, meldung: str) -> None:
        super().__init__(meldung)
        self.status = status
        self.meldung = meldung

    @property
    def anmeldung_ungueltig(self) -> bool:
        """True, wenn das gespeicherte Token nicht mehr gilt (Instanz gelöscht o. Ä.)."""
        return self.status == 401
