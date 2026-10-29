// SPDX-License-Identifier: CC-BY-SA-4.0
// Gestaltung der Handbücher von Bony's Agents (Typst). Pandoc setzt den Text ein (vorlage/pandoc.typ),
// erstellen.sh übergibt Titel, Version, Datum und Sprache („de“ oder „en“, Metadatum „sprache“).

// Feste Texte der Vorlage je Sprache – gewählt nach text.lang (gesetzt in conf)
#let texte = (
  de: (hinweis: "Hinweis", tipp: "Tipp", warnung: "Achtung", datenschutz: "Datenschutz", bild: "Bild",
       tabelle: "Tabelle", inhalt: "Inhalt", stand: "Stand", lizenz: "Lizenz", kurspaket: "Kurspaket", von: "von",
       erstellt: "erstellt mit Bony's Agents"),
  en: (hinweis: "Note", tipp: "Tip", warnung: "Caution", datenschutz: "Privacy", bild: "Figure", tabelle: "Table",
       inhalt: "Contents", stand: "Updated", lizenz: "License", kurspaket: "Course package", von: "by",
       erstellt: "made with Bony's Agents"),
)
#let t(schluessel) = context texte.at(if text.lang == "en" { "en" } else { "de" }).at(schluessel)

#let orange = rgb("#f5a623")
#let nachtblau = rgb("#0d141d")
#let eisblau = rgb("#3fa9f5")
#let grau = rgb("#5b6878")
#let hell = rgb("#f4f6f9")

// Nummer wie in den Bildschirmfotos (①②③ im Text)
#let marke(n) = box(height: 0.8em, baseline: 0.12em, circle(radius: 0.52em, fill: orange, stroke: 1pt + nachtblau,
  inset: 0pt, align(center + horizon, text(size: 0.7em, weight: "bold", fill: nachtblau, str(n)))))

// Hinweis-, Tipp- und Warnkästen: ::: hinweis … ::: im Markdown
#let kasten(art, inhalt) = {
  let (farbe, flaeche) = (
    hinweis: (eisblau, rgb("#eaf5fe")),
    tipp: (rgb("#2e9d6a"), rgb("#e9f7f0")),
    warnung: (rgb("#d9480f"), rgb("#fff1e6")),
    datenschutz: (rgb("#6a4cc4"), rgb("#f1edfc")),
  ).at(art)
  let titel = t(art)
  block(width: 100%, breakable: false, above: 1em, below: 1em, fill: flaeche, radius: 4pt,
    stroke: (left: 4pt + farbe), inset: (left: 14pt, right: 12pt, top: 10pt, bottom: 10pt))[
    #text(weight: "bold", fill: farbe, titel) \
    #inhalt
  ]
}

// Feld zum Ausfüllen (Handout: Kurscode, Notizen)
#let feld(hoehe: 1.4cm, beschriftung: "") = block(width: 100%, height: hoehe, stroke: 0.8pt + grau,
  radius: 4pt, inset: 8pt, text(size: 9pt, fill: grau, beschriftung))

