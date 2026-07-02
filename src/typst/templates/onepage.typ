// Naavik 1-page resume — the single default template.
//
// Dense, recruiter-standard, ATS-parseable single column:
// name + one clickable contact line, Summary → Experience → Projects →
// Education → Skills, entry headings left with dates right-aligned on the
// same baseline, tight consistent spacing. Ligatures disabled so ATS
// parsers never see `fi`/`fl` PUA codepoints.
//
// Consumes JSON via `sys.inputs.data`. The payload is precomposed by
// `document_generator._build_resume_data` — all conditional separators,
// date ranges, and link hrefs are built in Python so the template never
// juggles `#if` chains that leak stray spaces:
//   {
//     "profile": {"full_name": str},
//     "headline": str | null,                  // tailored > profile headline
//     "contact_links": [{"text": str, "href": str | null}],
//     "summary": str | null,                   // JD-tailored 2-3 line pitch
//     "experiences": [
//       {"heading": str,                       // "Senior Software Engineer · Intuit"
//        "meta": str | null,                   // "Mountain View, CA"
//        "dates": str,                         // "Jan 2025 – Present"
//        "bullets": [str]}
//     ],
//     "projects": [{"title": str, "date": str | null, "text": str | null,
//                   "link": str | null}],
//     "education": [{"heading": str, "meta": str | null, "dates": str}],
//     "skills": [{"category": str, "items": [str]}],
//   }

#let data = json.decode(sys.inputs.data)

#set document(title: data.profile.full_name + " — Resume")

#set page(paper: "us-letter", margin: (x: 0.45in, y: 0.38in))

#set text(
  font: ("Helvetica", "Arial", "Liberation Sans"),
  size: 9.5pt,
  fill: rgb("#111111"),
  features: ("liga": 0, "clig": 0, "dlig": 0),
)
#set par(leading: 0.5em, justify: false)

#let accent = rgb("#111111")

#let section_title(name) = {
  v(0.55em)
  text(weight: "bold", size: 10pt, tracking: 0.06em, upper(name))
  v(-0.62em)
  line(length: 100%, stroke: 0.6pt + accent)
  v(-0.18em)
}

// One bullet line with hanging indent so wraps align under the text.
#let bullet_line(t) = {
  pad(left: 2pt, par(hanging-indent: 7pt, leading: 0.45em)[• #t])
  v(-0.62em)
}

// Entry heading: content left, dates right, one shared baseline.
#let entry(left_content, dates) = {
  grid(
    columns: (1fr, auto),
    column-gutter: 10pt,
    align: (left, right),
    left_content,
    text(size: 8.5pt, fill: rgb("#333333"), dates),
  )
}

// ───────── Header ─────────

#align(center)[
  #text(weight: "bold", size: 15.5pt, tracking: 0.02em, data.profile.full_name)
  #if data.headline != none [
    #v(-0.55em)
    #text(size: 9.5pt, fill: rgb("#333333"), data.headline)
  ]
  #v(-0.5em)
  #text(size: 8.5pt)[
    #{
      let parts = ()
      for c in data.contact_links {
        if c.href != none {
          parts.push(link(c.href, text(fill: rgb("#1a4a8a"), c.text)))
        } else {
          parts.push(text(c.text))
        }
      }
      parts.join([ #h(2pt) · #h(2pt) ])
    }
  ]
]

#v(-0.2em)

// ───────── Summary ─────────

#if data.summary != none [
  #section_title("Summary")
  #text(size: 9.5pt, data.summary)
]

// ───────── Experience ─────────

#section_title("Experience")

#for (i, exp) in data.experiences.enumerate() [
  #if i > 0 [#v(0.28em)]
  #entry(
    [#text(weight: "bold", exp.heading)#if exp.meta != none [#text(size: 8.5pt, fill: rgb("#333333"))[ — #exp.meta]]],
    exp.dates,
  )
  #v(-0.5em)
  #for b in exp.bullets [
    #bullet_line(b)
  ]
  #v(0.55em)
]

// ───────── Projects ─────────

#if data.projects.len() > 0 [
  #section_title("Projects")
  #for (i, p) in data.projects.enumerate() [
    #if i > 0 [#v(0.22em)]
    #entry(
      [#text(weight: "bold", p.title)#if p.link != none [#text(size: 8.5pt)[ — #link(p.link, text(fill: rgb("#1a4a8a"), p.link.replace("https://", "").replace("http://", "")))]]],
      if p.date != none { p.date } else { "" },
    )
    #if p.text != none and p.text != "" [
      #v(-0.55em)
      #pad(left: 2pt, text(size: 9pt, p.text))
    ]
    #v(-0.15em)
  ]
]

// ───────── Education ─────────

#if data.education.len() > 0 [
  #section_title("Education")
  #for e in data.education [
    #entry(
      [#text(weight: "bold", e.heading)#if e.meta != none [#text(size: 8.5pt, fill: rgb("#333333"))[ — #e.meta]]],
      e.dates,
    )
    #v(-0.1em)
  ]
]

// ───────── Skills ─────────

#if data.skills.len() > 0 [
  #section_title("Skills")
  #for s in data.skills [
    #par(hanging-indent: 8pt, leading: 0.45em)[#text(weight: "bold", s.category + ": ")#s.items.join(", ")]
    #v(-0.55em)
  ]
]

// ───────── Page-count metadata for validator ─────────

#context [
  #metadata((pages: counter(page).final().first()))<naavik-meta>
]
