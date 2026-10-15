# Editionen: Bony's Agents und Bony's Agents Kursleiter

Ab Version 0.19.0 gibt es zwei Editionen aus **einem** Quellcode:

1. **Bony's Agents** – für alle, die Agent-PCs nutzen, und für **Teilnehmer** von Schulungen.
2. **Bony's Agents Kursleiter** – alles aus 1., dazu die Funktionen, um selbst Schulungen zu geben.

Teilnehmer brauchen **nur die normale Version**. Wer zwischen den Editionen wechselt (in beide Richtungen),
behält Agent-PCs, Vorlagen, Bibliotheken und Einstellungen – beide nutzen denselben Datenordner.

## Welche Version brauche ich?

| Du möchtest … | Version |
|---|---|
| eigene Agent-PCs nutzen, Vorlagen und Programme verwalten | **Bony's Agents** |
| an einer Schulung teilnehmen (beitreten, Vorführung ansehen, Hilfe anfordern) | **Bony's Agents** |
| selbst Schulungen geben (Vorlage im Netz freigeben, vorführen, Hilfe-Anfragen annehmen) | **Bony's Agents Kursleiter** |

## Funktion ↔ Edition

| Funktion | Bony's Agents | Kursleiter |
|---|:---:|:---:|
| Agent-PCs erstellen, starten, verwalten, Desktops, Bildschirm, Fernzugriff | ✅ | ✅ |
| Vorlagen erstellen und verwalten, Programme hinzufügen, Bony's VPN, Mission Control, Obsidian | ✅ | ✅ |
| Hintergrundbild der Agent-PCs aktualisieren | ✅ | ✅ |
| Vorlage als `.bonys`-Datei exportieren und importieren | ✅ | ✅ |
| **Teilnehmer:** „Kurs beitreten“ – Freigaben im Netz finden, Code/QR-Inhalt eingeben, Fingerabdruck prüfen, Vorlage laden (`bonys-agents join`) | ✅ | ✅ |
| **Teilnehmer:** Vorführung im Browser öffnen | ✅ | ✅ |
| **Teilnehmer:** „Hilfe anfordern“ mit Zustimmungs-Dialogen (Ansehen / Steuern) und Hinweis, solange zugesehen oder gesteuert wird | ✅ | ✅ |
| **Kursleiter:** Vorlage im Netzwerk freigeben (HTTPS-Server, mDNS-Ankündigung, `bonys-agents share`) | – | ✅ |
| **Kursleiter:** Vorführen (Kurs-Server, WebSocket-Proxy, noVNC, `bonys-agents present`) | – | ✅ |
| **Kursleiter:** Hilfe-Anfragen annehmen, Teilnehmer-Agent-PCs ansehen und (nach Zustimmung) steuern | – | ✅ |
| **Kursleiter:** Dashboard (Stufe 4, geplant) | – | ✅ |
| Hinweis „Du möchtest selbst Schulungen geben? → Bony's Agents Kursleiter“ (Menü ⓘ, „Über“) | ✅ | – |

In der normalen Version fehlen die Kursleiter-Knöpfe und -Menüs ganz. `bonys-agents share` und
`bonys-agents present` melden dort verständlich, dass es sie nur in der Kursleiter-Version gibt (Rückgabe 2).
`--version`, `doctor` und das „Über“-Fenster zeigen Version und Edition, z. B. `bonys-agents 0.19.0 (Anwender)`.

## Technik

- **Ein Quellcode, ein Unterpaket:** Alles nur für Kursleiter liegt in `src/bonys_agents/trainer/`
  (`share_server.py`, `present.py`, `helpdesk.py`, `announce.py`, `cli.py`, `gui/`, `resources/present/`,
  `resources/novnc/`). Die normale Version wird **ohne** diesen Ordner gebaut – kein Server-Code, kein noVNC im
  Paket, nicht nur ausgeblendet. Das Hauptpaket importiert `trainer` nie auf Modulebene, nur hinter
  `edition.IS_TRAINER` (geprüft von `tests/test_editions.py`).
- **Gemeinsam im Hauptpaket:** Kurs-Protokoll und seine Version (`share.PROTOCOL`, `share.check_protocol`),
  Code- und Fingerabdruck-Prüfung, Manifest (`bonysfile`), Teilnehmer-Seite (`share.fetch_info/download`,
  `helpmode.HelpClient`), RFB-Filter (`rfb`), WebSocket (`websocket`), Brücke zum VNC-Socket (`vncbridge`), mDNS-Suche.
- **Kurs-Protokoll:** Kursleiter und Teilnehmer schicken ihre Protokoll-Version mit (`X-Bonys-Protocol`, in den
  Antworten `protocol`). Passt sie nicht, gibt es eine Meldung wie „Kurs-Protokoll passt nicht: Kursleiter
  (Bony's Agents 0.20.0) nutzt Version 2, dieses Programm (Bony's Agents 0.19.0) Version 1. Der Teilnehmer sollte
  Bony's Agents aktualisieren.“ Ohne Angabe (bis 0.18) gilt Version 1 – ältere Teilnehmer bleiben kompatibel.