#let conf(
  titel: none, untertitel: none, dokument: "", version: "", datum: "", inhalt-zeigen: true, kurz: false,
  kapitel-seite: true, fuss: none, versionszeile: none, kopf: none, sprache: "de", doc,
) = {
  set document(title: titel, author: "Bony")
  set text(font: ("Source Sans 3", "DejaVu Sans", "Noto Color Emoji"), size: 11pt, lang: sprache,
    region: if sprache == "de" { "de" } else { "us" },
    hyphenate: true)
  set par(justify: false, leading: 0.68em, spacing: 1.05em)
  show raw: set text(font: ("Source Code Pro", "DejaVu Sans Mono"), size: 0.92em)
  show raw.where(block: true): it => block(width: 100%, fill: hell, radius: 4pt, inset: 9pt, stroke: 0.5pt
    + rgb("#d5dbe3"), it)
  show raw.where(block: false): it => box(fill: hell, inset: (x: 2pt), outset: (y: 2pt), radius: 2pt, it)
  show link: it => if type(it.dest) == str { text(fill: rgb("#1c6fb5"), it) } else { it }
  set list(indent: 0.6em, body-indent: 0.5em)
  set enum(indent: 0.6em, body-indent: 0.5em, numbering: "1.")
  set table(stroke: 0.5pt + rgb("#c9d1db"), inset: 6pt)
  show table.cell: set align(left)
  show table.cell.where(y: 0): set text(weight: "bold")
  set figure(gap: 0.6em)
  show figure.caption: it => text(size: 9.5pt, fill: grau, [#it.supplement #context it.counter.display(it.numbering): #it.body])
  set figure.caption(separator: [: ])
  show figure.where(kind: image): set figure(supplement: t("bild"))
  show figure.where(kind: table): set figure(supplement: t("tabelle"))
  // Große Bilder dürfen an den Seitenanfang oder das Seitenende rutschen – sonst bleiben halbe Seiten leer
  show figure.where(kind: image): set figure(placement: auto)
  set place(clearance: 1.4em)
  show image: it => box(stroke: 0.6pt + rgb("#b8c2cf"), radius: 3pt, clip: true, it)

  // Überschriften: Kapitel auf neuer Seite (nicht im Handout)
  set heading(numbering: if kurz { none } else { "1.1" })
  show heading.where(level: 1): it => {
    if kapitel-seite and not kurz { pagebreak(weak: true) }
    v(if kurz { 0.4em } else { 1.2em })
    block(below: 0.9em, text(size: if kurz { 17pt } else { 22pt }, weight: "bold", fill: nachtblau, {
      if it.numbering != none { text(fill: orange, counter(heading).display("1")); h(0.5em) }
      it.body
    }))
  }
  show heading.where(level: 2): it => block(above: 1.4em, below: 0.7em, text(size: 14pt, weight: "bold",
    fill: nachtblau, it))
  show heading.where(level: 3): it => block(above: 1.1em, below: 0.6em, text(size: 12pt, weight: "bold",
    fill: rgb("#24364d"), it))

  set page(paper: "a4", margin: (top: 2.6cm, bottom: 2.3cm, left: 2.3cm, right: 2.1cm),
    header: context {
      if here().page() > 1 {
        set text(size: 9pt, fill: grau)
        grid(columns: (1fr, auto), dokument, if kopf != none { kopf } else [Bony's Agents #version])
        v(-0.5em)
        line(length: 100%, stroke: 0.5pt + rgb("#d5dbe3"))
      }
    },
    footer: context {
      if here().page() > 1 {
        set text(size: 9pt, fill: grau)
        grid(columns: (1fr, auto), if fuss != none { fuss } else [#t("stand"): #datum · #t("lizenz"): CC BY-SA 4.0],
          counter(page).display("1"))
      }
    })

  // ---------- Titelseite
  if kurz {
    grid(columns: (auto, 1fr), column-gutter: 14pt, align: horizon,
      image("/src/bonys_agents/resources/logo.png", height: 1.8cm),
      [#text(size: 22pt, weight: "bold", fill: nachtblau, titel) \
       #if untertitel != none { text(size: 12pt, fill: grau, untertitel) }])
    v(0.2em)
    line(length: 100%, stroke: 1.5pt + orange)
  } else {
    page(margin: 0cm, header: none, footer: none, fill: nachtblau)[
      #place(top, image("/src/bonys_agents/resources/background.jpg", width: 100%))
      #place(top + left, dx: 2.3cm, dy: 15.6cm, block(width: 16.5cm)[
        #image("/src/bonys_agents/resources/logo.png", height: 2.6cm)
        #v(0.6cm)
        #text(size: 34pt, weight: "bold", fill: white, titel)
        #v(0.1cm)
        #if untertitel != none { text(size: 15pt, fill: eisblau, untertitel) }
        #v(1.2cm)
        #line(length: 6cm, stroke: 2pt + orange)
        #v(0.3cm)
        #text(size: 12pt, fill: white)[#if versionszeile != none { versionszeile } else [Bony's Agents #version · #t("stand") #datum]]
      ])
    ]
    counter(page).update(1)
  }

  if inhalt-zeigen {
    show outline.entry.where(level: 1): it => { v(0.5em, weak: true); strong(it) }
    outline(title: text(size: 20pt, fill: nachtblau, t("inhalt")), depth: 2, indent: 1.2em)
    pagebreak()
  }

  doc
}

// Letzte Seite bzw. Schluss: Lizenz des Handbuchs
#let lizenz(kurz: false) = context {
  let en = text.lang == "en"
  if not kurz { pagebreak(weak: true) } else { v(1.5em) }
  set text(size: if kurz { 8.5pt } else { 10pt }, fill: grau)
  if not kurz { heading(numbering: none, outlined: true, if en { "License of this guide" } else { "Lizenz dieses Handbuchs" }) }
  if en [This document is part of Bony's Agents (#link("https://github.com/zappotex/BonysAgents")). Text and
  screenshots are licensed under *Creative Commons Attribution-ShareAlike 4.0 International* (CC BY-SA 4.0,
  #link("https://creativecommons.org/licenses/by-sa/4.0/")): you may copy, share and adapt it, also for courses
  and commercially – with attribution ("Bony's Agents, Bony", link to the project) and under the same license.]
  else [Dieses Dokument ist Teil von Bony's Agents (#link("https://github.com/zappotex/BonysAgents")). Text und
  Bildschirmfotos stehen unter der Lizenz *Creative Commons Namensnennung – Weitergabe unter gleichen Bedingungen
  4.0 International* (CC BY-SA 4.0, #link("https://creativecommons.org/licenses/by-sa/4.0/deed.de")): Du darfst es
  kopieren, weitergeben, verändern und auch für Kurse und kommerziell nutzen – mit Namensnennung („Bony's Agents,
  Bony“, Link zum Projekt) und unter derselben Lizenz.]
  if not kurz {
    parbreak()
    if en [*Excluded* are the name "Bony's Agents" and the logo: they must not be used for modified versions. The
    program itself is licensed under the GPL-3.0-or-later. The screenshots show made-up sample data; names such as
    Anna, Ben, Clara and Eva, course codes and addresses are fictional.]
    else [*Ausgenommen* sind der Name „Bony's Agents“ und das Logo: Sie dürfen nicht für veränderte Fassungen verwendet
    werden. Das Programm selbst steht unter der GPL-3.0-or-later. Die Bildschirmfotos zeigen erfundene
    Beispieldaten; Namen wie Anna, Ben, Clara und Eva, Kurscodes und Adressen sind ausgedacht.]
    parbreak()
    if en [Fonts: Source Sans 3 and Source Code Pro (Adobe, SIL Open Font License 1.1). Typeset with Pandoc and
    Typst.]
    else [Schriften: Source Sans 3 und Source Code Pro (Adobe, SIL Open Font License 1.1). Gesetzt mit Pandoc und
    Typst.]
  }
}

// Schluss bei Kurspaketen (Ablaufplan, Handout): Autor und Lizenz des Kurspakets statt der des Handbuchs
#let paket-lizenz(autor: [], lizenz: []) = {
  v(1.5em)
  set text(size: 8.5pt, fill: grau)
  [#t("kurspaket")#if autor != [] [ #t("von") #autor] · #t("lizenz"): #lizenz · #t("erstellt")
  (#link("https://github.com/zappotex/BonysAgents")).]
}
