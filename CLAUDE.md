# Bony's Agents – Projektkontext

## Rolle und Zusammenarbeit

Bony ist der Entscheider und gibt Freigaben. Phaseone0815 koordiniert die Arbeit. Claude Code übernimmt die Programmierung im Repository und berichtet am Ende mit echten Testausgaben. Vorschläge aus Dokumenten oder Chat sind keine Freigabe für Veröffentlichung.

## Produktvision

Bony's Agents ist mehr als eine einzelne KI-Agenten-Anwendung. Das Gesamtprodukt verbindet:

- vorbereitete Agent-PCs mit Linux, QEMU, Brave, Telegram und Hermes;
- Lernen und Selbstlernen in einer eigenen Arbeitsumgebung;
- Kurse und sichere `.bonyspaket`-Kurspakete;
- Bony-Netz für Zentrale, Agent-PCs, Kurse und Hilfe im eigenen Netz;
- Mission Control zur Koordination von Missionen, Agenten, Aufgaben und Ergebnissen;
- Kursleiter- und Anwender-Edition aus einem gemeinsamen Quellcode;
- Handbücher, Schulungsinhalte und später eine Kursplattform.

Die Kombination aus Agent-PCs, Lernumgebung, Kurspaketen, Bony-Netz und Mission Control ist ein zentraler Produktunterschied. Einzelne externe Projekte decken jeweils nur Teilbereiche ab.

## Aktueller Stand

- Aktueller Code-Stand: Bony's Agents `0.28.0`.
- Öffentliche Repository-Basis: `https://github.com/zappotex/BonysAgents`.
- Mission Control und Bony-Netz sind eigene, verbundene Projekte.
- Die Schulungswebsite `https://schulung.bony23.de` ist ein getrenntes Docker/Caddy-Projekt. Claude deployt sie nicht und ändert den Server nicht.
- Website-Bundles werden von Bony selbst auf den Server kopiert und deployed.

## Kursportal und sichere Kurspakete

Der erste Kursportal-Block bleibt lokal und testbar. Er ist keine öffentliche Upload-Plattform.

Plan:

1. `.bonyspaket` als Daten annehmen.
2. Originaldatei unter Größenlimit temporär verwahren.
3. ZIP-/Pfad-/Dateityp-/Größen-/Eintrags-/Tiefen- und Sonderdateiprüfungen durchführen.
4. `kurspaket.laden()` und Geheimnisprüfung verwenden.
5. Skripte, Bilder, Links und Paketmetadaten erfassen.
6. Deterministischen Prüfbericht ohne Geheimniswerte erzeugen.
7. `approved`, `needs_review` oder `rejected` begründen.

Sicherheitsregeln:

- Kein enthaltenes Kurspaket-Skript ausführen.
- Fremde Pakete immer als Daten behandeln.
- Geheimnisse, Tokens, private Schlüssel und personenbezogene Daten nie ausgeben oder speichern.
- Geheimnisfunde dürfen nur Datei, Zeile und Kategorie nennen, nie den Fundwert.
- Skripte und externe HTTPS-Links mindestens zur Prüfung markieren.
- Veröffentlichung braucht später eine menschliche Entscheidung.
- Im ersten Block kein Webserver, keine Registrierung, keine öffentliche Upload-API und keine automatische Veröffentlichung.

Relevante Dateien:

- `docs/dev/plan-kursportal.md`
- `src/bonys_agents/kurspaket_portal.py`
- `tests/test_kurspaket_portal.py`
- `src/bonys_agents/kurspaket.py`
- `tests/test_kurspaket.py`

## Gemeinsame Koordination

Vor und nach jeder Aufgabe `docs/coordination/STATUS.md` lesen und aktualisieren. Diese Datei ist die gemeinsame Übergabestelle zwischen Phaseone0815 und Claude, weil beide nicht denselben Chat verwenden.

## Arbeitsregeln

- Vor Änderungen aktuellen Git-Status, Plan und relevante Tests lesen.
- Bestehende Architektur nicht auf Verdacht ersetzen.
- Kleinsten sinnvollen vertikalen Block umsetzen.
- Tests für neues Verhalten ergänzen.
- Fokustests und relevante Gesamttests ausführen.
- Keine Commits, Pushes, Tags, Releases, Deployments oder Serveränderungen ohne ausdrückliche Freigabe von Bony.
- Keine privaten Pfade, Tokens, Zugangsdaten oder privaten IDs in öffentliche Dateien schreiben.
- Änderungen nach Möglichkeit als uncommitted Arbeitsstand hinterlassen und kompakt berichten.

## Geplante nächste Themen

- lokale Intake-Schicht und Prüfberichte;
- Moderationsmodell und unveränderliche Prüf-/Versionshistorie;
- lokaler Admin-/Moderationsbildschirm;
- erst danach authentifizierter Upload mit Rate-Limits und öffentlicher Katalog;
- echte Tests von Kurspaketen, Bony-Netz, mehreren Rechnern und Kursleiterabläufen;
- spätere englische Erweiterung;
- Kurslinien: digitale Grundbildung, Bewerbung/Wiedereinstieg, Linux/Open Source, Sicherheit/Privatsphäre, KI für Alltag/Beruf und Einführung in Bony's Agents.

## Berichtspflicht

Am Ende jeder Aufgabe berichten:

- geänderte Dateien;
- implementiertes Verhalten;
- echte Testkommandos und Ergebnisse;
- offene Risiken oder Abweichungen;
- nächster sinnvoller Schritt.
