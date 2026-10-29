-- SPDX-License-Identifier: CC-BY-SA-4.0
-- Pandoc-Filter für die Handbücher (nur Ausgabe Typst):
--   ::: hinweis / tipp / warnung / datenschutz  → Kasten (vorlage/stil.typ)
--   ::: feld {hoehe="3cm" text="Kurscode"}     → leeres Feld zum Ausfüllen (Handout)
--   ::: seitenumbruch                          → neue Seite
--   ①…⑨ im Text                                → Nummer wie in den Bildschirmfotos
--   Bilder „bilder/…“                          → Pfad ab der Wurzel des Repositorys (typst --root)

local KAESTEN = { hinweis = true, tipp = true, warnung = true, datenschutz = true }
local MARKEN = { ["①"] = 1, ["②"] = 2, ["③"] = 3, ["④"] = 4, ["⑤"] = 5, ["⑥"] = 6, ["⑦"] = 7, ["⑧"] = 8,
                 ["⑨"] = 9 }

local function typst(text) return pandoc.RawBlock("typst", text) end

-- Sprache aus dem Metadatum „sprache“ (erstellen.sh: -M sprache=en); Standard Deutsch
local englisch = false
local function Meta(meta)
  englisch = meta.sprache ~= nil and pandoc.utils.stringify(meta.sprache) == "en"
  if englisch then meta["sprache-en"] = true end
  return meta
end

function Div(el)
  for _, klasse in ipairs(el.classes) do
    if KAESTEN[klasse] then
      local inhalt = { typst('#kasten("' .. klasse .. '")[') }
      for _, b in ipairs(el.content) do table.insert(inhalt, b) end
      table.insert(inhalt, typst("]"))
      return inhalt
    elseif klasse == "feld" then
      local hoehe = el.attributes.hoehe or "1.4cm"
      local text = (el.attributes.text or ""):gsub('"', '\\"')
      return typst('#feld(hoehe: ' .. hoehe .. ', beschriftung: "' .. text .. '")')
    elseif klasse == "seitenumbruch" then
      return typst("#pagebreak()")
    end
  end
end

function Str(el)
  local teile, rest, gefunden = {}, el.text, false
  while true do
    local anfang, ende, nummer = nil, nil, nil
    for zeichen, n in pairs(MARKEN) do
      local a, e = rest:find(zeichen, 1, true)
      if a and (not anfang or a < anfang) then anfang, ende, nummer = a, e, n end
    end
    if not anfang then break end
    gefunden = true
    if anfang > 1 then table.insert(teile, pandoc.Str(rest:sub(1, anfang - 1))) end
    table.insert(teile, pandoc.RawInline("typst", "#marke(" .. nummer .. ")"))
    rest = rest:sub(ende + 1)
  end
  if not gefunden then return nil end
  if #rest > 0 then table.insert(teile, pandoc.Str(rest)) end
  return teile
end

-- Selbst gemachte Bilder (bilder/eigene/) können noch fehlen: dann ein Platzhalter mit der Beschreibung
local function vorhanden(pfad)
  local f = io.open(pfad, "rb")
  if f then f:close() return true end
  return false
end

function Image(el)
  if el.src:match("^bilder/") or el.src:match("^vorlage/") then
    if not vorhanden(el.src) then
      io.stderr:write("  Bild fehlt noch: " .. el.src .. "\n")
      return pandoc.RawInline("typst", '#block(width: 100%, height: 4cm, fill: luma(240), radius: 4pt, inset: 12pt, '
        .. 'align(center + horizon, text(fill: luma(110))[' .. (englisch and 'Image to follow: ' or 'Bild folgt: ') .. el.src
        .. ']))')
    end
    el.src = "/docs/handbuch/" .. el.src
  end
  return el
end

-- Erst die Metadaten (Sprache), dann der Text
return {
  { Meta = Meta },
  { Div = Div, Str = Str, Image = Image },
}
