// Naavik 1-page resume — NEU style.
//
// Per AGENTS.md § Owner Profile: Helvetica, 0.3in margins, compact 1-page.
// Consumes JSON via `sys.inputs.data` (passed as a path to a JSON file).
//
// Required JSON shape (validated at compile-time by document_generator):
//   {
//     "profile": {
//       "full_name": str,
//       "headline": str,
//       "email": str,
//       "phone": str | null,
//       "location": str | null,
//       "portfolio_url": str | null,
//       "linkedin_handle": str | null,
//       "github_handle": str | null,
//       "summary_short": str | null,
//     },
//     "experiences": [
//       {"company": str, "role": str, "location": str | null,
//        "start_date": str, "end_date": str | null,
//        "bullets": [str]  // already trimmed by AI
//       }
//     ],
//     "education": [
//       {"institution": str, "degree": str, "start_date": str,
//        "end_date": str | null, "gpa": str | null}
//     ],
//     "skills": [{"category": str, "items": [str]}],
//     "projects": [{"title": str, "text": str, "link": str | null}],
//   }

#let data = json.decode(sys.inputs.data)

#set page(
  paper: "us-letter",
  margin: 0.3in,
)

#set text(
  font: ("Helvetica", "Arial", "Liberation Sans"),
  size: 9.5pt,
  fill: rgb("#111111"),
)
#set par(leading: 0.45em)

#let section_title(name) = {
  v(0.4em)
  text(weight: "bold", size: 10.5pt, upper(name))
  v(-0.45em)
  line(length: 100%, stroke: 0.5pt + rgb("#000000"))
  v(-0.05em)
}

#let bullet_line(t) = {
  text("• " + t)
  linebreak()
}

// ───────── Header ─────────

#align(center)[
  #text(weight: "bold", size: 14pt, data.profile.full_name)
  #linebreak()
  #text(size: 9.5pt, data.profile.headline)
  #linebreak()
  #text(size: 9pt)[
    #if data.profile.email != none [#data.profile.email]
    #if data.profile.phone != none [ · #data.profile.phone]
    #if data.profile.location != none [ · #data.profile.location]
  ]
  #if (data.profile.linkedin_handle != none
       or data.profile.github_handle != none
       or data.profile.portfolio_url != none) [
    #linebreak()
    #text(size: 9pt)[
      #if data.profile.linkedin_handle != none [linkedin.com/in/#data.profile.linkedin_handle]
      #if data.profile.github_handle != none [ · github.com/#data.profile.github_handle]
      #if data.profile.portfolio_url != none [ · #data.profile.portfolio_url]
    ]
  ]
]

// ───────── Summary ─────────

#if data.profile.summary_short != none [
  #section_title("Summary")
  #data.profile.summary_short
]

// ───────── Experience ─────────

#section_title("Experience")

#for exp in data.experiences [
  #grid(
    columns: (1fr, auto),
    [#text(weight: "bold", exp.role) — #text(weight: "bold", exp.company)
     #if exp.location != none [, #exp.location]],
    [#text(size: 9pt)[#exp.start_date — #if exp.end_date != none [#exp.end_date] else [Present]]],
  )
  #v(-0.3em)
  #for b in exp.bullets [
    #bullet_line(b)
  ]
  #v(0.15em)
]

// ───────── Skills ─────────

#section_title("Skills")

#for skill_group in data.skills [
  #text(weight: "bold", skill_group.category + ": ")
  #skill_group.items.join(", ")
  #linebreak()
]

// ───────── Projects ─────────

#if data.projects.len() > 0 [
  #section_title("Projects")
  #for p in data.projects [
    #text(weight: "bold", p.title)
    #if p.link != none [ — #text(size: 9pt, p.link)]
    #linebreak()
    #p.text
    #linebreak()
  ]
]

// ───────── Education ─────────

#if data.education.len() > 0 [
  #section_title("Education")
  #for e in data.education [
    #grid(
      columns: (1fr, auto),
      [#text(weight: "bold", e.institution) — #e.degree
       #if e.gpa != none [ (GPA: #e.gpa)]],
      [#text(size: 9pt)[#e.start_date — #if e.end_date != none [#e.end_date] else [Present]]],
    )
  ]
]

// ───────── Page-count metadata for validator ─────────

#context [
  #metadata((pages: counter(page).final().first()))<naavik-meta>
]
