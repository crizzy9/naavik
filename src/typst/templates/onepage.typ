// Naavik 1-page resume — 1:1 Typst conversion of the owner's LaTeX OnePage
// template (cv.tex): 10pt US-letter, 0.3in side margins / 0.25in top+bottom,
// Helvetica, centered small-caps name + one contact line, small-caps section
// titles over a full-width rule, ○-bulleted tight itemize, jobentry /
// educationentry / projectentry layouts. Ligatures disabled so ATS parsers
// never see `fi`/`fl` PUA codepoints.
//
// Consumes JSON via `sys.inputs.data`, precomposed by
// `document_generator._build_resume_data`:
//   {
//     "profile": {"full_name": str},
//     "contact_lines": [[{"text": str, "href": str | null}]],  // TWO lines
//     "summary": str | null,                    // JD-tailored, optional
//     "experiences": [
//       {"company": str,                        // "Intuit, Personalization"
//        "title": str,                          // "Senior Software Engineer"
//        "location": str,                       // "Mountain View, CA"
//        "dates": str,                          // "Jan 2025 – Present"
//        "bullets": [str]}
//     ],
//     "education": [{"institution": str, "school": str | null,
//                    "location": str, "dates": str,
//                    "degree": str, "gpa": str | null}],
//     "skills": [{"category": str, "items": [str]}],   // per-job tailored subset
//     "projects": [{"title": str, "descriptor": str | null,
//                   "date": str | null, "text": str | null}],
//     "certifications": [{"title": str, "date": str | null,
//                         "text": str | null}],
//     "open_source": [{"title": str, "descriptor": str | null,
//                      "date": str | null, "text": str | null}],
//   }
// Projects render as bold title + "— descriptor" (2-3 words, AI-chosen);
// per-project links are NEVER rendered — the header portfolio URL covers it.
// There is deliberately NO headline field — header is name + contacts only.

#let data = json(bytes(sys.inputs.data))

#set document(title: data.profile.full_name + " — Resume")

// cv.tex geometry exactly: \usepackage[margin=0.3in, top=0.25in,
// bottom=0.25in]{geometry}. Do NOT widen these — the refine-bullet char
// budget (112/118 in document_generator) is calibrated to this text width;
// the 2026-07 0.5in experiment made calibrated one-liners wrap by a word.
#set page(paper: "us-letter", margin: (x: 0.3in, top: 0.25in, bottom: 0.25in))

// cv.tex's preamble asks for Helvetica, but the compiled reference PDF
// actually embeds Computer Modern (CMR10/CMBX10/CMTI10 — the `sans` package
// never takes effect). New Computer Modern is bundled inside the typst
// binary, so it renders identically everywhere AND its narrower metrics are
// what let cv.tex's ~127-char bullets fit on one printed line.
#set text(
  font: ("New Computer Modern", "Liberation Sans"),
  size: 10pt,
  fill: rgb("#111111"),
  features: ("liga": 0, "clig": 0, "dlig": 0),
)
// leading = intra-paragraph line height; spacing = inter-paragraph gap.
// LaTeX source uses noitemsep/nolistsep — paragraph gaps collapse to the
// line rhythm, which is what packs the page. justify matches LaTeX's default
// full justification: interword glue SHRINKS on tight lines, which is how
// cv.tex fits its longest bullets on one printed line.
// 0.52em ≈ cmr10's 12pt \baselineskip at 10pt — measured against the
// pdflatex render; 0.42em packed noticeably tighter than the reference.
#set par(leading: 0.52em, spacing: 0.52em, justify: true)
#set block(spacing: 0.52em)

#let linkcolor = rgb("#0000EE")

// Helvetica/Liberation Sans carry no `smcp` feature and Typst won't
// synthesize small caps for them — emulate: uppercase everything, initial
// letter full-size, the rest at ~78%.
#let sc(s, ratio: 0.78) = {
  let words = ()
  for w in str(s).split(" ") {
    let cl = w.clusters()
    if cl.len() == 0 { continue }
    words.push([#upper(cl.first())#text(size: ratio * 1em)[#upper(cl.slice(1).join())]])
  }
  words.join([ ])
}

// LaTeX \titleformat: \scshape\large title, black \titlerule under, tight
// vertical spacing (-8pt above via \vspace, -5pt after the rule).
#let sectitle(name) = {
  v(0.22em)
  block(spacing: 0pt)[
    #text(size: 12pt)[#sc(name)]
    // -0.45em let the rule clip letter bottoms (J/y descenders sat on it);
    // -0.30em leaves a hairline gap. Pre/post spacing shrunk to compensate.
    #v(-0.30em)
    #line(length: 100%, stroke: 0.5pt + black)
  ]
  v(0.02em)
}

