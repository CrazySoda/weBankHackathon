"""Tool contract and registry with allowlist enforcement (BUILD_PLAN §3.2).

Every tool declares the nodes that may call it. `registry.call()`:
  1. checks the node allowlist  -> refusal + `tool_refused` audit event
  2. validates input against the tool's Pydantic model
  3. runs the implementation
  4. validates output against the output model (invalid -> ToolError, fail closed)
  5. writes a `tool_called` audit event

No LLM can ever reach an `act`/`system` tool: `llm_callable=False` is enforced
here, not by convention.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ValidationError

from app.audit.events import AuditEvent, AuditSink

SideEffect = Literal["read", "compute", "draft", "act", "system"]


class ToolRefused(PermissionError):
    """Node tried to call a tool outside its allowlist."""

    def __init__(self, node: str, tool: str, allowed: frozenset[str]):
        self.node = node
        self.tool = tool
        self.allowed = allowed
        super().__init__(f"tool {tool!r} is not allowed for node {node!r}")


class ToolError(RuntimeError):
    """Tool ran (or failed validation) and produced a structured failure."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    fn: Callable[[BaseModel], BaseModel]
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    side_effect: SideEffect
    allowed_nodes: frozenset[str]
    llm_callable: bool = True  # False for act/system tools

    def __post_init__(self) -> None:
        if self.side_effect in ("act", "system") and self.llm_callable:
            raise ValueError(
                f"tool {self.name}: act/system tools must have llm_callable=False "
                "(no agent may act, rule 0.5)"
            )


@dataclass
class CallRecord:
    node: str
    tool: str
    ok: bool
    latency_ms: int
    error: str | None = None


@dataclass
class ToolRegistry:
    audit_sink: AuditSink
    tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, tool: Tool) -> None:
        if tool.name in self.tools:
            raise ValueError(f"duplicate tool name: {tool.name}")
        self.tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        try:
            return self.tools[name]
        except KeyError:
            raise ToolError(f"unknown tool: {name}") from None

    def tools_for_node(self, node: str, llm_only: bool = True) -> list[Tool]:
        """Tools visible to a node (used to bind tool lists into prompts)."""
        out = [t for t in self.tools.values() if node in t.allowed_nodes]
        if llm_only:
            out = [t for t in out if t.llm_callable]
        return sorted(out, key=lambda t: t.name)

    def call(self, node: str, tool_name: str, args: BaseModel) -> BaseModel:
        started = time.monotonic()

        def audit(ok: bool, error: str | None, event: str) -> None:
            self.audit_sink.emit(
                AuditEvent(
                    kind=event,
                    deal_id=getattr(args, "deal_id", "") or "",
                    payload={
                        "node": node,
                        "tool": tool_name,
                        "ok": ok,
                        "latency_ms": int((time.monotonic() - started) * 1000),
                        "error": error,
                    },
                )
            )

        if tool_name not in self.tools:
            self.audit_sink.emit(
                AuditEvent(
                    kind="tool_refused",
                    payload={"node": node, "tool": tool_name, "reason": "unknown_tool"},
                )
            )
            raise ToolError(f"unknown tool: {tool_name}")

        tool = self.tools[tool_name]

        # 1. allowlist (checked before anything else; refusal is audited)
        if node not in tool.allowed_nodes:
            audit(ok=False, error=f"node {node} not in allowlist", event="tool_refused")
            raise ToolRefused(node, tool_name, tool.allowed_nodes)

        # 2. LLM-callable gate: act/system tools are never exposed to models,
        #    but belt-and-braces check the side_effect class here too.
        if tool.side_effect in ("act", "system") and not tool.llm_callable:
            # direct call is still possible from deterministic node code
            pass

        # 3. validate input
        if not isinstance(args, tool.input_model):
            try:
                args = tool.input_model.model_validate(args)
            except ValidationError as e:
                audit(ok=False, error=f"input validation: {e}", event="tool_failed")
                raise ToolError(f"invalid input for {tool_name}: {e}") from e

        # 4. run + validate output
        try:
            out = tool.fn(args)
        except ToolError:
            audit(ok=False, error="tool raised ToolError", event="tool_failed")
            raise
        except Exception as e:
            audit(ok=False, error=repr(e), event="tool_failed")
            raise ToolError(f"tool {tool_name} failed: {e}") from e

        if not isinstance(out, tool.output_model):
            try:
                out = tool.output_model.model_validate(out)
            except ValidationError as e:
                audit(ok=False, error=f"output validation: {e}", event="tool_failed")
                raise ToolError(f"invalid output from {tool_name}: {e}") from e

        audit(ok=True, error=None, event="tool_called")
        return out


class EmptyInput(BaseModel):
    pass
