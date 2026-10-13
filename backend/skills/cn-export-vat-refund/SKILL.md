---
name: cn-export-vat-refund
description: Work out the China export VAT refund due on this shipment and what can void it.
node: compliance
version: 0.1.0
---

## When to use

Every deal: the Shenzhen exporter's margin depends on the refund. Use it to
determine the rebate rate for the goods' HS code, check the documentation
that makes the refund claimable, and feed the exact refund into
`calc_export_vat_refund`.

## Method

1. Fix the HS code (use `suggest_hs_code` if the LC and invoice disagree) —
   the rebate rate is set per HS line, not per product name.
2. Look up the rebate rate for that HS line: China's export rebate tiers are
   13%, 9%, 6% and 0% (full rebate to no rebate; some lines are export-
   restricted or taxed instead).
3. Collect the claim prerequisites: VAT special invoice from the supplier (or
   self-produced goods declaration), customs export declaration matching the
   invoice, foreign-exchange receipt, and declaration inside the claim window
   after the export date.
4. Cap check: the refund can never exceed the input VAT actually paid on the
   goods (invoice VAT); for manufacturers the 免抵退 (exempt-credit-refund)
   method offsets input VAT against domestic sales VAT first — only the
   residual is refunded.
5. Call `calc_export_vat_refund` with invoice value, rebate rate and input
   VAT; never compute the refund yourself.
6. Flag `block` conditions: rebate rate 0%, restricted goods, missing VAT
   special invoice, export declaration mismatch, or an expired claim window.

## Tools & rules

Tools: `calc_export_vat_refund` (compute — the refund figure),
`lookup_rules` (read — STA/State Taxation Administration notices and the
current rebate table). Rules: `cn-vat-rebate-tiers`, `cn-vat-input-cap`,
`cn-vat-claim-window`, `cn-vat-exempt-credit-refund`.

## Output format

One `Finding` (`check_id` `cn-vat-refund`): `info` when the refund computes
cleanly (state the rebate rate and CNY amount in the explanation, quoting the
tool output), `warn` for documentation gaps that delay payment, `block` when
the refund is legally unavailable.

## Common pitfalls

- Rebate rate is not the VAT rate: a 13%-VAT good can carry a 9% rebate, and
  the difference is a cost, not an error — do not "correct" it.
- Refund base is FOB-equivalent invoice value excluding supported burdens;
  using CIF pulls in freight and overstates the claim.
- Report as export proceeds in FX within the window, or the refund freezes.
- Trading companies refund on the purchase invoice; manufacturers on the
  免抵退 method — applying the wrong method wrongs the number by design.
