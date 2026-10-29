# SPDX-License-Identifier: GPL-3.0-or-later
"""„Agenten-Apps“: offline lesbare Liste von Programmen mit MCP-Server auf dem Schreibtisch des Agent-PCs.

Einzige Quelle ist ``agent-apps/agent-apps.yaml`` im Repository (im Programm unter ``resources/agent-apps``).
Bony's Agents installiert die Programme der Liste NICHT – der Nutzer (oder sein Hermes-Agent) entscheidet selbst.
Im Gast erzeugt ``build_agent_apps.py`` (braucht nur python3-yaml) die Seite mit den echten Pfaden des
Agent-Benutzers; die Online-Version baut der Pages-Workflow aus derselben Liste.
"""

from __future__ import annotations

from pathlib import Path

from bonys_agents.i18n import n_, tr

APP_ID = "agenten-apps"
GUEST_DIR = "/usr/share/bonys-agents/agenten-apps"
PAGE = f"{GUEST_DIR}/index.html"
LAUNCHER = "agenten-apps.desktop"
# Erzeugt die Seite neu (z. B. nachdem n8n dazukam) – als root, ohne Argumente
REBUILD = "/usr/local/bin/bonys-agenten-apps"
WORK_DIR = "Agent-Dateien"
WORK_DIR_EN = "Agent-Files"   # englischer Agent-PC (agent-apps.en.yaml ersetzt den Ordner in allen Befehlen)
TRANSLATION = "agent-apps.en.yaml"
FILES = ("agent-apps.yaml", TRANSLATION, "build_agent_apps.py", LAUNCHER)
# Einträge unter „vorinstalliert“ → woran man im Gast (als root) erkennt, dass sie wirklich da sind
INSTALLED_CHECKS = {"n8n": "docker container inspect n8n"}


def source_dir() -> Path:
    """Ordner mit der Liste: im Programm (``resources/agent-apps``), im Quellcode ``agent-apps/``."""
    here = Path(__file__).resolve().parent
    for cand in (here / "resources" / "agent-apps", here.parent.parent / "agent-apps"):
        if (cand / "agent-apps.yaml").is_file():
            return cand
    raise FileNotFoundError(tr("Die Liste „Agenten-Apps“ (agent-apps.yaml) fehlt im Programm."))


def _heredoc(path: str, text: str, delim: str) -> str:
    if any(line.strip() == delim for line in text.splitlines()):
        raise ValueError(tr("{path} enthält die Endmarke {delim}", path=path, delim=delim))
    return f"cat > {path} <<'{delim}'\n{text.rstrip(chr(10))}\n{delim}\n"


def install_script() -> str:
    """App-Schritt (als root im Gast, $AGENT_USER/$AGENT_HOME/$DESKTOP_DIR gesetzt)."""
    src = source_dir()
    parts = [
        "\napt-get install -y python3 python3-yaml xdg-utils",
        f"install -d -m 0755 {GUEST_DIR}",
    ]
    for i, name in enumerate(FILES):
        parts.append(_heredoc(f"{GUEST_DIR}/{name}", (src / name).read_text("utf-8"), f"BONYS_AA_{i}"))
    checks = "\n".join(
        f'{c} >/dev/null 2>&1 && DA="$DA,{i}"' for i, c in INSTALLED_CHECKS.items())
    parts.append(r"""chmod 644 """ + GUEST_DIR + r"""/*
cat > """ + REBUILD + r""" <<EOF
#!/bin/sh
# Von Bony's Agents: Seite „Agenten-Apps“ neu erzeugen (echte Pfade, unter „Schon dabei“ nur Installiertes),
# in der Sprache des Agent-PCs (/etc/default/locale)
set -e
DA=""
""" + checks.replace("$", r"\$") + r"""
UEB=""
case "\$(unset LANG; [ -r /etc/default/locale ] && . /etc/default/locale; echo "\${LANG:-}")" in
  de*|"") ;;
  *) UEB="--uebersetzung """ + GUEST_DIR + "/" + TRANSLATION + r"""" ;;
esac
# shellcheck disable=SC2086
python3 """ + GUEST_DIR + r"""/build_agent_apps.py """ + GUEST_DIR + r"""/agent-apps.yaml """ + PAGE + r""" \
  --home '$AGENT_HOME' --installiert "\${DA#,}" \$UEB
chmod 644 """ + PAGE + r"""
EOF
chmod 755 """ + REBUILD + r"""
""" + REBUILD + r"""
install -m 0644 """ + GUEST_DIR + "/" + LAUNCHER + " /usr/share/applications/" + LAUNCHER + r"""
cp /usr/share/applications/""" + LAUNCHER + r""" "$DESKTOP_DIR/"
chown "$AGENT_USER:$AGENT_USER" "$DESKTOP_DIR/""" + LAUNCHER + r""""
chmod 755 "$DESKTOP_DIR/""" + LAUNCHER + r""""
if [ "${AGENT_LANG:-de}" = de ]; then W=""" + WORK_DIR + r"""; else W=""" + WORK_DIR_EN + r"""; fi
install -d -o "$AGENT_USER" -g "$AGENT_USER" -m 0755 "$AGENT_HOME/$W"
""")
    return "\n".join(parts)


# Nach dem Installieren/Entfernen einer „vorinstallierten“ App (z. B. n8n): Seite auffrischen, falls vorhanden
REFRESH = f"[ -x {REBUILD} ] && {REBUILD} || true\n"


def _install_or_error() -> str:
    """Fehlt die Liste im Programm (kaputte Installation), bricht nur dieser Schritt mit klarer Meldung ab."""
    try:
        return install_script()
    except (OSError, ValueError) as exc:
        msg = str(exc).replace("'", "")
        return f"\necho 'FEHLER: {msg}' >&2\nexit 1\n"


def app_spec():
    from bonys_agents.apps import AppSpec

    return AppSpec(
        id=APP_ID,
        name=n_("Agenten-Apps (Liste)"),
        description=n_("Liste auf dem Schreibtisch mit Programmen, die dein Hermes-Agent über MCP selbst bedienen "
                       "kann – mit Installationsbefehlen von den offiziellen Seiten, offline lesbar"),
        weight=1.5,
        check=f"test -s {PAGE} && {{ test -d \"$HOME/{WORK_DIR}\" || test -d \"$HOME/{WORK_DIR_EN}\"; }}",
        launcher=LAUNCHER,
        install=_install_or_error(),
    )
