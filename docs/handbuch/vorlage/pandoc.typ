// SPDX-License-Identifier: CC-BY-SA-4.0
// Pandoc-Vorlage für die Handbücher: setzt den umgewandelten Markdown-Text in die Gestaltung aus stil.typ.
#import "/docs/handbuch/vorlage/stil.typ": conf, kasten, marke, feld, lizenz

#let horizontalRule = line(length: 100%, stroke: 0.5pt + rgb("#c9d1db"))
#let divider = horizontalRule

#show: doc => conf(
  titel: [$title$],
$if(subtitle)$
  untertitel: [$subtitle$],
$endif$
  dokument: [$dokument$],
  version: "$version$",
  datum: "$datum$",
  inhalt-zeigen: $if(kurz)$false$else$true$endif$,
  kurz: $if(kurz)$true$else$false$endif$,
  kapitel-seite: $if(kompakt)$false$else$true$endif$,
  doc,
)

$body$

#lizenz(kurz: $if(kurz)$true$else$false$endif$)
