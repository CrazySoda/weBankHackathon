---
name: sanctions-screening
description: Screen the deal parties against curated sanctions lists and judge each hit.
node: compliance
version: 0.1.0
---

## When to use

Every deal, before finance and approval. Screen the beneficiary, applicant,
issuing/advising banks, the carrying vessel and the buyer's declared address
against the curated consolidated lists. A missed sanctioned party blocks the
deal forever; a careless "clear" on a fuzzy match is the second-worst outcome.

## Method

1. Collect the screening names exactly as they appear in the documents
   (beneficiary, buyer, banks, vessel name), plus known aliases.
2. Call `screen_sanctions` for each name. It matches against the curated
   UN Security Council consolidated list and partner lists on file.
3. For each candidate hit, disambiguate using secondary identifiers: date of
   birth, nationality, passport/registration number, address, vessel IMO.
   A name match without identifier support is not a confirmed hit.
4. Beware name-matching traps: transliteration variance in Arabic and Chinese
   names (e.g. "Al-Nusra"/"An-Nusrah"), initials vs full names, reversed
   given/family order for Chinese names, and common surnames producing
   systematic false positives.
5. Apply ownership logic: an entity not itself listed can still be blocked if
   it is majority-owned (50%+ rule) by listed persons — screen the corporate
   family, not just the counterparty of record.
6. Close each non-hit explicitly: state the screened name, the list version
   used, and the identifiers used to reject each candidate — an undocumented
   clearance is not a clearance.
7. Any confirmed or probable hit is `block` and routes the deal to `escalate`.
   Never waive a sanctions finding in this harness.

## Tools & rules

Tools: `screen_sanctions` (read — curated list matching),
`lookup_rules` (read — screening procedure text).
Rules: `unsc-consolidated-screening`, `sanctions-transliteration-variance`,
`sanctions-ownership-rule`, `sanctions-document-clearance`.

## Output format

One `Finding` (`check_id` `sanctions-screen`): `block` with the matched list
entry quoted in `evidence` for confirmed/probable hits; `info` documenting the
clearance (names screened, list version, candidates rejected and why).

## Common pitfalls

- Clearing on a low similarity score without recording which identifiers
  distinguished the candidate — that is an undocumented clearance.
- Screening only the exact spelling; edit-distance and phonetic variants of
  transliterated names carry most real hits.
- Forgetting the vessel: sanctioned shipping lines and flag-of-convenience
  vessels appear in the documents, not in the contract parties.
- Treating delisted entities as still blocked (or the reverse) — check the
  list version date against the screening date.
