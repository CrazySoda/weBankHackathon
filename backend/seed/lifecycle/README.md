# End-to-end LC lifecycle corpus (synthetic)

> Every party, number and identifier here is **invented**. Tax and refund rates for
> HS 9405 are **demo assumptions** (see `../rules/`, `demo_assumption: true`).
> Each PDF carries a "SYNTHETIC DEMO DOCUMENT" banner.

Four fictional Shenzhen to Chattogram LED-lamp deals under a documentary LC
(USD 100,000, CIF, 60 days after bill of lading). One software, four roles:
**seller**, **buyer**, **issuing bank**, **advising bank**.

| Deal | Scenario | Expected outcome |
|---|---|---|
| HD-01 | Clean lifecycle (hero) | approval, payout, CNY settlement |
| HD-02 | Invoice USD 120,000 against an LC of USD 100,000 | bank refuses (`lc-invoice-exceeds-lc`), corrected invoice, re-presentation, approval |
| HD-03 | Bill of lading dated after the LC latest shipment date | escalate (`lc-late-shipment`); only an LC amendment can cure it |
| HD-04 | Hidden white-text instructions on the commercial invoice | injection escalation (`hidden_text`, `instruction_like_phrase`) |

## Who produces what (HD-01)

| Step | Date | Actor | Documents |
|---|---|---|---|
| 1 | 2026-09-10 | seller uploads | D01 proforma invoice |
| 2 | 2026-09-15 | buyer uploads | D02 importer registration (IRC, TIN, BIN) |
| 3 | 2026-09-18 | buyer uploads | D03 LC application (LCA) |
| 4 | 2026-09-24 | **bank issues** | D04 documentary credit (MT700 style) |
| 5 | 2026-09-26 | **bank issues** | D05 LC advice to the seller |
| 6 | 2026-10-15 | seller uploads | D13 input VAT invoice summary (refund claim) |
| 7 | 2026-11-05 | seller uploads | D06 invoice, D07 packing list, D08 export customs declaration, D09 bill of lading, D10 certificate of origin, D11 insurance certificate |
| 8 | 2026-11-09 | seller + **bank** | D12 bill of exchange, D14 presentation schedule (day 8 of 21) |
| 9 | 2026-11-13 | **bank issues** | D15 examination result (4 banking days), D16 acceptance advice |
| 10 | 2026-11-13 | **bank issues** | D17 release of shipping documents to the **buyer** |
| 11 | 2026-11-24 | buyer uploads | D18 bill of entry (duty and VAT) |
| 12 | 2026-12-31 | **bank issues** | D19 payment advice, D20 FX and CNY settlement statement |

Release goes to the **buyer**: the endorsed bill of lading is what lets them
collect the goods. China no longer requires the export-proceeds verification form
(abolished 2012-08-01), so there is none in the set.

## Numbers come from `calc/`, not the generator

`tests/unit/test_lifecycle_data.py` recomputes every figure on the bank and customs
documents through the real calculators: the CNY settlement (`effective_fx_cost`),
the bill-of-entry tax stack (`import_tax_stack_bdt`) and the export VAT refund
(`export_vat_refund`, capped by input VAT in the hero deal). It also checks UCP 600
timing (21-day presentation, 5-banking-day examination), invoice, packing and
insurance arithmetic, and that only the poisoned invoice trips the injection screen.

## Regenerate

```bash
cd backend
uv run python -I seed/lifecycle/generate.py     # lifecycle.json + pdfs/
uv run python -I seed/verify_checksums.py       # byte-identical proof
```

## Known gaps

- The graph's `compliance` node runs the presentation-period check only when a
  `presentation_date` is on the invoice fields; the presentation schedule is not yet
  an extracted document kind. The ground truth composes it (`check_inputs_*`).
- Buyer, bank and seller roles exist in the data but not yet in the application
  (single-tenant demo). Role-based upload and release views are future work.
- Unverified rules (all of them, so far) are listed by `unverified_rule_ids()`.
