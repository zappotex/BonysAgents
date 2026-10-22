#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Erzeugt die Seite "Agenten-Apps" für Bony's Agents aus agent-apps.yaml.

Aufruf:
    python3 build_agent_apps.py agent-apps.yaml index.html [--home /home/agent] [--installiert n8n]

--home ersetzt "~" in MCP-Einträgen durch den echten Pfad, weil nicht jeder
MCP-Client "~" selbst auflöst. Ohne --home bleibt "~" stehen (gut für die
Online-Version).
--installiert: kommagetrennte IDs aus "vorinstalliert", die im Agent-PC wirklich
da sind (die anderen fehlen dann auf der Seite). Ohne: alle (Online-Version).

Benötigt nur PyYAML (Debian: python3-yaml). Die erzeugte Seite ist
vollständig eigenständig und funktioniert offline.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import shlex
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML fehlt: sudo apt install python3-yaml")

STATUS_TEXT = {"stabil": "Stabil", "beta": "Beta", "alpha": "Alpha"}
PFLICHTFELDER = ("id", "name", "kategorie", "beschreibung", "lizenz", "status",
                 "homepage", "quelle", "installation", "mcp")
PFLICHT_VORINSTALLIERT = ("id", "name", "beschreibung", "lizenz", "oeffnen", "homepage")
PFLICHT_META = ("titel", "untertitel")
ID_MUSTER = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def e(text) -> str:
    return html.escape(str(text if text is not None else ""), quote=True)


def expand_home(value: str, home: str | None) -> str:
    if home and (value == "~" or value.startswith("~/")):
        return home.rstrip("/") + value[1:]
    return value


def shell_arg(value: str) -> str:
    """Für die Kommandozeile quoten – ein führendes ~/ bleibt frei, damit die Shell es auflöst."""
    if value.startswith("~/"):
        rest = value[2:]
        return "~/" + (shlex.quote(rest) if rest else "")
    return shlex.quote(value)


def hermes_command(app: dict, home: str | None) -> str:
    """Befehl, der den MCP-Server bei Hermes anmeldet (``hermes mcp add``)."""
    mcp = app["mcp"]
    teile = ["hermes", "mcp", "add", app["id"], "--command", shell_arg(expand_home(mcp["command"], home))]
    args = [shell_arg(expand_home(a, home)) for a in mcp.get("args", [])]
    if args:
        teile += ["--args", *args]
    return " ".join(teile)


def hermes_snippet(app: dict, home: str | None) -> str:
    """Derselbe Eintrag für ~/.hermes/config.yaml (Format laut Hermes-Doku: mcp_servers → command/args)."""
    mcp = app["mcp"]
    args = [expand_home(a, home) for a in mcp.get("args", [])]
    lines = [
        "mcp_servers:",
        f"  {app['id']}:",
        f"    command: {json.dumps(expand_home(mcp['command'], home), ensure_ascii=False)}",
        f"    args: {json.dumps(args, ensure_ascii=False)}",
    ]
    return "\n".join(lines)


def _https(fehler: list[str], wo: str, feld: str, wert) -> None:
    if wert and not str(wert).startswith("https://"):
        fehler.append(f"{wo}: {feld} muss mit https:// beginnen")


