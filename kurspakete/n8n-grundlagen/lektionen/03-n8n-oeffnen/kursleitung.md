- Kein Symbol „n8n“: Agent-PC ohne n8n erstellt → Agent-PC starten, in der Detailansicht bei „Programme“ →
  „Programme hinzufügen …“ → n8n (dauert einige Minuten, lädt das offizielle Docker-Image).
- Seite bleibt leer: n8n startet noch (bis zu einer Minute nach dem Hochfahren). Danach F5.
- Für das Konto reicht eine beliebige Adresse im Format `name@example.com` – n8n schickt keine Mails. Das Passwort
  aber merken, sonst ist n8n nach dem Abmelden verschlossen.
- Die Prüfung fragt in der Datenbank von n8n nur, **ob** ein Benutzer mit E-Mail-Adresse existiert – sie liest weder
  Adresse noch Passwort.
