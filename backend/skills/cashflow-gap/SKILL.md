---
name: cashflow-gap
description: Project the SME's cash balance and expose the gap between money going out and LC proceeds arriving.
node: cashflow
version: 0.1.0
---

## When to use

Before the exporter commits to the production and shipment schedule. Supplier
deposits and wages go out weeks before LC proceeds arrive at tenor; this skill
quantifies the trough and whether the SME survives it without emergency
borrowing.

## Method

1. Collect outflow events and dates: supplier deposit (often 30% at order),
   balance on shipment, wages/overheads, and Bangladesh clearance charges
   (duty/VAT/AIT via `calc_landed_cost` — the buyer's cost, but confirm who
   pays which line under the Incoterm; FOB means the exporter pays nothing at
   clearance).
2. Collect inflows: LC proceeds at tenor (sight = on compliant presentation;
   usance = tenor days after acceptance), any existing receivables.
3. Call `project_cash_flow` with the event list, opening balance and a 90-day
   horizon; it returns daily balances, the minimum balance and the days below
   zero. Do not build the projection yourself.
4. Identify the trough: `min_balance_day` and `min_balance_minor` from the
   projection; name the events bracketing it.
5. Test the LC tenor against the gap: if proceeds land after the trough, the
   gap must be bridged (trade finance offer, deposit renegotiation, or a
   shorter usance).
6. Run what-ifs the tool supports: shift the shipment date by a week, delay a
   supplier balance, or assume a document discrepancy pushes payment one
   presentation cycle (~10-15 days).

## Tools & rules

Tools: `project_cash_flow` (compute — 90-day projection with what-if inputs),
`calc_landed_cost` (compute — clearance-cost events where the exporter pays).
Rules: `cash-deposit-outflow-timing`, `cash-lc-tenor-inflow`, `cash-min-balance-floor`.

## Output format

The node stores the tool result in `state.cash_projection`
(`CashProjectionState`: daily balances, `min_balance_minor`, `min_balance_day`,
`days_below_zero`). Your explanation names the trough day, the causative
events, the days below zero, and whether the finance offer closes the gap.

## Common pitfalls

- Counting LC proceeds from the shipment date instead of from compliant
  presentation plus tenor; a 90-day usance paid 20 days late shifts the trough
  by the same 20 days.
- Forgetting wages and rent between the deposit and shipment — the trough is
  rarely on a document date.
- Treating the buyer's clearance duties as the exporter's outflow; follow the
  Incoterm before adding a `calc_landed_cost` event.
- Reporting the average balance instead of the minimum — solvency cares about
  the worst day only.