def check(data) -> None:
    """Bricht mit einer klaren Meldung ab, wenn Pflichtfelder fehlen oder Werte nicht passen."""
    if not isinstance(data, dict):
        sys.exit("Fehler in der Liste: Die Datei enthält keine Einträge (oben müssen meta, vorinstalliert, apps stehen).")
    fehler: list[str] = []
    meta = data.get("meta")
    if not isinstance(meta, dict):
        fehler.append("meta: Abschnitt fehlt")
        meta = {}
    for feld in PFLICHT_META:
        if not meta.get(feld):
            fehler.append(f"meta: Feld '{feld}' fehlt")
    _https(fehler, "meta", "online_url", meta.get("online_url"))
    ids: set[str] = set()
    vorinstalliert = data.get("vorinstalliert") or []
    apps = data.get("apps")
    if not isinstance(vorinstalliert, list):
        fehler.append("vorinstalliert: muss eine Liste sein")
        vorinstalliert = []
    if not isinstance(apps, list) or not apps:
        fehler.append("apps: Liste fehlt oder ist leer")
        apps = []
    for nr, it in enumerate(vorinstalliert, start=1):
        wo = f"vorinstalliert #{nr} ({it.get('id', '?') if isinstance(it, dict) else '?'})"
        if not isinstance(it, dict):
            fehler.append(f"{wo}: kein Eintrag mit Feldern")
            continue
        for feld in PFLICHT_VORINSTALLIERT:
            if not it.get(feld):
                fehler.append(f"{wo}: Feld '{feld}' fehlt")
        _https(fehler, wo, "homepage", it.get("homepage"))
    for nr, app in enumerate(apps, start=1):
        wo = f"apps #{nr} ({app.get('id', '?') if isinstance(app, dict) else '?'})"
        if not isinstance(app, dict):
            fehler.append(f"{wo}: kein Eintrag mit Feldern")
            continue
        for feld in PFLICHTFELDER:
            if not app.get(feld):
                fehler.append(f"{wo}: Feld '{feld}' fehlt")
        if app.get("id") and not ID_MUSTER.match(str(app["id"])):
            fehler.append(f"{wo}: id nur aus Kleinbuchstaben, Ziffern und '-'")
        if app.get("status") and app["status"] not in STATUS_TEXT:
            fehler.append(f"{wo}: unbekannter status '{app['status']}' (erlaubt: {', '.join(STATUS_TEXT)})")
        if app.get("id") in ids:
            fehler.append(f"{wo}: doppelte id")
        ids.add(app.get("id"))
        for url_feld in ("homepage", "quelle"):
            _https(fehler, wo, url_feld, app.get(url_feld))
        mcp = app.get("mcp")
        if mcp and (not isinstance(mcp, dict) or not mcp.get("command")):
            fehler.append(f"{wo}: mcp braucht 'command'")
        elif mcp and not isinstance(mcp.get("args", []), list):
            fehler.append(f"{wo}: mcp.args muss eine Liste sein")
        if app.get("voraussetzungen") is not None and not isinstance(app["voraussetzungen"], list):
            fehler.append(f"{wo}: voraussetzungen muss eine Liste sein")
    if fehler:
        sys.exit("Fehler in der Liste:\n  " + "\n  ".join(fehler))


def code_block(text: str, label: str) -> str:
    return (f'<div class="code"><div class="code-head"><span>{e(label)}</span>'
            f'<button class="copy" type="button">Kopieren</button></div>'
            f'<pre><code>{e(text.strip())}</code></pre></div>')


def render_app(app: dict, home: str | None) -> str:
    status = app["status"]
    voraus = app.get("voraussetzungen") or []
    geprueft = app.get("geprueft_am")
    badges = [f'<span class="badge s-{e(status)}">{e(STATUS_TEXT[status])}</span>',
              '<span class="badge mcp">MCP</span>']
    if geprueft:
        badges.append(f'<span class="badge ok">Getestet {e(geprueft)}</span>')
    meta = [f"<dt>Lizenz</dt><dd>{e(app['lizenz'])}</dd>"]
    if voraus:
        meta.append(f"<dt>Braucht</dt><dd>{e(', '.join(voraus))}</dd>")
    if app.get("pruefsumme"):
        meta.append(f"<dt>Prüfsumme</dt><dd>{e(app['pruefsumme'])}</dd>")
    hinweis = (f'<p class="hint">{e(app["hinweis"])}</p>' if app.get("hinweis") else "")
    such = " ".join(str(app.get(k, "")) for k in ("name", "kategorie", "beschreibung", "agent_kann")).lower()
    return f"""
<article class="app" data-kat="{e(app['kategorie'])}" data-such="{e(such)}">
  <header>
    <div><p class="kat">{e(app['kategorie'])}</p><h2>{e(app['name'])}</h2></div>
    <div class="badges">{''.join(badges)}</div>
  </header>
  <p>{e(app['beschreibung'])}</p>
  {f'<p class="agent"><strong>Dein Agent kann damit:</strong> {e(app["agent_kann"])}</p>' if app.get('agent_kann') else ''}
  <dl>{''.join(meta)}</dl>
  {hinweis}
  <details>
    <summary>Installieren &amp; mit Hermes verbinden</summary>
    <ol class="steps">
      <li>Offizielle Quelle prüfen: <a href="{e(app['quelle'])}" target="_blank" rel="noopener">{e(app['quelle'])}</a></li>
      <li>Im Terminal ausführen:{code_block(app['installation'], 'Terminal')}</li>
      <li>Bei Hermes anmelden (Hermes zeigt die Werkzeuge, mit „Y“ bestätigen):{code_block(hermes_command(app, home), 'Terminal')}</li>
      <li>Oder von Hand in <code>~/.hermes/config.yaml</code> eintragen:{code_block(hermes_snippet(app, home), 'Hermes MCP-Eintrag')}
      Danach Hermes neu starten (oder im laufenden Hermes <code>/reload-mcp</code>).</li>
    </ol>
  </details>
  <footer><a href="{e(app['homepage'])}" target="_blank" rel="noopener">Website</a></footer>
</article>"""


