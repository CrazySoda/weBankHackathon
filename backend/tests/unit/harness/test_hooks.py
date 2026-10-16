"""Node hook wrapper tests: budget, audit, fail-closed semantics."""

from app.audit.events import InMemoryAuditSink
from app.graph.state import DealState, ExtractedDoc, ExtractedField, SourceRef
from app.harness.budget import DealBudget
from app.harness.hooks import NodeContext, validate_state_invariants, wrap_with_hooks


def mk_state(**kw) -> DealState:
    return DealState(deal_id="d1", tenant_id="t1", **kw)


def mk_ctx(max_steps: int = 10) -> tuple[NodeContext, InMemoryAuditSink]:
    sink = InMemoryAuditSink()
    ctx = NodeContext(
        budget=DealBudget("d1", max_steps=max_steps, max_tokens=10**9, max_cost_minor=10**9),
        audit=sink,
    )
    return ctx, sink


def node_ok(state: DealState, ctx: NodeContext) -> dict:
    return {"amendment_draft": "x"}


def node_boom(state: DealState, ctx: NodeContext) -> dict:
    raise RuntimeError("exploded")


def node_forbidden(state: DealState, ctx: NodeContext) -> dict:
    return {"deal_id": "hacked"}


class TestBefore:
    async def test_emits_node_started_and_counts_step(self):
        ctx, sink = mk_ctx()
        wrapped = wrap_with_hooks("plan", node_ok, ctx)
        await wrapped(mk_state())
        kinds = [e.kind for e, _ in sink.events]
        assert kinds[0] == "node_started"
        assert ctx.budget.steps == 1

    async def test_budget_breach_returns_fatal_error(self):
        ctx, sink = mk_ctx(max_steps=1)
        wrapped = wrap_with_hooks("plan", node_ok, ctx)
        await wrapped(mk_state())  # step 1 ok
        update = await wrapped(mk_state())  # step 2 breaches (max_steps=1)
        assert update == {"fatal_error": "budget: steps 1 >= 1"}
        assert "budget_exceeded" in [e.kind for e, _ in sink.events]

    async def test_killed_budget_short_circuits(self):
        ctx, _sink = mk_ctx()
        ctx.budget.kill("operator stop")
        wrapped = wrap_with_hooks("plan", node_ok, ctx)
        update = await wrapped(mk_state())
        assert "fatal_error" in update


class TestAfter:
    async def test_emits_node_finished_with_summary(self):
        ctx, sink = mk_ctx()
        wrapped = wrap_with_hooks("plan", node_ok, ctx)
        update = await wrapped(mk_state())
        assert update["amendment_draft"] == "x"
        finished = [e for e, _ in sink.events if e.kind == "node_finished"]
        assert finished[0].payload["summary"]["keys"] == ["amendment_draft"]

    async def test_node_exception_becomes_fatal_error(self):
        ctx, sink = mk_ctx()
        wrapped = wrap_with_hooks("compliance", node_boom, ctx)
        update = await wrapped(mk_state())
        assert "fatal_error" in update
        # error text is never copied into state (it may carry secrets/PII)
        assert "exploded" not in update["fatal_error"]
        assert "RuntimeError" in update["fatal_error"]
        assert "node_failed" in [e.kind for e, _ in sink.events]

    async def test_forbidden_field_rejected(self):
        ctx, _sink = mk_ctx()
        wrapped = wrap_with_hooks("compliance", node_forbidden, ctx)
        update = await wrapped(mk_state())
        assert "fatal_error" in update


class TestInvariants:
    def test_healthy_state(self):
        state = mk_state()
        assert validate_state_invariants(state) == []

    def test_confidence_out_of_range_detected(self):
        # model_construct bypasses validation, simulating a bug upstream
        bad_field = ExtractedField.model_construct(
            name="x", value="1", confidence=1.5, source=SourceRef(page=1)
        )
        doc = ExtractedDoc.model_construct(
            doc_id="d",
            sha256="a",
            kind="commercial_invoice",
            fields=[bad_field],
            extraction_model="fast",
            low_confidence=False,
        )
        state = mk_state(extracted=[doc])
        problems = validate_state_invariants(state)
        assert problems and "confidence" in problems[0]

    def test_receipt_requires_approval(self):
        from app.graph.state import Money, Receipt

        state = mk_state(
            receipt=Receipt(
                receipt_id="r1",
                deal_id="d1",
                payout_ref="p1",
                amount=Money(minor=1, currency="USD"),
                executed_at="now",
            )
        )
        assert validate_state_invariants(state)
