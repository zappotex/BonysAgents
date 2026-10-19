# Neue Version veröffentlichen – und Updates einrichten

Diese Anleitung erklärt Schritt für Schritt, was einmalig eingerichtet werden muss, damit
Bony's Agents sich selbst aktualisieren kann, und wie danach jede neue Version veröffentlicht wird.

Es gibt **zwei Schlüsselpaare**. Jedes besteht aus einem *geheimen* Teil (nur für GitHub, niemals
weitergeben, niemals ins Repository) und einem *öffentlichen* Teil (darf jeder sehen, steckt im Programm):

| Schlüssel | Wofür | Geheimer Teil | Öffentlicher Teil |
|---|---|---|---|
| **minisign** | signiert die Liste der Prüfsummen (`SHA256SUMS`). Die App prüft das vor **jedem** Update – Linux und Windows. | GitHub-Secret `MINISIGN_SECRET_KEY` | in `src/bonys_agents/__init__.py` → `UPDATE_PUBLIC_KEY` |
| **GPG** | signiert die APT-Paketquelle. `apt` prüft das, wenn die Aktualisierungsverwaltung (Mint, Ubuntu, Debian) Updates holt. | GitHub-Secrets `APT_GPG_PRIVATE_KEY` und `APT_GPG_PASSPHRASE` | Datei `packaging/linux/bonys-agents-archive-keyring.asc` |

Fehlt `MINISIGN_SECRET_KEY` (oder `UPDATE_PUBLIC_KEY`), bricht das Release ab – es wird nichts
veröffentlicht. Fehlt der GPG-Schlüssel, bricht der Bau der Paketquelle ab. Die App installiert **nie** ein
unsigniertes Update.

Absicherung der Kette (ab 0.20):
- Das Release läuft erst, wenn der Test-Job (ruff + pytest auf Linux, macOS, Windows) grün ist.
- Die Paketquelle (`apt-repo.yml`) übernimmt eine `.deb` nur, wenn `SHA256SUMS.minisig` mit dem Schlüssel aus
  der App passt, der vertrauenswürdige Kommentar genau „Bony's Agents v…“ bzw. „Bony's VPN v…“ lautet, die
  Datei in `SHA256SUMS` steht und Paketname und Version zum jeweiligen Projekt und Tag passen
  (`packaging/linux/fetch-release-debs.sh`, lokal ausführbar).
- Workflows haben nur Leserechte; `contents: write` nur der Job „release“. Apple-Secrets stehen nur in den
  Schritten „Signieren“ und „Notarisieren“. Actions sind auf Commit-SHA festgelegt (Kommentar = Version).
