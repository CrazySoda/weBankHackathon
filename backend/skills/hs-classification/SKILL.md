---
name: hs-classification
description: Classify goods under the HS using the GRI and obtain candidate codes with confidence.
node: compliance
version: 0.1.0
---

## When to use

Whenever the LC, LCA, invoice and customs declarations must agree on one HS
code, or when a duty/VAT/rebate rate is about to be applied to a line. The HS
code drives the Bangladesh duty stack and the China rebate rate, so a wrong
code corrupts every number downstream.

## Method

1. Determine the classification from the goods themselves — name, material,
   function, degree of completion — not from the code someone wrote earlier.
2. Apply GRI 1: classification is determined by the terms of the headings and
   any relative section or chapter notes; a heading that covers the goods
   decides before any other rule is consulted.
3. GRI 2(a): incomplete or unfinished articles with the essential character of
   complete articles classify as the complete article (e.g. unassembled,
   flat-packed luminaires shipped for assembly).
4. GRI 2(b)/3: for mixtures and composite goods, GRI 3(a) prefers the most
   specific description; GRI 3(b) classifies by essential character (material,
   function, value); GRI 3(c) falls back to the last applicable heading.
5. GRI 4: goods not covered elsewhere classify under the heading for the most
   similar goods.
6. GRI 6: apply the same rules at subheading level, comparing subheadings
   within one heading only, mutatis mutandis — the six-digit code is where
   duty lines actually live.
7. Call `suggest_hs_code` with the full goods description; treat its output as
   candidates with confidence — never auto-select. Compare candidates against
   the code stated in the LC/LCA.
8. On conflict between the stated code and your best candidate, raise a
   `warn` (or `block` when duty rates diverge materially) and let the human
   confirm before `calc_landed_cost` or `calc_export_vat_refund` run.

## Tools & rules

Tools: `suggest_hs_code` (compute — candidates + confidence, never
auto-selects), `lookup_rules` (read — tariff and note text).
Rules: `gri-heading-first`, `gri-composite-essential-character`,
`gri-subheading-comparison`, `hs-stated-code-conflict`.

## Output format

One `Finding` (`check_id` `hs-classification`) per conflict: quote the goods
description as evidence, name the candidate heading and the stated heading,
and state which downstream calculators must re-run if the code changes.

## Common pitfalls

- Classifying by trade name or marketing name — the GRI work on objective
  properties (material, function, construction).
- Comparing subheadings across different headings under GRI 6 — that is a
  heading-level question, do it at step 2.
- Ignoring chapter notes: Note 3 to Chapter 84 (function machines) or
  Section XVI Note 3 (composite machines) routinely override intuition.
- Treating the model's top candidate as decided; only a human or a binding
  ruling fixes the code.
