# Rechtstexte Kursportal (ENTWÜRFE)

Stand: 28.10.2026 · Auftrag von Bony („Rechtstexte … Entwürfe“). **Das sind Entwürfe, keine Rechtsberatung.** Eine
Fachperson (Datenschutz/IT-Recht) muss sie prüfen, bevor sie unter `kurse.bony23.de` veröffentlicht werden.

Verantwortlicher ist Bony **privat**. Name, Anschrift und Kontaktadresse stehen als Platzhalter in `<…>` und werden
von Bony **nicht im Repository**, sondern direkt in der Veröffentlichung eingetragen.

| Datei | Zweck | Wann nötig |
|---|---|---|
| [datenschutzerklaerung.md](datenschutzerklaerung.md) | Information nach Art. 13 DSGVO | vor dem ersten Einreicher-Token, ab Release 0.28.0 verlinkbar |
| [impressum.md](impressum.md) | Anbieterkennzeichnung | wenn die Seite öffentlich erreichbar ist |
| [einreichungsbedingungen.md](einreichungsbedingungen.md) | Rechte und Pflichten der Einreichenden | vor dem ersten Einreicher-Token |
| [meldeweg.md](meldeweg.md) | Meldung rechtswidriger Inhalte, Ablauf | vor dem ersten Einreicher-Token |

Technische Grundlage: `docs/dev/datenschutz-kursportal.md` (Datenflüsse), `packaging/kursportal-server/README.md` (Löschen).

## Offene Fragen an die Fachperson
1. Reicht für den Katalogabruf berechtigtes Interesse (Art. 6 Abs. 1 lit. f) plus Information, oder ist Einwilligung nötig?
   (In der App ist die Quelle bis zu einer ausdrücklichen Zustimmung abgeschaltet.)
2. Ist ein hashverketteter Verlauf mit Token-Namen zulässig, wenn die Löschung auf Anfrage möglich bleibt?
3. Genügt die Lizenz CC BY-SA 4.0 für Einreichungen, auch bei anonymen oder pseudonymen Einreichenden?
4. Welche Haftungsprivilegien greifen (DDG/DSA), und genügt der Meldeweg?
5. Ist ein Auftragsverarbeitungsvertrag mit dem Hoster nötig und vorhanden?