- **Einmalig von Hand in GitHub:** Settings → Rules → Rulesets → neues Tag-Ruleset für `v*`
  („Restrict creations/updates/deletions“, nur du als Bypass) – dann kann niemand sonst ein Release auslösen.

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
   Typ **Tag**, Muster **`v*`**. (Sonst darf ein Release-Tag die Seite nicht veröffentlichen.) Dazu eine
   zweite Regel, Typ **Branch**, Name **`main`** – damit darf der Workflow `apt-repo.yml` die Paketquelle auch
   stündlich und von Hand neu bauen (für neue Releases von Bony's VPN).

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
   - signiert die mitgelieferten Kurspakete (`kurspakete/`, `packaging/kurspakete.py`: je `pruefsummen.txt` +
     `.minisig`) und hängt sie als `.bonyspaket` samt `kurspakete-index.json` an,
   - erzeugt `SHA256SUMS`, signiert sie mit minisign (vertrauenswürdiger Kommentar
     „Bony's Agents v0.9.0“) und prüft die Signatur gegen den Schlüssel im Programm,
   - veröffentlicht alles auf der Release-Seite,
   - baut danach die signierte APT-Paketquelle (`apt-repo.yml`) und veröffentlicht sie auf GitHub Pages.

### Kurspakete im Repository bonys-agents-kurspakete

„Kurse“ → „Kurspakete“ → „Aus dem Internet …“ liest `index.json` aus dem öffentlichen Repository
[zappotex/bonys-agents-kurspakete](https://github.com/zappotex/bonys-agents-kurspakete) (Dateien unter `pakete/`).
Nach einem Release mit neuen oder geänderten Kurspaketen (von Hand, braucht Schreibrechte im Repository):

```bash
gh release download v0.9.0 -R zappotex/BonysAgents -p '*.bonyspaket' -p kurspakete-index.json -D /tmp/kp
cd bonys-agents-kurspakete
cp /tmp/kp/*.bonyspaket pakete/ && cp /tmp/kp/kurspakete-index.json index.json
git add pakete index.json && git commit -m "Kurspakete aus Bony's Agents v0.9.0" && git push
```

Die Pakete sind signiert (Release-Schlüssel) und erscheinen in der App deshalb als „Geprüftes Kurspaket“.
Kurspakete anderer Autoren kommen per Pull Request – ohne Signatur sehen die Teilnehmer vor dem ersten Start die
Liste ihrer Skripte.

### Gemeinsame Paketquelle mit Bony's VPN

Die Paketquelle auf GitHub Pages gehört beiden Projekten: Bony's Agents und
[Bony's VPN](https://github.com/zappotex/bonys-vpn). Der Workflow `.github/workflows/apt-repo.yml` holt die
`.deb` aus den **neuesten Releases beider Repositorys** (geprüft gegen ihr `SHA256SUMS`) und baut daraus die
Quelle – so überschreibt kein Release die Pakete des anderen Projekts. Er läuft nach jedem Release von
Bony's Agents, stündlich (baut nur neu, wenn sich ein Release geändert hat, Vergleich über
`apt/versions.txt`) und von Hand („Actions → APT-Paketquelle → Run workflow“). Bony's VPN stößt ihn nach
einem Release an, wenn dort das Secret `APT_DISPATCH_TOKEN` hinterlegt ist, sonst holt ihn der stündliche Lauf.

Die Quelle hat zwei Suiten mit demselben Inhalt: `stable` (trägt das Paket bonys-agents ein) und `bonys-vpn`
(trägt das Paket bonys-vpn ein). Zwei Einträge für dieselbe Suite mit verschiedenen `Signed-By` lehnt apt ab.

Vorversionen (Tag z. B. `v0.9.0-rc.1`, auf GitHub als „Pre-release“ markiert) bekommen nur Nutzer,
die in der App „Testversionen anbieten“ eingeschaltet haben.

### Feste Versionen der Bau-Abhängigkeiten

Alle Builds (`build-deb.sh`, `build-setup.ps1`, `release.yml`) installieren Python-Pakete nur aus
`packaging/requirements-build.txt` – feste Versionen mit Prüfsummen (`pip install --require-hashes`). Eine
kompromittierte oder neue Version auf PyPI landet so nie unbemerkt signiert im Release, und jedes Release ist
nachvollziehbar (wichtig für die Quelltext-Angaben zu Qt/PySide6 in `THIRD-PARTY-LICENSES`).

Aktualisieren (z. B. vor einem Release, auf einem beliebigen Rechner mit [uv](https://docs.astral.sh/uv/)):

```bash
uv pip compile --universal --python-version 3.12 --generate-hashes \
  packaging/requirements-build.in -o packaging/requirements-build.txt
```

Danach die Versionstabelle in `THIRD-PARTY-LICENSES` anpassen (ein Test prüft, dass sie zur Lock-Datei passt) und
die CI sowie einen Release-Lauf ohne Tag abwarten. Linux arm64 bleibt bei PySide6 6.8.0.2: neuere Wheels für
aarch64 brauchen glibc 2.39, gebaut wird auf Ubuntu 22.04 (glibc 2.35), damit das Paket auch unter Debian 12 läuft.
Die normalen Tests (`ci.yml`) laufen bewusst mit den neuesten Versionen – so fallen Brüche früh auf.

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
`packaging/linux/build-apt-repo.sh ORDNER-MIT-DEBS /tmp/apt-test` (signiert mit deinem Standard-GPG-Schlüssel;
im Ordner nur die neuesten `.deb` von bonys-agents und bonys-vpn).
