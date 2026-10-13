---
name: bd-import-docs
description: Verify the Bangladesh import-side documents and duty lines the deal must satisfy.
node: compliance
version: 0.1.0
---

## When to use

The buyer clears the goods in Bangladesh under an LC. Use this skill to check
that the import-side paperwork chain is complete and that the duty lines the
buyer will pay (which feed `calc_landed_cost`) match the HS code the goods
will actually be classified under.

## Method

1. Confirm the LCA (Letter of Credit Authorisation) exists and its amount,
   currency and beneficiary match the sales contract and the LC.
2. Confirm the importer holds a valid IRC (Import Registration Certificate)
   for the goods' category; a commercial importer's IRC covers the HS
   chapters it is registered for.
3. Reconcile the LC's HS code (and the LCA's) against `suggest_hs_code`
   candidates for the actual goods; a wrong HS line changes every duty rate.
4. Check the Bangladesh duty stack for that HS line: CD (customs duty), RD
   (regulatory duty), VAT, AIT (advance income tax), AT (advance tax) — these
   are the inputs `calc_landed_cost` needs; flag any that the documents leave
   ambiguous.
5. Check pre-shipment inspection (PSI) requirements: if the LCA or the
   public-procurement context requires PSI, the shipment must carry a clean
   inspection certificate from the appointed agency.
6. Check endorsement chain: LC advised → LCA issued → shipment within LCA
   validity; an expired LCA blocks negotiation.

## Tools & rules

Tools: `lookup_rules` (read — Bangladesh Customs tariff and import policy
text), `check_lc_documents` (compute — LC vs LCA vs invoice field match).
Rules: `bd-lca-required`, `bd-irc-scope`, `bd-ait-hs-rate`, `bd-psi-certificate`.

## Output format

One `Finding` per gap (`check_id` `bd-import-docs`): `block` for a missing
LCA/IRC or expired validity, `warn` for duty-line ambiguity (feed the assumed
rate to `calc_landed_cost` and say so), `info` for advisory items.

## Common pitfalls

- AIT is a percentage of assessable value (not of duty) for most lines —
  confusing the base skews landed cost by the AIT rate itself.
- RD compounds on CD-inclusive value in the tariff formula; do not apply RD
  to the raw CIF value.
- PSI certificates are shipment-specific; a template or another shipment's
  certificate is a block, not a warn.
- Bangladesh import policy changes by fiscal year (July-June); check the rule
  version in force at shipment date, not at planning date.
