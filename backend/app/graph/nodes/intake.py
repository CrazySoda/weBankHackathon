"""intake node: registers documents for extraction.

Deliberately boring: validation happened at the API boundary (size/type/scan).
The node just snapshots document refs into state; the fan-out router emits one
`extract_doc` Send per document.
"""

from __future__ import annotations

from typing import Any

from app.graph.state import DealState
from app.harness.hooks import NodeContext


def intake(state: DealState, ctx: NodeContext) -> dict[str, Any]:
    # documents were registered by the API before the run started; nothing to
    # decide here. Emit an audit-visible marker of the batch size only.
    return {}
