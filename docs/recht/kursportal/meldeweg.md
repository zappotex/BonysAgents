# Meldeweg für rechtswidrige Inhalte – ENTWURF

> Entwurf, keine Rechtsberatung – vor Veröffentlichung prüfen lassen.

## Für Meldende
Du hast im Community-Katalog ein Kurspaket gefunden, das Rechte verletzt oder rechtswidrig ist? Schreib an
<KONTAKT-E-MAIL> mit:

1. Name des Kurspakets und Version,
2. was rechtswidrig ist und warum (Gesetz, Recht, Fundstelle im Paket),
3. deinen Kontaktdaten für Rückfragen (werden nur für diese Meldung verwendet),
4. der Erklärung, dass deine Angaben nach bestem Wissen richtig sind.

## Ablauf (intern)
1. Eingang bestätigen (innerhalb von <FRIST, Vorschlag 2 Werktage>).
2. Bei offensichtlichem Verstoß sofort **zurückziehen**:
   `docker compose exec portal python /app/server.py entscheiden <ID> withdrawn <AKTEUR> "Meldung"`.
   Der Katalog wird dabei sofort neu geschrieben, das Paket ist nicht mehr abrufbar.
3. Prüfen und entscheiden; Einreichende informieren, wenn eine Kontaktmöglichkeit besteht.
4. Bei bestätigtem Verstoß oder Anfrage nach Art. 17 DSGVO endgültig löschen:
   `docker compose exec portal python /app/server.py loeschen <ID> rechtsverstoss|art17 <AKTEUR>`.
5. Meldende über das Ergebnis informieren. Die Meldung und ihre Bearbeitung kurz festhalten (ohne Personendaten, soweit
   möglich).
