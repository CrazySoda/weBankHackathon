---
name: lc-ucp600-check
description: Check commercial documents for consistency with the letter of credit.
node: compliance
version: 0.1.0
---

## When to use

Use for any deal paid under a documentary credit. Run it on the LC plus the
commercial invoice, packing list and (if present) bill of lading, before the
exporter presents documents — a discrepancy found now costs a correction, the
same discrepancy found by the bank costs a refusal fee and the tenor.

## Method

1. Establish the credit's terms: expiry date and place, latest shipment date,
   presentation period, available-with/by, partial shipments and transshipment
   allowed or not (UCP 600 Art. 6).
2. Check the presentation window: documents must be presented on or before
   expiry AND, when the credit demands a transport document, within 21
   calendar days after the shipment date (Art. 14(c)).
3. Check the commercial invoice: amount not exceeding the credit amount
   (Art. 18(b)), currency identical to the credit, goods description matching
   the credit (Art. 18(c)); the invoice must be issued by the beneficiary.
4. Check consistency across documents: quantities, weights, marks and
   descriptions, consignee/notify parties, ports of loading/discharge
   (Art. 14(d)) — data need not be identical, but must not conflict.
5. Check the transport document against Art. 19-25 for the credit's chosen
   mode, including on-board date, carrier identification and clean status.
6. Run `check_lc_documents` for the deterministic field comparison; treat its
   output as evidence, not as the verdict.
7. Use `lookup_rules` to quote the exact article text behind each suspected
   discrepancy.
8. Classify each discrepancy: `block` (bank would refuse: late shipment,
   over-shipment, amount exceeded, missing document), `warn` (fixable data
   conflict), `info` (non-conflicting variation allowed by Art. 14(d)).

## Tools & rules

Tools: `check_lc_documents` (compute — field-level comparison), `lookup_rules`
(read — article text). Rules: `ucp600-art6-expiry`, `ucp600-art14c-presentation-period`,
`ucp600-art14d-consistency`, `ucp600-art18b-invoice-amount`, `ucp600-art14d-typos`.

## Output format

One `Finding` per discrepancy: `check_id` `lc-consistency`, the UCP article as
`rule_id`, severity per step 8, `fixable` true for document-side corrections,
and `evidence` quoting both sides of the conflict (LC clause vs document text).

## Common pitfalls

- "About"/"approximately" in the credit permits ±10% on amount, quantity or
  unit price (Art. 30(a)); without it, packing tolerance of ±5% still applies
  to quantity when not stipulated in packing units (Art. 30(b)). Do not flag
  within tolerance.
- Typo-level differences that do not create conflict with other data (e.g.
  "SHENZHEN" vs "SHENZHEN CITY") are acceptable under Art. 14(d).
- Partial shipment is allowed unless the credit prohibits it (Art. 31(b)).
- Truncated drafts drawn under the credit: do not require documents the credit
  does not call for; banks examine on the face of the documents only (Art. 14(a)).
