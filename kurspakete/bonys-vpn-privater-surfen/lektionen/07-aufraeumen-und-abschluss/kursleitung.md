- Löschen im Dateimanager (Nemo) legt die Datei in den Papierkorb – erst „Papierkorb leeren“ macht sie weg. Wer im
  Terminal arbeiten mag: `shred -u ~/Downloads/*.conf`.
- Die Prüfung sieht nur nach Dateinamen `*.conf` in den Downloads-Ordnern und ob in Bony's VPN ein Tunnel
  importiert ist – sie öffnet keine Datei.
- Abschlussrunde: „Wo nutzt ihr das VPN als Erstes?“ – und noch einmal der Merksatz: privater, nicht anonym.
- Vorlagen: Eine Vorlage „frisch“ (ohne persönliche Daten) setzt Bony's VPN ganz zurück, und beim Weitergeben
  (`.bonys`) warnt Bony's Agents vor gefundenen WireGuard-Konfigurationen. Eine Vorlage **mit** persönlichen Daten
  (Klon) enthält den Tunnel samt Schlüssel – die nie weitergeben.
