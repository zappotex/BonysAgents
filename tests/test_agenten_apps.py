# SPDX-License-Identifier: GPL-3.0-or-later
"""n8n, Software-Center und die Liste „Agenten-Apps“: Apps, Skripte, Dialog-Hinweise und das Build-Skript der Liste
(Pflichtfelder, echte Pfade, Hermes-Eintrag)."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from bonys_agents import agenten_apps, apps, cloudinit, n8n
from bonys_agents.gui.template_dialogs import deletion_text

ROOT = Path(__file__).resolve().parent.parent
LISTE = ROOT / "agent-apps" / "agent-apps.yaml"
yaml = pytest.importorskip("yaml")


def bash_syntax_ok(script: str) -> bool:
    if not sys.platform.startswith("linux"):
        return True
    return subprocess.run(["bash", "-n"], input=script, text=True).returncode == 0


@pytest.fixture(scope="module")
def build():
    spec = importlib.util.spec_from_file_location("build_agent_apps", ROOT / "agent-apps" / "build_agent_apps.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def liste():
    return yaml.safe_load(LISTE.read_text("utf-8"))


# ---------------------------------------------------------------- Liste und Build-Skript
def test_list_is_valid_and_official(build, liste):
    build.check(liste)  # bricht sonst ab
    ids = [a["id"] for a in liste["apps"]]
    assert {"pdfcraft", "photocraft", "wordcraft", "gridcraft", "deckcraft", "cadcraft", "solidcraft"} <= set(ids)
    assert liste["meta"]["online_url"] == "https://zappotex.github.io/BonysAgents/agenten-apps/"
    for a in liste["apps"]:
        assert a["quelle"].startswith("https://") and a["homepage"].startswith("https://")
        # GitHub-Downloads nur aus dem offiziellen Release und mit Prüfsumme
        for line in a["installation"].splitlines():
            if "github.com" in line and "wget" in line:
                assert "/releases/latest/download/" in line, line
        if "SHA256SUMS.txt" in a["installation"]:
            assert "sha256sum --check" in a["installation"], a["id"]


def test_page_with_home_has_real_paths(build, liste):
    page = build.render(liste, "/home/agent", {"n8n"})
    assert "hermes mcp add pdfcraft --command /home/agent/.local/bin/pdfcraft-cli --args mcp --compact --root " \
           "/home/agent/Agent-Dateien/pdf" in page
    assert "&quot;/home/agent/Agent-Dateien/pdf&quot;" in page        # config.yaml-Eintrag (HTML-escaped)
    assert "~/Agent-Dateien/pdf" not in page.split("<details>")[1].split("hermes mcp add")[1].split("</code>")[0]
    assert "Bereits installiert" in page and "localhost:5678" in page
    for a in liste["apps"]:
        assert f">{a['name']}</h2>" in page


def test_page_hides_preinstalled_that_is_missing(build, liste):
    assert "Bereits installiert" not in build.render(liste, "/home/agent", set())
    assert "Bereits installiert" in build.render(liste, None, None)     # Online-Version: alles


def test_online_page_keeps_tilde_for_the_shell(build, liste):
    page = build.render(liste, None)
    # ~/ bleibt ungequotet, damit die Shell es auflöst
    assert "--command ~/.local/bin/pdfcraft-cli --args mcp --compact --root ~/Agent-Dateien/pdf" in page


def test_shell_arg_quotes_but_keeps_tilde(build):
    assert build.shell_arg("~/A B") == "~/'A B'"
    assert build.shell_arg("a;rm -rf /") == "'a;rm -rf /'"
    assert build.expand_home("~", "/home/x") == "/home/x"
    assert build.expand_home("~nobody/x", "/home/x") == "~nobody/x"


@pytest.mark.parametrize("kaputt, meldung", [
    ({"meta": {"titel": "x", "untertitel": "y"}, "apps": []}, "apps: Liste fehlt oder ist leer"),
    ({"meta": {"titel": "x"}, "apps": [{"id": "a"}]}, "Feld 'untertitel' fehlt"),
    ({"meta": {"titel": "x", "untertitel": "y"}, "apps": [{"id": "a", "status": "neu"}]}, "Feld 'mcp' fehlt"),
    ({"meta": {"titel": "x", "untertitel": "y"}, "apps": [{"id": "A"}]}, "id nur aus Kleinbuchstaben"),
    ({"meta": {"titel": "x", "untertitel": "y"}, "vorinstalliert": [{"id": "n8n"}], "apps": [{"id": "a"}]},
     "vorinstalliert #1 (n8n): Feld 'oeffnen' fehlt"),
    (["keine", "liste"], "keine Einträge"),
])
def test_missing_fields_stop_with_clear_message(build, kaputt, meldung):
    with pytest.raises(SystemExit) as exc:
        build.check(kaputt)
    assert meldung in str(exc.value)


def test_cli_exits_nonzero_on_broken_list(tmp_path):
    bad = tmp_path / "liste.yaml"
    bad.write_text("meta: {titel: x}\napps: []\n", "utf-8")
    r = subprocess.run([sys.executable, str(ROOT / "agent-apps" / "build_agent_apps.py"), str(bad),
                        str(tmp_path / "index.html")], capture_output=True, text=True)
    assert r.returncode != 0 and "Fehler in der Liste" in r.stderr
    assert not (tmp_path / "index.html").exists()


# ---------------------------------------------------------------- Apps
def test_new_apps_are_default_and_in_order():
    for i in ("software-center", "n8n", "agenten-apps"):
        assert apps.APPS[i].default, i
    order = list(apps.APPS)
    assert order.index("docker") < order.index("n8n") < order.index("agenten-apps")
    assert apps.dependencies(["n8n"]) == ["brave", "docker"]


def test_agenten_apps_script_carries_the_list():
    script = cloudinit.app_install_script(apps.APPS[agenten_apps.APP_ID], "agent")
    assert bash_syntax_ok(script)
    assert LISTE.read_text("utf-8").rstrip("\n") in script
    assert "python3-yaml" in script and agenten_apps.PAGE in script
    assert "--home '$AGENT_HOME'" in script and '"\\${DA#,}"' in script
    assert 'Agent-Dateien' in script and "/usr/share/applications/agenten-apps.desktop" in script
    assert "docker container inspect n8n" in script


def test_missing_list_only_breaks_its_own_step(monkeypatch):
    monkeypatch.setattr(agenten_apps, "source_dir", lambda: (_ for _ in ()).throw(FileNotFoundError("weg")))
    body = agenten_apps._install_or_error()
    assert "FEHLER: weg" in body and "exit 1" in body


def test_n8n_only_local_with_volume_and_official_image():
    s = n8n.container_script()
    assert bash_syntax_ok(s)
    assert "-p 127.0.0.1:5678:5678" in s and " -p 5678" not in s
    assert "-v n8n_data:/home/node/.n8n" in s
    assert "IMAGE='docker.n8n.io/n8nio/n8n:stable'" in s
    assert "--restart unless-stopped" in s and 'GENERIC_TIMEZONE="$ZONE"' in s and 'TZ="$ZONE"' in s
    install = cloudinit.app_install_script(apps.APPS[n8n.APP_ID], "agent")
    assert bash_syntax_ok(install)
    assert "systemctl enable bonys-n8n.service" in install and agenten_apps.REBUILD in install
    spec = apps.APPS[n8n.APP_ID]
    assert spec.update == "/usr/local/bin/bonys-n8n update" and not spec.redistributable
    assert bash_syntax_ok(spec.uninstall) and "docker volume rm n8n_data" in spec.uninstall


def test_n8n_ram_warning_counts_mission_control():
    assert n8n.resource_warnings(["hermes"], 1024, 2048) == []
    assert n8n.resource_warnings(["n8n"], 4096, 2048) == []
    assert n8n.resource_warnings(["n8n"], 4096, 2048, other_ram_mb=1536)   # mit Mission Control zu knapp
    assert "RAM" in n8n.resource_warnings(["n8n"], 2048, 2048)[0]


def test_n8n_data_leaves_fresh_templates():
    fresh = cloudinit.generalize_script("agent", remove_personal=True)
    clone = cloudinit.generalize_script("agent", remove_personal=False)
    assert "docker volume rm n8n_data" in fresh and "n8n_data" not in clone
    assert n8n.FRESH_CLEANUP in deletion_text("agent", True, workflows=True)
    assert n8n.FRESH_CLEANUP not in deletion_text("agent", True)


def test_software_center_offline_fix():
    script = cloudinit.app_install_script(apps.APPS["software-center"], "agent")
    assert bash_syntax_ok(script)
    assert "GIO_USE_NETWORK_MONITOR=netlink" in script and "/etc/environment" in script
    assert "gnome-software-plugin-flatpak" in script and "download-updates=false" in script
