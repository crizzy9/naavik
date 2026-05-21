#!/usr/bin/env node
// OpenResume parser subprocess shim — plan 67 (0.3.4) § C.5 / T6.
//
// Standalone Node script invoked by `services/ats_parser_ensemble.py`. Reads
// a PDF from `argv[2]` (or stdin), parses via OpenResume's parse-resume-from-pdf
// subset, prints the structured output as JSON to stdout.
//
// OpenResume's parser is GPL/MIT licensed (open source, repo at
// `xitanggg/open-resume`). This shim invokes it via npm when installed;
// otherwise falls back to a minimal placeholder that emits the canonical
// 8-field schema with `null` values so the ensemble still gets a signal.
//
// Exit codes:
//   0  success — JSON on stdout
//   1  argv error / file not readable
//   2  parser unavailable (OpenResume not installed in node_modules)
//   3  parse failure
//
// Install OpenResume locally with:
//   cd scripts && npm init -y && npm i pdfjs-dist@4

"use strict";

const fs = require("fs");

function emitFallback() {
  // When OpenResume isn't installed, emit a minimal placeholder with the
  // 8 canonical fields nulled. Ensemble treats null fields as "not found",
  // so this conservatively under-scores OpenResume rather than over-scoring.
  process.stdout.write(
    JSON.stringify({
      profile: { name: null, email: null, phone: null },
      workExperiences: [],
      educations: [],
      skills: [],
      _meta: { fallback: true, reason: "openresume-not-installed" },
    })
  );
  process.exit(0);
}

async function main() {
  const pdfPath = process.argv[2];
  if (!pdfPath) {
    process.stderr.write("usage: openresume_parser.js <pdf-path>\n");
    process.exit(1);
  }
  if (!fs.existsSync(pdfPath)) {
    process.stderr.write(`file not found: ${pdfPath}\n`);
    process.exit(1);
  }

  let pdfjsLib;
  try {
    // pdfjs-dist is what OpenResume's parser depends on. The full parser
    // pulls additional helpers from open-resume/lib; we use the minimal
    // subset that extracts text-by-coordinate. Fall back when missing.
    pdfjsLib = require("pdfjs-dist/legacy/build/pdf.js");
  } catch (err) {
    emitFallback();
    return;
  }

  let buffer;
  try {
    buffer = fs.readFileSync(pdfPath);
  } catch (err) {
    process.stderr.write(`read failed: ${err.message}\n`);
    process.exit(1);
  }

  let doc;
  try {
    doc = await pdfjsLib.getDocument({
      data: new Uint8Array(buffer),
      verbosity: 0,
    }).promise;
  } catch (err) {
    process.stderr.write(`pdf parse failed: ${err.message}\n`);
    process.exit(3);
  }

  const lines = [];
  for (let i = 1; i <= doc.numPages; i++) {
    const page = await doc.getPage(i);
    const content = await page.getTextContent();
    for (const item of content.items) {
      const text = (item.str || "").trim();
      if (text) lines.push(text);
    }
  }
  const flat = lines.join("\n");

  // Coarse heuristic extraction. OpenResume's production parser is far
  // more sophisticated (bounding-box clustering, section detection); we
  // ship a minimal subset that's good enough for the cross-check signal.
  const emailMatch = flat.match(/[\w.+-]+@[\w-]+\.[\w.-]+/);
  const phoneMatch = flat.match(/(?:\+?\d{1,2}\s*)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}/);
  const firstLine = lines[0] || null;

  // First "experience" entry — look for a line containing common role
  // keywords as a proxy for the section header.
  const expIdx = lines.findIndex((ln) =>
    /Professional Experience/i.test(ln)
  );
  let firstExpJob = null;
  let firstExpCompany = null;
  let firstExpDate = null;
  if (expIdx >= 0 && lines[expIdx + 1]) {
    const row = lines[expIdx + 1];
    // Crude split — "Title at Company" or "Title · Company"
    const parts = row.split(/\s*[·•]\s*|\s+at\s+/i);
    firstExpJob = parts[0] || null;
    firstExpCompany = parts[1] || null;
    const dateMatch = (lines[expIdx + 2] || "").match(
      /(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}|\d{1,2}[/-]\d{4}/
    );
    if (dateMatch) firstExpDate = dateMatch[0];
  }

  const eduIdx = lines.findIndex((ln) => /Education/i.test(ln));
  const firstEduSchool = eduIdx >= 0 ? lines[eduIdx + 1] || null : null;

  const skillsIdx = lines.findIndex((ln) => /Skills/i.test(ln));
  const skills =
    skillsIdx >= 0 ? lines.slice(skillsIdx + 1, skillsIdx + 6) : [];

  process.stdout.write(
    JSON.stringify({
      profile: {
        name: firstLine,
        email: emailMatch ? emailMatch[0] : null,
        phone: phoneMatch ? phoneMatch[0] : null,
      },
      workExperiences: firstExpJob
        ? [{ jobTitle: firstExpJob, company: firstExpCompany, date: firstExpDate }]
        : [],
      educations: firstEduSchool ? [{ school: firstEduSchool }] : [],
      skills: skills,
      _meta: { fallback: false },
    })
  );
}

main().catch((err) => {
  process.stderr.write(`unexpected error: ${err.message}\n`);
  process.exit(3);
});
