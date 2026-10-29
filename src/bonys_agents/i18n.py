# SPDX-License-Identifier: GPL-3.0-or-later
"""Sprache der Oberfläche: deutsche Texte im Code, englische aus ``resources/i18n/en.json``.

Schlüssel ist der deutsche Text selbst (wie bei Bony's VPN): ``tr("Agent-PC „{name}“ gestartet", name=n)``.
Fehlt eine Übersetzung (leerer Eintrag oder gar keiner), erscheint der deutsche Text.

Die Einstellung „sprache“ (``auto`` / ``de`` / ``en``) steht in ``settings.json`` (Menü ⓘ → „Sprache / Language“).
„auto“ folgt der Systemsprache: Deutsch bei ``de*``, sonst Englisch. Mit ``FREIGESCHALTET = False`` bliebe „auto“
deutsch und nur ein ausdrückliches „en“ schaltete um. Neue Texte sammelt ``packaging/i18n-sammeln.py`` in den Katalog.

Texte, die an einer Stelle festgelegt und erst beim Anzeigen übersetzt werden (Konstanten, Zustände wie „läuft“,
Beschreibungen in Datenklassen), markiert ``n_("…")``: Der Wert bleibt deutsch (Vergleiche und Schlüssel ändern sich
nicht), der Sammler nimmt den Text in den Katalog, angezeigt wird er mit ``tr(variable)``. So hängt nichts davon ab,
wann ein Modul geladen wurde.
"""

from __future__ import annotations

import json
import os
import re
from functools import cache
from importlib import resources
from pathlib import Path




DEUTSCH = "de"
ENGLISCH = "en"
SPRACHEN = (DEUTSCH, ENGLISCH)
AUTO = "auto"
EINSTELLUNG = "sprache"
# Umgebungsvariable mit Vorrang vor Einstellung und System („de“ oder „en“) – zum Ausprobieren und für die Tests
UMGEBUNG = "BONYS_AGENTS_SPRACHE"
# Seit Phase 2 (docs/dev/plan-englisch.md) ist die Oberfläche vollständig englisch: „auto“ folgt dem System.
FREIGESCHALTET = True

_aktiv: str = DEUTSCH


def system_sprache(name: str | None = None, env=None) -> str:
    """„de“ für deutsche Systeme, sonst „en“.

    ``name``: Systemsprache wie ``QLocale.system().name()`` („de_AT“); ohne Angabe die Umgebungsvariablen
    wie bei gettext (LANGUAGE, LC_ALL, LC_MESSAGES, LANG)."""
    if name is None:
        env = os.environ if env is None else env
        for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
            value = env.get(var, "")
            if value and value not in ("C", "POSIX", "C.UTF-8"):
                name = value.split(":")[0]
                break
    return DEUTSCH if (name or "").lower().startswith("de") else ENGLISCH


def einstellung() -> str:
    """Gespeicherte Wahl: „auto“, „de“ oder „en“ (Unbekanntes zählt als „auto“)."""
    from . import storage   # erst hier: i18n wird auch aus Modulen geladen, die storage selbst braucht

    wert = storage.load_settings().get(EINSTELLUNG)
    return wert if wert in (AUTO, *SPRACHEN) else AUTO


def einstellung_setzen(wert: str) -> None:
    if wert not in (AUTO, *SPRACHEN):
        raise ValueError(tr("Unbekannte Sprache „{wert}“.", wert=wert))
    from . import storage

    s = storage.load_settings()
    s[EINSTELLUNG] = wert
    storage.save_settings(s)


def waehlen(wahl: str, system: str) -> str:
    """Sprache aus Einstellung und Systemsprache."""
    if wahl in SPRACHEN:
        return wahl
    return system if FREIGESCHALTET else DEUTSCH


def starten(system_name: str | None = None) -> str:
    """Beim Programmstart: Sprache festlegen (gilt bis zum Ende, Umstellen wirkt nach einem Neustart)."""
    if (fest := os.environ.get(UMGEBUNG, "").strip().lower()) in SPRACHEN:
        return setzen(fest)
    try:
        wahl = einstellung()
    except OSError:
        wahl = AUTO
    return setzen(waehlen(wahl, system_sprache(system_name)))


def setzen(sprache: str) -> str:
    global _aktiv
    _aktiv = sprache if sprache in SPRACHEN else DEUTSCH
    return _aktiv


def sprache() -> str:
    return _aktiv


@cache
def katalog(sprache: str) -> dict[str, str]:
    """Übersetzungen einer Sprache (deutscher Text → Übersetzung); leere Einträge sind noch offen."""
    if sprache == DEUTSCH:
        return {}
    try:
        text = (resources.files("bonys_agents") / "resources" / "i18n" / f"{sprache}.json").read_text("utf-8")
        daten = json.loads(text)
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in daten.items() if isinstance(k, str) and isinstance(v, str) and v}


