// Naavik 1-page resume — ATS-friendly variant (plan 66 / 0.3.1 § T6).
//
// Strict single-column; plain `•` bullets; MM/YYYY dates; ligature-disabled
// Helvetica; no header/footer with content; PDF/A-1b output (when typst
// supports it; the --pdf-standard flag is opt-in via the document_generator).
//
// Section headings use the cross-ATS allowlist exact strings:
// "Summary" / "Professional Experience" / "Education" / "Skills" / "Projects".
//
// Auto-selected for `Application.board` ∈ ATS-known set
// (Workday/Greenhouse/Lever/Ashby/LinkedIn). Manual + company-direct
// applications stay on the creative `onepage.typ` template.
//
// Required JSON shape (compatible with onepage.typ + tailored_headline):
//   {
//     "profile": {full_name, headline, email, phone, location,
//                 portfolio_url, linkedin_handle, github_handle,
//                 summary_short},
//     "tailored_headline": str | null,  // overrides profile.headline when present
//     "experiences": [{company, role, location, start_date, end_date, bullets}],
//     "education": [{institution, degree, start_date, end_date, gpa}],
//     "skills": [{category, items}],
//     "projects": [{title, text, link}],
//   }

#let data = json.decode(sys.inputs.data)

#set document(title: data.profile.full_name + " — Resume")

#set page(
  paper: "us-letter",
  margin: 0.3in,
)

// Ligatures disabled (T6.1) — prevents `fi`/`fl`/`ff` PUA Unicode that
// some ATS parsers (Taleo) cannot recover into separate characters.
#set text(
  font: ("Helvetica", "Arial", "Liberation Sans"),
  size: 10pt,
  fill: rgb("#000000"),
  features: ("liga": 0, "clig": 0, "dlig": 0),
)
#set par(leading: 0.45em, justify: false)

#let section_title(name) = {
  v(0.4em)
  text(weight: "bold", size: 11pt, name)
  v(-0.45em)
  line(length: 100%, stroke: 0.5pt + rgb("#000000"))
  v(-0.05em)
}

#let bullet_line(t) = {
  // Strict plain `•` (U+2022) per T6 ATS guidance.
  text("• " + t)
  linebreak()
}

// ───────── Header (single column; no grid) ─────────

#align(left)[
  #text(weight: "bold", size: 14pt, data.profile.full_name)
  #linebreak()
  // tailored_headline (T7) overrides profile.headline when present.
  #if "tailored_headline" in data and data.tailored_headline != none [
    #text(size: 10pt, data.tailored_headline)
  ] else [
    #text(size: 10pt, data.profile.headline)
  ]
  #linebreak()
  #text(size: 9pt)[
    #if data.profile.email != none [#data.profile.email]
    #if data.profile.phone != none [ #sym.bullet #data.profile.phone]
    #if data.profile.location != none [ #sym.bullet #data.profile.location]
  ]
  #if (data.profile.linkedin_handle != none
       or data.profile.github_handle != none
       or data.profile.portfolio_url != none) [
    #linebreak()
    #text(size: 9pt)[
      #if data.profile.linkedin_handle != none [linkedin.com/in/#data.profile.linkedin_handle]
      #if data.profile.github_handle != none [ #sym.bullet github.com/#data.profile.github_handle]
      #if data.profile.portfolio_url != none [ #sym.bullet #data.profile.portfolio_url]
    ]
  ]
]

// ───────── Summary ─────────

#if data.profile.summary_short != none [
  #section_title("Summary")
  #data.profile.summary_short
]

// ───────── Professional Experience ─────────

#section_title("Professional Experience")

#for exp in data.experiences [
  // Single-column layout: role/company on one line, dates on the next.
  // No grid — preserves ATS row-by-row parsing.
  #text(weight: "bold", exp.role) #sym.bullet #text(weight: "bold", exp.company)
  #if exp.location != none [, #exp.location]
  #linebreak()
  #text(size: 9pt)[#exp.start_date #sym.dash.en #if exp.end_date != none [#exp.end_date] else [Present]]
  #linebreak()
  #v(0.1em)
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
    #if p.link != none [ #sym.bullet #text(size: 9pt, p.link)]
    #linebreak()
    #p.text
    #linebreak()
  ]
]

// ───────── Education ─────────

#if data.education.len() > 0 [
  #section_title("Education")
  #for e in data.education [
    #text(weight: "bold", e.institution) #sym.bullet #e.degree
    #if e.gpa != none [ (GPA: #e.gpa)]
    #linebreak()
    #text(size: 9pt)[#e.start_date #sym.dash.en #if e.end_date != none [#e.end_date] else [Present]]
    #linebreak()
  ]
]

// ───────── Page-count metadata for validator ─────────

#context [
  #metadata((pages: counter(page).final().first()))<naavik-meta>
]
