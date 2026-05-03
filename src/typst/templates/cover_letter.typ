// Naavik cover letter — 4-section letter + signature block.
//
// Per BACKEND.md § K.4. Consumes JSON via `sys.inputs.data` (path to JSON file).
//
// Required JSON shape:
//   {
//     "profile": {"full_name": str, "email": str, "phone": str | null,
//                 "location": str | null},
//     "job": {"company": str, "role": str},
//     "letter": {"intro": str, "body": str, "why_company": str, "close": str},
//     "today": str,  // pre-formatted date e.g. "May 3, 2026"
//   }

#let data = json.decode(sys.inputs.data)

#set page(
  paper: "us-letter",
  margin: (x: 1in, y: 1in),
)

#set text(
  font: ("Helvetica", "Arial", "Liberation Sans"),
  size: 11pt,
  fill: rgb("#111111"),
)
#set par(leading: 0.65em, justify: false)

// ───────── Sender block (top-right) ─────────

#align(right)[
  #text(weight: "bold", size: 11pt, data.profile.full_name)
  #linebreak()
  #if data.profile.location != none [#data.profile.location #linebreak()]
  #data.profile.email
  #if data.profile.phone != none [
    #linebreak()
    #data.profile.phone
  ]
]

#v(0.5em)
#text(size: 10pt, data.today)
#v(1em)

// ───────── Recipient ─────────

Hiring Team
#linebreak()
#text(weight: "bold", data.job.company)

#v(0.8em)

Dear Hiring Manager,

#v(0.6em)

// ───────── Body sections ─────────

#data.letter.intro

#v(0.5em)

#data.letter.body

#v(0.5em)

#data.letter.why_company

#v(0.5em)

#data.letter.close

#v(1em)

Sincerely,
#linebreak()
#text(weight: "bold", data.profile.full_name)

// ───────── Page-count metadata for validator ─────────

#context [
  #metadata((pages: counter(page).final().first()))<naavik-meta>
]
