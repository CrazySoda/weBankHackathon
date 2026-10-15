"""Tool registry: allowlist enforcement, validation, audit, act-tool gating."""

import pytest
from app.audit.events import AuditEvent, InMemoryAuditSink
from app.harness.tools.registry import Tool, ToolError, ToolRefused, ToolRegistry
from pydantic import BaseModel


class AddIn(BaseModel):
    a: int
    b: int


class AddOut(BaseModel):
    sum: int


def add(inp: AddIn) -> AddOut:
    return AddOut(sum=inp.a + inp.b)


class BoomIn(AddIn):
    pass


def boom(_: AddIn) -> AddOut:
    raise RuntimeError("kaboom")


class DraftIn(BaseModel):
    deal_id: str = ""
    text: str


class DraftOut(BaseModel):
    text: str


def draft(inp: DraftIn) -> DraftOut:
    return DraftOut(text=inp.text.upper())


def mk_registry(**extra: Tool) -> ToolRegistry:
    sink = InMemoryAuditSink()
    reg = ToolRegistry(audit_sink=sink)
    reg.register(
        Tool(
            name="add",
            description="adds two ints",
            fn=add,
            input_model=AddIn,
            output_model=AddOut,
            side_effect="compute",
            allowed_nodes=frozenset({"compliance"}),
        )
    )
    reg.register(
        Tool(
            name="boom",
            description="raises",
            fn=boom,
            input_model=BoomIn,
            output_model=AddOut,
            side_effect="compute",
            allowed_nodes=frozenset({"compliance"}),
        )
    )
    reg.register(
        Tool(
            name="draft_amendment",
            description="drafts text",
            fn=draft,
            input_model=DraftIn,
            output_model=DraftOut,
            side_effect="draft",
            allowed_nodes=frozenset({"resolve_exception"}),
        )
    )
    for tool in extra.values():
        reg.register(tool)
    return reg


class TestAllowlist:
    def test_call_inside_allowlist(self):
        reg = mk_registry()
        out = reg.call("compliance", "add", AddIn(a=1, b=2))
        assert out.sum == 3

    def test_call_outside_allowlist_refused(self):
        reg = mk_registry()
        with pytest.raises(ToolRefused):
            reg.call("fx", "add", AddIn(a=1, b=2))
        kinds = [e.kind for e, _ in reg.audit_sink.events]
        assert "tool_refused" in kinds

    def test_unknown_tool_refused(self):
        reg = mk_registry()
        with pytest.raises(ToolError, match="unknown tool"):
            reg.call("compliance", "nope", AddIn(a=1, b=2))
        kinds = [e.kind for e, _ in reg.audit_sink.events]
        assert "tool_refused" in kinds

    def test_refusal_event_records_node_and_tool(self):
        reg = mk_registry()
        with pytest.raises(ToolRefused):
            reg.call("verify", "add", AddIn(a=1, b=2))
        refused = [e for e, _ in reg.audit_sink.events if e.kind == "tool_refused"]
        assert refused[0].payload["node"] == "verify"
        assert refused[0].payload["tool"] == "add"


class TestValidation:
    def test_input_coerced(self):
        reg = mk_registry()
        out = reg.call("compliance", "add", {"a": "1", "b": 2})  # type: ignore[arg-type]
        assert out.sum == 3

    def test_invalid_input_fails_closed(self):
        reg = mk_registry()
        with pytest.raises(ToolError, match="invalid input"):
            reg.call("compliance", "add", {"a": "x", "b": 2})  # type: ignore[arg-type]
        assert "tool_failed" in [e.kind for e, _ in reg.audit_sink.events]

    def test_tool_exception_wrapped_and_audited(self):
        reg = mk_registry()
        with pytest.raises(ToolError, match="failed") as exc:
            reg.call("compliance", "boom", BoomIn(a=1, b=2))
        assert "kaboom" not in str(exc.value)  # tool error text is not echoed
        assert "tool_failed" in [e.kind for e, _ in reg.audit_sink.events]

    def test_success_audited(self):
        reg = mk_registry()
        reg.call("compliance", "add", AddIn(a=1, b=2))
        ok = [e for e, _ in reg.audit_sink.events if e.kind == "tool_called"]
        assert ok and ok[0].payload["ok"] is True
        assert ok[0].payload["latency_ms"] >= 0


class TestActToolGating:
    def test_act_tool_must_not_be_llm_callable(self):
        class PayoutIn(BaseModel):
            deal_id: str

        class PayoutOut(BaseModel):
            ref: str

        with pytest.raises(ValueError, match="llm_callable"):
            Tool(
                name="execute_sandbox_payout",
                description="pays",
                fn=lambda i: PayoutOut(ref="x"),
                input_model=PayoutIn,
                output_model=PayoutOut,
                side_effect="act",
                allowed_nodes=frozenset({"execute"}),
                llm_callable=True,  # forbidden by rule 0.5
            )

    def test_system_tool_must_not_be_llm_callable(self):
        class E(BaseModel):
            pass

        with pytest.raises(ValueError, match="llm_callable"):
            Tool(
                name="write_audit_event",
                description="audits",
                fn=lambda i: E(),
                input_model=E,
                output_model=E,
                side_effect="system",
                allowed_nodes=frozenset({"*"}),
                llm_callable=True,
            )

    def test_tools_for_node_excludes_act_tools(self):
        class PayoutIn(BaseModel):
            deal_id: str

        class PayoutOut(BaseModel):
            ref: str

        reg = mk_registry(
            **{
                "execute_sandbox_payout": Tool(
                    name="execute_sandbox_payout",
                    description="pays",
                    fn=lambda i: PayoutOut(ref="x"),
                    input_model=PayoutIn,
                    output_model=PayoutOut,
                    side_effect="act",
                    allowed_nodes=frozenset({"execute"}),
                    llm_callable=False,
                )
            }
        )
        names = [t.name for t in reg.tools_for_node("execute", llm_only=True)]
        assert names == []
        names_all = [t.name for t in reg.tools_for_node("execute", llm_only=False)]
        assert names_all == ["execute_sandbox_payout"]


class TestAuditChainIntact:
    def test_events_form_valid_chain(self):
        reg = mk_registry()
        with pytest.raises(ToolRefused):
            reg.call("fx", "add", AddIn(a=1, b=2))
        reg.call("compliance", "add", AddIn(a=1, b=2))
        sink: InMemoryAuditSink = reg.audit_sink  # type: ignore[assignment]
        assert sink.verify_chain("default")

    def test_tamper_detected(self):
        reg = mk_registry()
        reg.call("compliance", "add", AddIn(a=1, b=2))
        sink: InMemoryAuditSink = reg.audit_sink  # type: ignore[assignment]
        # tamper: mutate an event's payload in place
        evt = sink.events[0][0]
        evt.payload["tool"] = "forged"
        assert not sink.verify_chain("default")


def test_audit_event_chain_is_deterministic():
    e = AuditEvent(kind="x", deal_id="d", payload={"a": 1}, ts="2026-01-01T00:00:00+00:00")
    h1 = e.chain("0" * 64)
    h2 = e.chain("0" * 64)
    assert h1 == h2
    assert e.chain("1" * 64) != h1
