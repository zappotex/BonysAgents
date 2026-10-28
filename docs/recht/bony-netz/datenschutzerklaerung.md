# Datenschutzerklärung Bony-Netz und Kursraum – ENTWURF

> Entwurf, keine Rechtsberatung – vor Veröffentlichung von einer Fachperson prüfen lassen.
> Vorschlag: Diesen Teil mit der Datenschutzerklärung des Kursportals (`docs/recht/kursportal/`) zu **einer** Seite
> unter `https://kurse.bony23.de/datenschutz` zusammenführen – diese Adresse verlinkt die App bereits.

## 1. Verantwortlicher
<NAME>, <ANSCHRIFT>, E-Mail: <KONTAKT-E-MAIL>

## 2. Worum es geht
Das Bony-Netz verbindet die Agent-PCs einer Installation von Bony's Agents über das Internet und stellt Kursräume für
Schulungen bereit. Es besteht aus
- der **Zentrale** (`zentrale.bony23.de`): Anmeldung, Geräteschlüssel, Kurse;
- dem **Netz** (`vpn.bony23.de`, Headscale mit eigenem Relay): verbindet die Geräte per WireGuard;
- dem **Kursraum-Server** (`kurs.bony23.de`, LiveKit): Bild, Ton, Bildschirm und Chat in Kursen.

Die App nutzt das Bony-Netz nur, wenn du es unter „Bony-Netz …“ einschaltest. Ausgeschaltet nimmt sie keinen Kontakt auf.
Wer einen **eigenen** Bony-Netz-Server betreibt, ist für ihn selbst verantwortlich.

## 3. Welche Daten verarbeitet werden

| Was | Wann | Gespeichert? | Wie lange |
|---|---|---|---|
| IP-Adresse, Zeitpunkt | bei jeder Anfrage an Zentrale, Netz und Kursraum | Die Zentrale führt **kein Zugriffsprotokoll**. Für die Grenze „Instanzen pro Anschluss und Tag“ speichert sie einen Hash aus IP-Adresse und einem geheimen Wert | 24 Stunden |
| Instanz (zufällige Kennung, Zugangs-Token nur als Hash) | beim Anlegen | ja – ohne Namen oder E-Mail | bis du die Instanz löschst |
| Geräte im Netz: Gerätename, Netzadresse (100.x), öffentliche Adresse und Port der Verbindung, Systemangaben von Tailscale, „zuletzt online“ | solange ein Agent-PC oder dein Rechner im Netz ist | ja (Headscale) | bis das Gerät oder die Instanz gelöscht wird |
| Kurs: Kursname, Name der Kursleitung, Kurscode (nur Kursleitung), Zeitpunkte | beim Anlegen eines Kurses | ja | beendete Kurse werden nach 30 Tagen gelöscht; ein Kurs endet von selbst 7 Tage nach Ablauf seines Kurscodes |
| Teilnahme: dein Anzeigename, der gewählte Agent-PC (Name, Netzadresse), Beitrittszeit | beim Beitritt | ja | bis du austrittst, entfernt wirst oder der Kurs endet |
| Fortschritt im Kurspaket: Lektion und „geschafft / noch nicht“ | während eines Kurses mit Kurspaket | ja, nur für die Kursleitung sichtbar, solange der Kurs läuft | bis der Kurs endet |
| Kurspaket des Kurses | wenn die Kursleitung eines hochlädt | ja | bis der Kurs endet |
| Bild, Ton, Bildschirm, Chat | nur im Kursraum und nur, was du einschaltest | **nein** – der Kursraum-Server leitet weiter, zeichnet nichts auf | – |
| Hilfe-Funktion: Netzadresse und Einmal-Passwort der Bildschirmfreigabe | nur nach deiner Zustimmung | nein – geht über den Kursraum-Server an die Kursleitung | gilt nur für diese Sitzung |

Verschlüsselung: Zwischen deinen Geräten im Netz Ende-zu-Ende (WireGuard) – der Server kann diesen Verkehr nicht lesen.
Bild, Ton und Chat im Kursraum sind auf dem Weg verschlüsselt, laufen aber **über den Kursraum-Server** (nicht
Ende-zu-Ende).

## 4. Zweck und Rechtsgrundlage
- Bereitstellung von Netz und Kursen, die du nutzt: Art. 6 Abs. 1 lit. b DSGVO.
- Schutz vor Missbrauch (Grenzen, 24-Stunden-Hash): Art. 6 Abs. 1 lit. f DSGVO (berechtigtes Interesse am sicheren
  Betrieb).
- Kamera und Mikrofon schaltest du selbst ein: <Einordnung durch die Fachperson – Einwilligung, Art. 6 Abs. 1 lit. a?>

## 5. Wer die Daten sieht
- Die **Kursleitung** sieht in ihrem Kurs die Anzeigenamen, die gewählten Agent-PCs und – solange der Kurs läuft – den
  Fortschritt. Mit deiner Zustimmung sieht sie über die Hilfe-Funktion den Bildschirm deines Agent-PCs.
- **Andere Teilnehmende** sehen im Kursraum deinen Anzeigenamen und, was du freigibst (Bild, Ton, Chat).
- Wir geben keine Daten an Dritte weiter. Siehe auch Abschnitt 7 (Hoster).
- Bitte schneide den Kursraum nicht mit. Technisch können wir Aufnahmen auf den Rechnern der Teilnehmenden nicht verhindern.

## 6. Cookies, Tracking
Keine Cookies, keine Analyse, keine Werbung.

## 7. Hoster
Der Server wird bei <HOSTER, ANSCHRIFT> betrieben. Vertrag zur Auftragsverarbeitung: <ja/nein – prüfen>.
Serverstandort: <LAND>. Der Hoster kann technisch bedingt Verbindungsdaten verarbeiten.

## 8. Deine Rechte
Auskunft (Art. 15), Berichtigung (16), Löschung (17), Einschränkung (18), Datenübertragbarkeit (20), Widerspruch (21)
und – wenn du eingewilligt hast – Widerruf mit Wirkung für die Zukunft. Deine Instanz samt Geräten, Kursen und
Teilnahmen löschst du jederzeit selbst in der App („Bony-Netz …“ → „Instanz löschen …“). Kontakt: <KONTAKT-E-MAIL>.
Du kannst dich bei einer Datenschutz-Aufsichtsbehörde beschweren.

## 9. Minderjährige
<Fachperson: Kurse für Minderjährige – Art. 8 DSGVO, Einwilligung der Eltern für Kamera/Mikrofon?>