def render_vorinstalliert(items: list[dict]) -> str:
    if not items:
        return ""
    cards = []
    for it in items:
        cards.append(f"""
<div class="pre">
  <div><h3>{e(it['name'])} <span class="badge ok">Bereits installiert</span></h3>
  <p>{e(it['beschreibung'])}</p>
  <p class="small">Lizenz: {e(it.get('lizenz'))}{' · ' + e(it['hinweis']) if it.get('hinweis') else ''}</p></div>
  <div class="pre-actions"><a class="btn" href="{e(it['oeffnen'])}" target="_blank" rel="noopener">Öffnen</a>
  <a href="{e(it['homepage'])}" target="_blank" rel="noopener">Website</a></div>
</div>""")
    return f'<section class="preinst"><h2 class="sec">Schon dabei</h2>{"".join(cards)}</section>'


CSS = """
:root{--bg:#f6f5f2;--card:#fff;--ink:#1d1d1b;--muted:#66645e;--line:#e3e0d8;--accent:#0f6e5c;--accent-ink:#fff;
--code:#f0eee8;--alpha:#a14a12;--alpha-bg:#fbe9dc;--beta:#7a5c00;--beta-bg:#fbf1cf;--ok:#1d6b34;--ok-bg:#dff1e3;--mcp:#3d3a8a;--mcp-bg:#e6e5f7}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#141513;--card:#1d1f1c;--ink:#ecebe6;--muted:#a19f97;--line:#2f322d;
--accent:#3fbf9f;--accent-ink:#0b1512;--code:#262925;--alpha:#f2a170;--alpha-bg:#3a2417;--beta:#e8c75a;--beta-bg:#352c10;--ok:#7fd894;--ok-bg:#183121;--mcp:#b4b1f5;--mcp-bg:#25244a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:960px;margin:0 auto;padding:32px 16px 64px}
h1{font-size:2rem;margin:0 0 4px;letter-spacing:-.01em}.lead{color:var(--muted);margin:0 0 20px}
.tip{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:10px;padding:14px 16px;margin:0 0 24px}
.toolbar{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 20px}
.toolbar input{flex:1 1 220px;padding:10px 12px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--ink);font:inherit}
.chip{padding:8px 12px;border-radius:999px;border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer;font:inherit;font-size:.9rem}
.chip[aria-pressed="true"]{background:var(--accent);color:var(--accent-ink);border-color:var(--accent)}
.sec{font-size:1.05rem;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin:28px 0 12px}
.pre{display:flex;gap:16px;justify-content:space-between;align-items:center;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;flex-wrap:wrap}
.pre h3{margin:0 0 4px}.pre p{margin:0 0 4px}.pre-actions{display:flex;gap:12px;align-items:center}
.btn{background:var(--accent);color:var(--accent-ink)!important;padding:8px 14px;border-radius:8px;text-decoration:none;font-weight:600}
.grid{display:grid;gap:14px;grid-template-columns:minmax(0,1fr)}
.app{min-width:0;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px}
.app header{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap}
.app h2{margin:0;font-size:1.3rem}.kat{margin:0;color:var(--muted);font-size:.8rem;text-transform:uppercase;letter-spacing:.06em}
.badges{display:flex;gap:6px;flex-wrap:wrap}
.badge{font-size:.75rem;font-weight:600;padding:3px 8px;border-radius:999px;white-space:nowrap}
.s-alpha{color:var(--alpha);background:var(--alpha-bg)}.s-beta{color:var(--beta);background:var(--beta-bg)}
.s-stabil,.ok{color:var(--ok);background:var(--ok-bg)}.mcp{color:var(--mcp);background:var(--mcp-bg)}
.agent{margin:8px 0}dl{display:grid;grid-template-columns:auto 1fr;gap:2px 12px;margin:10px 0;font-size:.9rem}
dt{color:var(--muted)}dd{margin:0}.hint,.small{color:var(--muted);font-size:.9rem}
details{margin-top:10px;border-top:1px solid var(--line);padding-top:10px}summary{cursor:pointer;font-weight:600;color:var(--accent)}
.steps{padding-left:20px}.steps li{margin:10px 0}
.code{margin-top:6px;border:1px solid var(--line);border-radius:8px;overflow:hidden}
.code-head{display:flex;justify-content:space-between;align-items:center;padding:4px 8px 4px 12px;background:var(--code);font-size:.8rem;color:var(--muted)}
.copy{font:inherit;font-size:.8rem;padding:3px 10px;border-radius:6px;border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer}
pre{margin:0;padding:12px;overflow-x:auto;background:var(--code);font:13px/1.5 ui-monospace,"DejaVu Sans Mono",monospace}
a{color:var(--accent)}.app footer{margin-top:8px;font-size:.9rem}
.empty{color:var(--muted);text-align:center;padding:24px}
.foot{margin-top:40px;color:var(--muted);font-size:.85rem;border-top:1px solid var(--line);padding-top:16px}
"""

