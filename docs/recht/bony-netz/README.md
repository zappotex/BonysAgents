# Rechtstexte Bony-Netz und Kursraum (ENTWÜRFE)

Stand: 28.10.2026 · aus der Durchsicht vor 1.0, Teil 2 (`docs/review-1.0-teil2.md`, Punkte DR-01 bis DR-03).
**Das sind Entwürfe, keine Rechtsberatung.** Eine Fachperson (Datenschutz/IT-Recht/Telekommunikationsrecht) muss sie
prüfen, bevor sie veröffentlicht werden.

Verantwortlicher ist Bony **privat**. Name, Anschrift und Kontaktadresse stehen als Platzhalter in `<…>` und werden
von Bony **nicht im Repository**, sondern direkt in der Veröffentlichung eingetragen.

| Datei | Zweck |
|---|---|
| [datenschutzerklaerung.md](datenschutzerklaerung.md) | Information nach Art. 13 DSGVO für Zentrale, Netz und Kursraum |

Das **Impressum** des Kursportals (`docs/recht/kursportal/impressum.md`) kann für alle Dienste unter `bony23.de` gelten.
Vorschlag: eine gemeinsame Datenschutzseite unter `https://kurse.bony23.de/datenschutz` (Kursportal + Bony-Netz) – die
App verlinkt diese Adresse im Bony-Netz-Dialog und im Katalogfenster. Die fertigen Seiten legt Bony selbst in den
Ordner `rechtstexte/` auf dem Server.

Technische Grundlage: Zentrale ab 0.2.1 (Repo `bonys-netz`) – kein Zugriffsprotokoll, Container-Protokolle begrenzt
(3 × 5 MB), IP-Hash nur 24 Stunden, Teilnahmen beim Kursende gelöscht, beendete Kurse nach 30 Tagen, Kurse enden 7
Tage nach Ablauf des Kurscodes.

## Offene Fragen an die Fachperson
1. **Telekommunikationsrecht:** Das Bony-Netz vermittelt Verbindungen (Relay) und bietet Chat, Video und Ton für einen
   offenen Nutzerkreis. Besteht eine **Meldepflicht bei der Bundesnetzagentur (§ 5 TKG)**? Welche Pflichten folgen aus
   dem **Fernmeldegeheimnis (§ 3 TDDDG)**?
2. Rollen: Ist die Kursleitung gegenüber den Teilnehmenden eigene Verantwortliche, gemeinsam Verantwortliche
   (Art. 26) oder Auftragsverarbeiterin (Art. 28)? Braucht es Nutzungsbedingungen für Kursleitungen?
3. Rechtsgrundlage für Kamera und Mikrofon im Kursraum (Vertrag oder Einwilligung)? Kurse mit Minderjährigen (Art. 8)?
4. Genügen die Löschfristen (Abschnitt 3), und sind Verzeichnis der Verarbeitungstätigkeiten (Art. 30) und
   technisch-organisatorische Maßnahmen (Art. 32) für eine Privatperson nötig?
5. Auftragsverarbeitungsvertrag mit dem Hoster; Drittlandbezug über die an Geräte verteilten DNS-Server?
6. Datenpannen (Art. 33/34): Welcher Ablauf ist angemessen?
