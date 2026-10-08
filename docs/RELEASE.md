# Neue Version veröffentlichen – und Updates einrichten

Diese Anleitung erklärt Schritt für Schritt, was einmalig eingerichtet werden muss, damit
Bony's Agents sich selbst aktualisieren kann, und wie danach jede neue Version veröffentlicht wird.

Es gibt **zwei Schlüsselpaare**. Jedes besteht aus einem *geheimen* Teil (nur für GitHub, niemals
weitergeben, niemals ins Repository) und einem *öffentlichen* Teil (darf jeder sehen, steckt im Programm):

| Schlüssel | Wofür | Geheimer Teil | Öffentlicher Teil |
|---|---|---|---|
| **minisign** | signiert die Liste der Prüfsummen (`SHA256SUMS`). Die App prüft das vor **jedem** Update – Linux und Windows. | GitHub-Secret `MINISIGN_SECRET_KEY` | in `src/bonys_agents/__init__.py` → `UPDATE_PUBLIC_KEY` |
| **GPG** | signiert die APT-Paketquelle. `apt` prüft das, wenn die Aktualisierungsverwaltung (Mint, Ubuntu, Debian) Updates holt. | GitHub-Secrets `APT_GPG_PRIVATE_KEY` und `APT_GPG_PASSPHRASE` | Datei `packaging/linux/bonys-agents-archive-keyring.asc` |

Fehlt etwas davon, baut die Pipeline trotzdem ein Release – nur eben ohne Signatur bzw. ohne
Paketquelle (es erscheint eine Warnung). Die App installiert **nie** ein unsigniertes Update.

---

## Einmalig: Vorbereitung

### 1. Repository festlegen

In `src/bonys_agents/__init__.py` steht:

```python
UPDATE_REPO = "DEIN-GITHUB-NAME/bonys-agents"
```

Dort den echten Namen eintragen, also `Besitzer/Repository` – so, wie er in der Adresse auf GitHub
steht (`https://github.com/Besitzer/Repository`). Daraus ergibt sich automatisch auch die Adresse der
APT-Paketquelle: `https://besitzer.github.io/Repository/apt/`.

### 2. minisign-Schlüssel erzeugen (für die Update-Prüfung in der App)

Im Terminal (Linux Mint/Ubuntu/Debian):

```bash
sudo apt install minisign
mkdir -p ~/bonys-schluessel && cd ~/bonys-schluessel
minisign -G -W -p bonys-agents-minisign.pub -s bonys-agents-minisign.key
```

`-W` heißt: ohne Passwort. Das ist hier richtig, denn der Schlüssel liegt später nur als geschütztes
GitHub-Secret vor, und die Pipeline kann kein Passwort eintippen.

Jetzt gibt es zwei Dateien:

- `bonys-agents-minisign.pub` – **öffentlich**. Die zweite Zeile (beginnt mit `RW…`) kopieren und in
  `src/bonys_agents/__init__.py` eintragen:

  ```python
  UPDATE_PUBLIC_KEY = "RW…die ganze Zeile…"
  ```

- `bonys-agents-minisign.key` – **geheim**. Gleich in Schritt 4 als Secret hinterlegen.

> **Sicherung!** Beide Dateien zusätzlich an einem sicheren Ort aufbewahren (z. B. USB-Stick im
> Schrank, Passwort-Manager). Geht der geheime Schlüssel verloren, können installierte Versionen
> neue Updates nicht mehr prüfen – dann müssten alle Nutzer die nächste Version von Hand installieren.

### 3. GPG-Schlüssel erzeugen (für die APT-Paketquelle)

```bash
gpg --quick-gen-key "Bony's Agents Paketquelle <bonys-agents@users.noreply.github.com>" rsa4096 sign never
```

GPG fragt nach einer **Passphrase** – ein gutes, langes Passwort ausdenken und notieren
(z. B. im Passwort-Manager). Danach den Fingerabdruck anzeigen:

```bash
gpg --list-secret-keys --keyid-format long "Bony's Agents Paketquelle"
```

Die lange Zeichenkette aus 40 Zeichen unter `sec` ist der Fingerabdruck. Damit:

```bash
FPR=HIER-DEN-FINGERABDRUCK-EINFÜGEN
cd ~/bonys-schluessel
gpg --armor --export-secret-keys "$FPR" > apt-geheim.asc         # geheim – für GitHub
gpg --armor --export "$FPR" > bonys-agents-archive-keyring.asc   # öffentlich – ins Repository
```

Die öffentliche Datei ins Projekt kopieren (das `.deb` bringt sie mit und richtet damit die
Paketquelle ein):

```bash
cp ~/bonys-schluessel/bonys-agents-archive-keyring.asc  <Projektordner>/packaging/linux/
```

### 4. Secrets bei GitHub anlegen

Auf GitHub im Repository: **Settings → Secrets and variables → Actions → New repository secret**.
Drei Secrets anlegen (Name genau so schreiben):

| Name | Inhalt |
|---|---|
| `MINISIGN_SECRET_KEY` | kompletter Inhalt von `bonys-agents-minisign.key` (`cat ~/bonys-schluessel/bonys-agents-minisign.key`, alles kopieren) |
| `APT_GPG_PRIVATE_KEY` | kompletter Inhalt von `apt-geheim.asc` (mit den Zeilen `-----BEGIN …` und `-----END …`) |
| `APT_GPG_PASSPHRASE` | die Passphrase aus Schritt 3 |

