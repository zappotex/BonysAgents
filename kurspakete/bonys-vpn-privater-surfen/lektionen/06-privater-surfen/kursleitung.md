- Lass die Teilnehmer selbst wählen, Punkt 1 und 2 sind Pflicht für alle. Danach kurz sammeln: Wer hatte welche
  DNS-Server? Wer einen einzigartigen Fingerabdruck? (Meist fast alle – gut für die Diskussion.)
- dnsleaktest zeigt Server des Internetanbieters: Bony's VPN nimmt das DNS aus der Konfiguration; fehlt dort eine
  Zeile `DNS =`, gehen die Anfragen am Tunnel vorbei → bei Proton neu erstellen (DNS ist dort immer gesetzt).
- Privates Fenster mit Tor braucht ein paar Sekunden zum Verbinden. Manche Seiten zeigen dort Captchas – normal.
- Wegwerf-PC und Tor Browser nur zeigen, nicht alle installieren lassen (dauert zu lange). Den Tor Browser gibt es
  für Linux nur auf x86_64, also nicht auf Macs mit Apple-Chip.
- Für Schnelle: Kill-Switch-Ausnahmen im Menü ansehen, oder Bony's Agents → Reiter „VPN“ beim laufenden Agent-PC.
