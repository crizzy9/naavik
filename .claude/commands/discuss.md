---
description: Spawn manager + architect + engineer (and hacker/designer if relevant) in parallel via Task to debate a topic — PR, plan, design idea, bug, or architectural choice. Returns a synthesis with dissents.
argument-hint: <topic, PR URL, plan path, or design doc path>
---

Topic: $ARGUMENTS

1. **Classify** topic into one of: PR / plan / design / bug / open-question / scope. Print classification so user can redirect if you got it wrong.
2. **Pick 3–4 relevant agents** from `{manager, architect, engineer, devops, hacker, designer}`. Defaults:
   - **PR or bug**: engineer + hacker + devops (+ manager if PR is milestone-shaping).
   - **Plan or open-question**: manager + architect + engineer (+ hacker if it touches auth/secrets/scraping).
   - **Design or new screen**: designer + architect + engineer (+ manager if it changes ROADMAP scope).
   - **Architectural choice / tech-stack debate**: architect + engineer + hacker + devops (+ manager).
3. **In single message**, spawn chosen agents in parallel via Task w/ SAME prompt:

   > Give your independent take on: $ARGUMENTS.
   >
   > List your strongest argument, your steel-manned counter-argument, and your verdict.
   > Be specific to this repo: read `AGENTS.md`, `ROADMAP.md`, + artifact path / topic. Cite file paths + line numbers where relevant.
   > Cap your response at ~300 words.

4. **Synthesize** when all agents return:
   - Where they agree (one bullet per converged point).
   - Where they dissent (one bullet per disagreement, naming the agents).
   - Your recommended path (one paragraph).
   - **Ask user before acting** — `/discuss` is deliberation tool, not execution tool. If user wants to act on recommendation, they'll say so or invoke `/build` / `/plan` / `/triage-bug` next.
