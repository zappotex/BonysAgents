# Mitmachen bei Bony's Agents

Schön, dass du helfen willst!

## Beitragsvereinbarung (CLA) – bitte zuerst lesen

Bony's Agents steht unter der **GPL-3.0-or-later** und wird zusätzlich unter **kommerziellen
Lizenzen** angeboten (Doppel-Lizenz). Beiträge kann ich deshalb **nur annehmen, wenn du der
[Beitragsvereinbarung (CLA)](CLA.md) zustimmst**. Sie erlaubt mir, deinen Beitrag auch unter
einer kommerziellen Lizenz weiterzugeben; dein Urheberrecht behältst du, und angenommene
Beiträge bleiben immer auch unter der GPL frei verfügbar.

So stimmst du zu: Schreib in deinen ersten Pull Request den Satz aus Abschnitt 7 der
[CLA.md](CLA.md). Ohne diese Zustimmung kann ich den Pull Request leider nicht übernehmen.

Neue Python-Dateien beginnen mit der Zeile `# SPDX-License-Identifier: GPL-3.0-or-later`.

## Entwicklungsumgebung

```bash
git clone https://github.com/zappotex/BonysAgents
cd BonysAgents
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
ruff check src tests
```

## Ein neues Programm hinzufügen

In `src/bonys_agents/apps.py` einen weiteren `AppSpec` anlegen:

```python
VSCODIUM = AppSpec(
    id="vscodium",
    name="VSCodium",
    description="Code-Editor ohne Telemetrie",
    install=r"""
apt-get install -y codium
""",
    default=False,
)
```

und in `APPS` eintragen. Das Snippet läuft im Gast als root; `$AGENT_USER`,
`$AGENT_HOME` und `$DESKTOP_DIR` stehen zur Verfügung. Es muss auf x86_64 **und**
ARM64 funktionieren.

## Regeln

- Programme nur aus offiziellen Quellen installieren
- Kein Code, der Daten ohne Zustimmung nach außen sendet
- Texte in der Oberfläche auf Deutsch
- Neue Funktionen bitte mit Tests (`tests/`)