- **Edition im Programm:** `bonys_agents.edition.EDITION` („anwender“ oder „kursleiter“). Im gebauten Programm steht
  sie fest (`bonys_agents/_edition.py`, schreibt `packaging/bonys-agents.spec` nur während des Bauens). Aus dem
  Quellcode (Entwicklung, `install.sh`) gilt die Kursleiter-Version, weil `trainer/` vorhanden ist; mit
  `BONYS_AGENTS_EDITION=anwender` lässt sich die normale Version simulieren.

## Pakete

| System | Bony's Agents | Bony's Agents Kursleiter | Wechsel |
|---|---|---|---|
| Debian/Ubuntu/Mint | `bonys-agents_VERSION_ARCH.deb` | `bonys-agents-kursleiter_VERSION_ARCH.deb` | Kursleiter: `Provides/Conflicts/Replaces: bonys-agents`, normal: `Conflicts/Replaces: bonys-agents-kursleiter` – Doppelklick auf die andere .deb oder `sudo apt install bonys-agents-kursleiter` bzw. `bonys-agents`. Gleiche Pfade und Befehle, Startmenü „Bony's Agents Kursleiter“. Beide in der APT-Paketquelle. |
| Windows | `BonysAgents-Setup-VERSION.exe` | `BonysAgents-Kursleiter-Setup-VERSION.exe` | Siehe unten |
| macOS | `BonysAgents-VERSION-macos-applesilicon.dmg` / `-intel.dmg` | `BonysAgents-Kursleiter-VERSION-macos-…dmg` | Siehe unten |

**Windows (Inno Setup):** Beide Installer haben **dieselbe AppId**. Für Windows ist es damit ein Programm in zwei
Ausführungen – die andere Edition zu installieren ist wie ein Update: derselbe Ordner (`C:\Program Files\Bony's
Agents`), ein einziger Eintrag unter „Apps“ (Name und Version zeigen die Edition), ein Deinstallationsprogramm.
`[InstallDelete]` löscht vorher die Programmdateien (`_internal`) und die Verknüpfungen der anderen Edition, damit
z. B. keine Kursleiter-Module liegen bleiben. Das ist sauberer als zwei AppIds mit gegenseitigem Deinstallieren
(zwei Einträge, Reihenfolge-Probleme, ein Neustart der Deinstallation mitten im Setup).

**macOS:** Die App heißt in beiden Editionen `Bony's Agents.app` und hat dieselbe Bundle-ID
(`io.github.bonys-agents`). Wer die andere Edition in „Programme“ zieht, ersetzt die bisherige (Finder fragt
„Ersetzen?“); Einstellungen und Berechtigungen hängen an der Bundle-ID und bleiben. Die Edition zeigen der Name der
.dmg und des Laufwerks sowie `CFBundleDisplayName` („Bony's Agents Kursleiter“). Zwei verschiedene Bundle-IDs
würden dagegen zwei Apps nebeneinander erzeugen, die sich Agent-PCs teilen – das wollen wir nicht.

**Updates** bleiben in der eigenen Edition: Die App lädt aus dem gemeinsamen Release nur die Datei ihrer Edition
(`updates.asset_for`), apt aktualisiert nur das installierte Paket.

## Bauen

```
packaging/linux/build-deb.sh               # dist/bonys-agents_…deb
packaging/linux/build-deb.sh kursleiter    # dist/bonys-agents-kursleiter_…deb (holt noVNC)
pyinstaller packaging/bonys-agents.spec -- --edition kursleiter    # oder BONYS_EDITION=kursleiter
python packaging/check-edition.py dist/bonys-agents anwender       # kein trainer/, kein noVNC, Edition fest
```

`packaging\windows\build-setup.cmd` baut beide Windows-Installer, die Release-Aktion alles für alle Plattformen
und hängt es an **ein** Release mit **einer** signierten `SHA256SUMS`.

## Tests

```
PYTHONPATH=src pytest                      # Kursleiter-Version (alles)
PYTHONPATH=src pytest --edition anwender   # Anwender-Version: bonys_agents.trainer lässt sich nicht importieren
```

Tests mit `@pytest.mark.kursleiter` (bzw. die Dateien `test_present.py`, `test_helpmode.py`,
`test_share_server.py`) laufen nur in der Kursleiter-Runde. `tests/test_editions.py` kopiert das Paket ohne
`trainer/` in einen leeren Ordner und prüft dort: alle Module importierbar, CLI und Hauptfenster laufen, keine
Kursleiter-Knöpfe. Die CI führt beide Runden aus, die Release-Aktion prüft die fertigen Pakete mit
`packaging/check-edition.py`.
