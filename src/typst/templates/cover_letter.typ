// Naavik cover letter — real business-letter structure.
//
// Sender block, date, recipient block (hiring manager when known),
// greeting, body paragraphs (empty sections are skipped — no blank gaps),
// close + signature. Concise: a solid half to ~3/4 page.
//
// Required JSON shape:
//   {
//     "profile": {"full_name": str, "email": str, "phone": str | null,
//                 "location": str | null},
//     "job": {"company": str, "role": str},
//     "recipient": {"name": str | null, "title": str | null},
//     "greeting": str,                       // "Dear Jane Doe," / "Dear Hiring Team,"
//     "letter": {"intro": str, "body": str, "why_company": str, "close": str},
//     "today": str,                          // pre-formatted, e.g. "May 3, 2026"
//   }

#let data = json.decode(sys.inputs.data)

#set document(title: data.profile.full_name + " — Cover Letter")

#set page(paper: "us-letter", margin: (x: 1in, y: 0.9in))

#set text(
  font: ("Helvetica", "Arial", "Liberation Sans"),
  size: 10.5pt,
  fill: rgb("#111111"),
  features: ("liga": 0, "clig": 0, "dlig": 0),
)
#set par(leading: 0.62em, justify: false)

// ───────── Sender block ─────────

#text(weight: "bold", size: 12pt, data.profile.full_name)
#v(-0.5em)
#text(size: 9pt, fill: rgb("#333333"))[
  #{
    let parts = ()
    if data.profile.location != none { parts.push(data.profile.location) }
    parts.push(data.profile.email)
    if data.profile.phone != none { parts.push(data.profile.phone) }
    parts.join(" · ")
  }
]

#v(0.9em)
#text(size: 10pt, data.today)
#v(0.9em)

// ───────── Recipient block ─────────

#if data.recipient.name != none [
  #data.recipient.name
  #if data.recipient.title != none [
    #linebreak()
    #text(size: 9.5pt, fill: rgb("#333333"), data.recipient.title)
  ]
  #linebreak()
] else [
  Hiring Team
  #linebreak()
]
#text(weight: "bold", data.job.company)
#linebreak()
#text(size: 9.5pt, fill: rgb("#333333"), "Re: " + data.job.role)

#v(0.9em)

#data.greeting

#v(0.35em)

// ───────── Body paragraphs (skip empties — no blank gaps) ─────────

#{
  let sections = (data.letter.intro, data.letter.body, data.letter.why_company, data.letter.close)
  for s in sections {
    if s != none and s.trim() != "" {
      par(s)
      v(0.35em)
    }
  }
}

#v(0.5em)

Sincerely,
#linebreak()
#text(weight: "bold", data.profile.full_name)

// ───────── Page-count metadata for validator ─────────

#context [
  #metadata((pages: counter(page).final().first()))<naavik-meta>
]
