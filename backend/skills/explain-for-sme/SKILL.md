---
name: explain-for-sme
description: Turn the deal's findings and numbers into plain language a small-business owner can act on.
node: report
version: 0.1.0
---

## When to use

At the end of every run, when the report is assembled for the exporter. The
readers are a micro-exporter and their family staff: no trade-finance
vocabulary, no tolerance for hedged numbers. Everything numeric is already
fixed upstream — this skill changes wording, never values.

## Method

1. Read the summary inputs from state only: findings (with severity and
   status), FX options, cash projection, finance offer, policy decision,
   receipt or escalation reason.
2. Lead with the outcome in one sentence: what the deal can do next (ship /
   fix one thing / get a correction / stop).
3. One short section per open finding: what is wrong, in one sentence, then
   the fix. Name the document and field ("the sales contract says Qingdao;
   your goods leave from Shenzhen"), never a rule citation as the
   explanation.
4. Translate terms: usance → "payment arrives N days after shipping papers
   are accepted"; discrepancy → "mismatch"; waiver → "you agreed to accept
   this and signed"; AIT → "advance income tax paid at Bangladesh customs".
5. State money exactly as computed upstream: currency + amount in plain
   numerals, one decimal at most, and say who pays it. Never convert, round,
   sum or derive any figure.
6. Close with the immediate next action and its deadline ("send the port
   correction request to your buyer before 30 June").
7. For escalated deals: say plainly what stopped the deal and that nothing
   was paid.

## Tools & rules

Tools: none — this skill needs no tools and never calls one.
Rules: `sme-plain-language`, `sme-numbers-fixed-upstream`, `sme-one-action-next`.

## Output format

A short summary (5-10 sentences) in the report: outcome sentence first, then
findings as "problem + fix", the money facts as fixed upstream, and one
explicit next action. No tables, no rule ids, no jargon.

## Common pitfalls

- Re-explaining with rule numbers ("Art. 14(d) inconsistency") — the reader
  does not know the articles; describe the mismatch itself.
- Softening a block finding ("minor documentation issue may...") — if the
  deal is stopped, the first sentence must say so.
- Introducing derived numbers ("about 2,000 dollars at today's rate") — all
  arithmetic is forbidden here; quote state figures verbatim.
- A wall of findings with no priority — order by severity, then by deadline.