// \setlist[itemize]{leftmargin=0.15in, noitemsep, nolistsep} with $\circ$:
// text starts exactly 0.15in from the margin (the char-budget calibration
// width); the ∘ label sits right-aligned in the gutter with a small labelsep,
// like LaTeX's list label box.
#let bullet_items(items) = {
  for b in items {
    grid(
      columns: (0.15in, 1fr),
      align(right, [∘#h(3.5pt)]),
      par(hanging-indent: 0in)[#b],
    )
  }
}

// \jobentry{company}{title}{location}{dates}:
// \textbf{#1} \hfill #2 \hfill \textit{#3} \hfill \textbf{#4}
#let jobentry(company, title, location, dates) = {
  grid(
    columns: (auto, 1fr, 1fr, auto),
    column-gutter: 8pt,
    align: (left, center, center, right),
    text(weight: "bold", company),
    title,
    emph(location),
    text(weight: "bold", dates),
  )
}

// \educationentry{institution}{school}{location}{dates} + degree/GPA line:
// \textbf{#1}, #2 \hfill \textit{#3} \hfill \textbf{#4}
// \textit{degree} \hfill GPA: x
#let educationentry(institution, school, location, dates, degree, gpa) = {
  grid(
    columns: (auto, 1fr, auto),
    column-gutter: 8pt,
    align: (left, center, right),
    [#text(weight: "bold", institution)#if school != none and school != "" [, #school]],
    emph(location),
    text(weight: "bold", dates),
  )
  v(-0.18em)
  grid(
    columns: (1fr, auto),
    emph(degree),
    if gpa != none and gpa != "" [GPA: #gpa] else [],
  )
}

// \projectentry{title}{date}: {#1} \hfill \textbf{#2}
// Bold title, optional "— descriptor" tagline (2-3 words), bold date right.
// No links here, ever — the header portfolio URL is the canonical pointer.
#let projectentry(title, descriptor, date) = {
  grid(
    columns: (1fr, auto),
    column-gutter: 8pt,
    [#text(weight: "bold", title)#if descriptor != none and descriptor != "" [ — #descriptor]],
    text(weight: "bold", if date != none { date } else { "" }),
  )
}

// ───────── Header ─────────

// \name{...} then two \contactinfo lines (phone|email|location and
// portfolio|github|linkedin), all centered, links in the LaTeX link blue.
#align(center)[
  #text(size: 14.4pt)[#sc(data.profile.full_name)]
  #v(-0.35em)
  #for line in data.contact_lines [
    // Explicit par() per line — plain content blocks would merge both
    // \contactinfo lines into one centered paragraph.
    #par(justify: false)[
      #text(size: 9pt)[
        #{
          let parts = ()
          for c in line {
            if c.href != none {
              parts.push(link(c.href, text(fill: linkcolor, c.text)))
            } else {
              parts.push(text(c.text))
            }
          }
          parts.join([ #h(1.5pt) | #h(1.5pt) ])
        }
      ]
    ]
  ]
]

// ───────── Summary (optional; tailored per-JD) ─────────

// Same 0.52em breathing rhythm as the rest of the page: other sections open
// with bold grid rows whose ascenders read as whitespace, but a justified
// 9.5pt paragraph hugs the rule — give it an explicit line-gap on both sides
// and page-rhythm leading (0.55em × 9.5pt ≈ 0.52em × 10pt).
#if data.at("summary", default: none) != none [
  #sectitle("Summary")
  #v(0.30em)
  #par(leading: 0.55em)[#text(size: 9.5pt, data.summary)]
  #v(0.22em)
]

// ───────── Education ─────────

#if data.education.len() > 0 [
  #sectitle("Education")
  #for (i, e) in data.education.enumerate() [
    #if i > 0 [#v(0.3em)]
    #educationentry(e.institution, e.school, e.location, e.dates, e.degree, e.gpa)
  ]
]

// ───────── Work Experience ─────────

#if data.experiences.len() > 0 [
  #sectitle("Work Experience")
  #for (i, exp) in data.experiences.enumerate() [
    #if i > 0 [#v(0.12em)]
    #jobentry(exp.company, exp.title, exp.location, exp.dates)
    #bullet_items(exp.bullets)
  ]
]

// ───────── Technical Skills ─────────

#if data.skills.len() > 0 [
  #sectitle("Technical Skills")
  #grid(
    columns: (auto, 1fr),
    column-gutter: 10pt,
    row-gutter: 0.42em,
    ..data.skills.map(s => (
      text(weight: "bold")[#s.category:],
      [#s.items.join(", ")],
    )).flatten()
  )
]

// ───────── Projects ─────────

#if data.projects.len() > 0 [
  #sectitle("Projects")
  #for p in data.projects [
    #projectentry(p.title, p.at("descriptor", default: none), p.date)
    #if p.text != none and p.text != "" [
      #bullet_items((p.text,))
    ]
  ]
]

// ───────── Certifications ─────────

#if data.at("certifications", default: ()).len() > 0 [
  #sectitle("Certifications")
  #for c in data.certifications [
    #projectentry(c.title, none, c.date)
    #if c.at("text", default: none) != none and c.text != "" [
      #bullet_items((c.text,))
    ]
  ]
]

// ───────── Open Source Contributions ─────────

#if data.at("open_source", default: ()).len() > 0 [
  #sectitle("Open Source Contributions")
  #for p in data.open_source [
    #projectentry(p.title, p.at("descriptor", default: none), p.date)
    #if p.text != none and p.text != "" [
      #bullet_items((p.text,))
    ]
  ]
]

// ───────── Page-count metadata for validator ─────────

#context [
  #metadata((pages: counter(page).final().first()))<naavik-meta>
]
