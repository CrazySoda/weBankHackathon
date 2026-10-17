"""Single source of the field dicts the deterministic LC battery consumes.

``compliance`` creates findings and ``verify`` recomputes them from the same
inputs; building both from one function guarantees a finding can never be
produced from data the verifier does not see (which would silently close it).
"""

from __future__ import annotations

from typing import Any

from app.graph.state import DealState

# Fields read from the bank's presentation schedule and merged into the
# invoice dict. Invoice values always win; the schedule only fills gaps.
SCHEDULE_FIELDS = ("presentation_date", "shipment_date")


def fields_of(state: DealState, kind: str) -> dict[str, Any]:
    for d in state.current_extracted:
        if d.kind == kind:
            return {f.name: f.value for f in d.fields}
    return {}


def lc_check_inputs(state: DealState) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return ``(lc_fields, invoice_fields)`` for ``run_lc_checks``."""
    lc = fields_of(state, "letter_of_credit")
    invoice = fields_of(state, "commercial_invoice")
    schedule = fields_of(state, "presentation_schedule")
    for name in SCHEDULE_FIELDS:
        if schedule.get(name) is not None and invoice.get(name) is None:
            invoice[name] = schedule[name]
    return lc, invoice