JS = """
(function(){
  var q=document.getElementById('q'),chips=[].slice.call(document.querySelectorAll('.chip')),
      apps=[].slice.call(document.querySelectorAll('.app')),empty=document.getElementById('empty'),kat='';
  function apply(){var t=(q.value||'').toLowerCase().trim(),n=0;
    apps.forEach(function(a){var ok=(!kat||a.dataset.kat===kat)&&(!t||a.dataset.such.indexOf(t)>-1);a.hidden=!ok;if(ok)n++;});
    empty.hidden=n>0;}
  q.addEventListener('input',apply);
  chips.forEach(function(c){c.addEventListener('click',function(){kat=c.dataset.kat;
    chips.forEach(function(x){x.setAttribute('aria-pressed',x===c?'true':'false')});apply();});});
  document.addEventListener('click',function(ev){var b=ev.target.closest('.copy');if(!b)return;
    var txt=b.closest('.code').querySelector('code').innerText;
    function done(){b.textContent='Kopiert ✓';setTimeout(function(){b.textContent='Kopieren'},1500);}
    if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(txt).then(done,fallback);}else{fallback();}
    function fallback(){var ta=document.createElement('textarea');ta.value=txt;document.body.appendChild(ta);ta.select();
      try{document.execCommand('copy');done();}catch(e){}document.body.removeChild(ta);}});
})();
"""


def render(data: dict, home: str | None, installiert: set[str] | None = None) -> str:
    meta = data.get("meta", {})
    apps = data.get("apps", [])
    vorinstalliert = [it for it in data.get("vorinstalliert") or [] if installiert is None or it["id"] in installiert]
    kats = sorted({a["kategorie"] for a in apps})
    chips = ['<button class="chip" type="button" data-kat="" aria-pressed="true">Alle</button>']
    chips += [f'<button class="chip" type="button" data-kat="{e(k)}" aria-pressed="false">{e(k)}</button>' for k in kats]
    online = meta.get("online_url")
    online_link = (f'<a href="{e(online)}" target="_blank" rel="noopener">Neueste Version der Liste online ansehen</a>'
                   if online else "")
    return f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(meta.get('titel', 'Agenten-Apps'))}</title><style>{CSS}</style></head>
<body><main class="wrap">
<h1>🤖 {e(meta.get('titel', 'Agenten-Apps'))}</h1>
<p class="lead">{e(meta.get('untertitel', ''))}</p>
<div class="tip"><strong>Tipp:</strong> {e(meta.get('hermes_tipp', ''))}</div>
{render_vorinstalliert(vorinstalliert)}
<h2 class="sec">Zum Nachinstallieren</h2>
<div class="toolbar"><input id="q" type="search" placeholder="Suchen, z. B. PDF, Bilder, Browser …" aria-label="Suchen">{''.join(chips)}</div>
<div class="grid">{''.join(render_app(a, home) for a in apps)}</div>
<p id="empty" class="empty" hidden>Nichts gefunden.</p>
<p class="foot">Alle Downloads kommen von den offiziellen Seiten der Hersteller. Bony's Agents installiert diese Programme
nicht automatisch – du entscheidest selbst. Arbeitsordner für Agenten: <code>{e(expand_home(meta.get('arbeitsordner', '~/Agent-Dateien'), home))}</code>.<br>{online_link}</p>
</main><script>{JS}</script></body></html>
"""


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("liste", type=Path)
    p.add_argument("ausgabe", type=Path)
    p.add_argument("--home", help="Home-Verzeichnis des Agent-PC-Nutzers, ersetzt ~ in MCP-Einträgen")
    p.add_argument("--installiert", help="kommagetrennte IDs aus 'vorinstalliert', die wirklich installiert sind")
    a = p.parse_args()
    try:
        data = yaml.safe_load(a.liste.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        sys.exit(f"Liste nicht lesbar ({a.liste}): {exc}")
    check(data)
    installiert = None if a.installiert is None else {i.strip() for i in a.installiert.split(",") if i.strip()}
    a.ausgabe.parent.mkdir(parents=True, exist_ok=True)
    a.ausgabe.write_text(render(data, a.home, installiert), encoding="utf-8")
    print(f"{len(data.get('apps', []))} Apps -> {a.ausgabe}")


if __name__ == "__main__":
    main()
