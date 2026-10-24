- Beim Vorführen die **Tunnel-Karte** (Adresse, DNS, Endpunkt) nicht lange zeigen – Fenster verkleinern oder nach dem
  Import weiterklicken. Den Schlüssel zeigt Bony's VPN ohnehin nie.
- „Server antwortet nicht“ / kein Handshake: Server überlastet oder abgeschaltet → bei Proton eine neue
  Konfiguration mit anderem Free-Server holen, alten Tunnel in Bony's VPN über „Löschen …“ entfernen.
- Free-Konto schon auf dem Handy verbunden → dort trennen (ein Gerät gleichzeitig).
- Warnung **„Befehle in der Konfiguration“**: bei Proton und FRITZ!Box nicht zu erwarten. Kommt sie doch, Datei
  nicht übernehmen – solche Befehle laufen als root.
- Die Prüfung fragt nur `bonys-vpn status --json` (verbundener Tunnel mit Handshake) – darin stehen keine Schlüssel.