Danach die Datei `apt-geheim.asc` löschen (`rm ~/bonys-schluessel/apt-geheim.asc`) – der GPG-Schlüssel
bleibt in deinem Schlüsselbund, und gesichert hast du ihn ja.

### 5. GitHub Pages einschalten (für die APT-Paketquelle)

1. **Settings → Pages → Build and deployment → Source:** „GitHub Actions“ wählen.
2. **Settings → Environments → github-pages → Deployment branches and tags:** eine Regel hinzufügen,
   Typ **Tag**, Muster **`v*`**. (Sonst darf ein Release-Tag die Seite nicht veröffentlichen.)

### 6. Änderungen committen

`UPDATE_REPO`, `UPDATE_PUBLIC_KEY` und `packaging/linux/bonys-agents-archive-keyring.asc` committen und
pushen. Ab der **nächsten** Version, die mit diesen Schlüsseln gebaut wurde, funktionieren Updates.
Ältere installierte Versionen ohne Schlüssel zeigen zwar „Version X ist verfügbar“, installieren
aber nichts – dort einmal die neue Version von Hand installieren.

### 7. Optional: macOS-App signieren und notarisieren (Apple-Developer-ID)

Ohne diesen Schritt wird die Mac-App **ad-hoc** signiert. Sie läuft genauso, aber macOS fragt beim
ersten Start einmal nach (Anleitung für Nutzer: README, Abschnitt „macOS → Erster Start“).

Mit einem **Apple-Developer-Konto** (Apple Developer Program, 99 € bzw. 99 US-$ pro Jahr) signiert die
Pipeline mit einer *Developer ID* und lässt die `.dmg` von Apple **notarisieren** (automatische
Schadsoftware-Prüfung). Dann öffnet sich die App per Doppelklick ohne Rückfrage.

1. Auf <https://developer.apple.com/account> → *Certificates* ein Zertifikat **„Developer ID Application“**
   anlegen (Zertifikatsanfrage aus der Schlüsselbundverwaltung eines Macs), herunterladen, im Schlüsselbund
   doppelklicken und dort samt privatem Schlüssel als `.p12` exportieren (mit Passwort).
2. Auf <https://account.apple.com> → *Anmeldung und Sicherheit* → **App-spezifisches Passwort** erzeugen.
3. Diese Secrets anlegen (wie in Schritt 4):

| Name | Inhalt |
|---|---|
| `APPLE_CERT_P12` | die `.p12`-Datei als base64: `base64 -i zertifikat.p12 \| pbcopy` (Mac) bzw. `base64 -w0 zertifikat.p12` (Linux) |
| `APPLE_CERT_PASSWORD` | das Passwort der `.p12`-Datei |
| `APPLE_ID` | die E-Mail-Adresse des Apple-Accounts |
| `APPLE_TEAM_ID` | die Team-ID (10 Zeichen, steht unter *Membership details*) |
| `APPLE_APP_PASSWORD` | das app-spezifische Passwort aus Schritt 2 |

Fehlen die Secrets, läuft der Build trotzdem durch (ad-hoc). Signiert wird mit `packaging/macos/sign.sh`,
notarisiert mit `xcrun notarytool` (Schritt „Notarisieren“ im Release-Workflow).

---

## Jede neue Version

1. Version in `src/bonys_agents/__init__.py` erhöhen (`__version__ = "0.9.0"`), Tests laufen lassen
   (`pytest`, `ruff check src tests`), committen und pushen. Warten, bis die Aktion **CI** grün ist.
2. Tag anlegen und pushen:

   ```bash
   git tag v0.9.0
   git push origin v0.9.0
   ```

3. Die Aktion **Release** (`.github/workflows/release.yml`) erledigt den Rest:
   - baut `.deb` (amd64 und arm64), Windows-Setup und je eine macOS-`.dmg` für Apple-Chip und Intel,
   - hängt die `.dmg` testweise auf einem Mac der passenden Art ein, startet die App (Kommandozeile,
     Desktop-App ohne Bildschirm und im Finder), installiert QEMU über Homebrew und startet testweise
     einen Agent-PC, bis QEMU läuft (`bonys-agents selftest --boot`),
   - installiert das `.deb` testweise in **Debian 13** und **Ubuntu 24.04** und führt dort
     `bonys-agents selftest` aus,
   - erzeugt `SHA256SUMS`, signiert sie mit minisign (vertrauenswürdiger Kommentar
     „Bony's Agents v0.9.0“) und prüft die Signatur gegen den Schlüssel im Programm,
   - veröffentlicht alles auf der Release-Seite,
   - baut die signierte APT-Paketquelle und veröffentlicht sie auf GitHub Pages.

Vorversionen (Tag z. B. `v0.9.0-rc.1`, auf GitHub als „Pre-release“ markiert) bekommen nur Nutzer,
die in der App „Testversionen anbieten“ eingeschaltet haben.

## Prüfen, ob alles klappt

```bash
# Signatur eines Releases von Hand prüfen
minisign -Vm SHA256SUMS -P "RW…öffentlicher Schlüssel…"
sha256sum -c SHA256SUMS --ignore-missing

# Paketquelle (nach Installation des .deb)
cat /etc/apt/sources.list.d/bonys-agents.sources
sudo apt update          # darf für „bonys-agents“ keinen Fehler zeigen
apt policy bonys-agents  # zeigt die Version aus der Paketquelle
```

Lokal lässt sich die Paketquelle auch ohne GitHub bauen:
`packaging/linux/build-apt-repo.sh dist /tmp/apt-test` (signiert mit deinem Standard-GPG-Schlüssel).
