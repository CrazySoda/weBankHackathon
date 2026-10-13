---
name: fx-route-compare
description: Compare FX conversion routes on what actually lands in the account, not on headline rates.
node: fx
version: 0.1.0
---

## When to use

The export proceeds arrive in USD (or are invoiced in USD) and the Shenzhen
SME spends CNY. Use this skill whenever the deal has an FX leg: choose the
route (bank wire, cross-border CNY settlement, payment provider) that nets the
most CNY after spread and fees.

## Method

1. Fetch route quotes with `get_fx_quotes` (sandbox, synthetic and labelled
   as such): note each route's quoted rate and any fixed fees.
2. Establish the mid-market reference rate for the same pair and timestamp —
   the spread of a route is its distance from mid, not from another route.
3. For each route, call `calc_effective_fx_cost` with the quoted rate, fees
   and amount; it returns the effective rate, spread in basis points and net
   proceeds. Never compute these yourself.
4. Compare routes on net minor units received — identical currencies, same
   settlement-date assumption. A "zero-commission" route with a 150 bp spread
   can lose to a fee-charging route near mid.
5. Check the path: a direct CNY leg (cross-border RMB settlement) avoids one
   conversion (USD→CNY) entirely; routes via an intermediate currency pay two
   spreads.
6. Note timing caveats: quotes are indicative and expire; tenor mismatch
   (receipt date vs conversion date) is a risk, not a cost — flag it, do not
   bake it into the number.
7. Report the ranking with per-route spread (bp), fixed fee and net amount.

## Tools & rules

Tools: `get_fx_quotes` (read — synthetic quotes), `calc_effective_fx_cost`
(compute — effective rate, spread, net proceeds).
Rules: `fx-mid-market-reference`, `fx-spread-plus-fees`, `fx-quote-freshness`.

## Output format

The node stores one `FxOption` per route in `state.fx_options` (tool-computed
`net_minor`, `effective_rate_scaled`, `spread_bp`, `fee_minor`, `synthetic`
flag). Your narrative names the best route, the bp spread versus mid, and any
caveat — quoting only figures that appear in tool output.

## Common pitfalls

- Comparing quoted rates from different timestamps — always compare against
  one mid-market reference.
- Ignoring receiving-bank charges that land after conversion; a route that
  wins by 8 bp can lose to a 15 USD correspondent fee on small deals.
- Treating the sandbox quotes as live market data — they are synthetic and
  labelled; say so in the explanation.
- Rounding or converting minor units yourself; the calculators own all
  arithmetic (rule 0.2).