def tr(text: str, **kw) -> str:
    """Deutscher Text → in der Sprache der Oberfläche; Platzhalter ``{name}`` werden danach eingesetzt."""
    out = katalog(_aktiv).get(text, text) if _aktiv != DEUTSCH else text
    return out.format(**kw) if kw else out


def n_(text: str) -> str:
    """Nur markieren: ``text`` kommt in den Katalog, bleibt hier aber deutsch – übersetzt wird beim Anzeigen."""
    return text


def tr_in(sprache: str, text: str, **kw) -> str:
    """Wie ``tr``, aber in einer bestimmten Sprache (z. B. der des Browsers bei Seiten für Teilnehmer)."""
    out = katalog(sprache).get(text, text) if sprache != DEUTSCH else text
    return out.format(**kw) if kw else out


def sprache_aus_accept(header: str | None) -> str:
    """Sprache aus dem HTTP-Kopf Accept-Language („de-DE,de;q=0.9,en;q=0.8“): Deutsch nur, wenn zuerst gewünscht."""
    erste = (header or "").split(",")[0].strip()
    return system_sprache(erste) if erste else DEUTSCH


# ---------------------------------------------------------------- Seiten im Browser (HTML + JavaScript)
# Texte stehen deutsch in der Seite: tr("…") bzw. tr('…') in *.js, data-tr am Element (Text), data-tr-placeholder und
# data-tr-title (Attribute) in *.html, dazu <title>. Die Seite lädt texte.js (seiten_js), die tr() bereitstellt und die
# markierten Elemente übersetzt. packaging/i18n-sammeln.py nimmt die Texte mit seiten_texte() in den Katalog.
_JS_TR = re.compile(r"""\btr\((?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)")""")
_HTML_TR = re.compile(r"<(\w+)\b[^>]*\bdata-tr(?![-\w])[^>]*>([^<]+)</\1>")
_HTML_TAG = re.compile(r"<\w+\b[^>]*>")
_HTML_TITEL = re.compile(r"<title>([^<]+)</title>")
_JS_ESCAPES = {"\\'": "'", '\\"': '"', "\\n": "\n", "\\\\": "\\"}


def _js_text(roh: str) -> str:
    return re.sub(r"\\[\\'\"n]", lambda m: _JS_ESCAPES[m.group(0)], roh)


def seiten_texte(*ordner: Path) -> list[str]:
    """Alle deutschen Texte der Seiten in ``ordner`` (nur *.js und *.html direkt darin), die übersetzt werden."""
    texte: list[str] = []
    for o in ordner:
        for datei in sorted(Path(o).glob("*.js")):
            for m in _JS_TR.finditer(datei.read_text("utf-8")):
                texte.append(_js_text(m.group(1) if m.group(1) is not None else m.group(2)))
        for datei in sorted(Path(o).glob("*.html")):
            html = datei.read_text("utf-8")
            texte += [m.group(2).strip() for m in _HTML_TR.finditer(html)]
            for tag in _HTML_TAG.findall(html):
                for attr in ("placeholder", "title"):
                    if f"data-tr-{attr}" in tag and (m := re.search(rf'\b{attr}="([^"]+)"', tag)):
                        texte.append(m.group(1))
            texte += _HTML_TITEL.findall(html)
    return list(dict.fromkeys(texte))


_SEITEN_JS = """(function () {
  var texte = %s, sprache = %s;
  if (!sprache) sprache = /^de\\b/i.test(navigator.language || '') ? 'de' : 'en';
  if (sprache === 'de') texte = {};
  window.SEITEN_SPRACHE = sprache;
  window.tr = function (text, kw) {
    var out = texte[text] || text;
    return kw ? out.replace(/\\{(\\w+)\\}/g, function (m, k) { return k in kw ? String(kw[k]) : m; }) : out;
  };
  function seite() {
    document.documentElement.lang = sprache;
    document.title = window.tr(document.title);
    document.querySelectorAll('[data-tr]').forEach(function (e) { e.textContent = window.tr(e.textContent.trim()); });
    ['placeholder', 'title'].forEach(function (a) {
      document.querySelectorAll('[data-tr-' + a + ']').forEach(function (e) { e[a] = window.tr(e[a]); });
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', seite); else seite();
})();
"""


def seiten_js(texte: list[str], sprache: str | None = None) -> bytes:
    """``texte.js`` für Seiten im Browser. ``sprache`` None: die Seite nimmt die Sprache des Browsers."""
    en = katalog(ENGLISCH)
    daten = {t: en[t] for t in texte if t in en}
    return (_SEITEN_JS % (json.dumps(daten, ensure_ascii=False), json.dumps(sprache))).encode()
