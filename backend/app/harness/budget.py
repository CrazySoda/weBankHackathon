"""Step/token/cost budgets and the kill switch (rule 0.6: fail closed).

Budgets are enforced by the node hooks, not by nodes. Each running deal owns a
`DealBudget`; the `before` hook calls `check_step()` and raises `BudgetExceeded`
when any limit trips. Cost/token usage is fed back by the LLM wrapper.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel


class BudgetExceeded(RuntimeError):
    def __init__(self, deal_id: str, reason: str):
        self.deal_id = deal_id
        self.reason = reason
        super().__init__(f"budget exceeded for {deal_id}: {reason}")


@dataclass
class DealBudget:
    deal_id: str
    max_steps: int
    max_tokens: int
    max_cost_minor: int  # USD minor units
    steps: int = 0
    tokens: int = 0
    cost_minor: int = 0
    killed: bool = False
    kill_reason: str = ""

    def check_step(self) -> None:
        """Raise BudgetExceeded if any limit is tripped. Called before each node."""
        if self.killed:
            raise BudgetExceeded(self.deal_id, f"kill switch: {self.kill_reason}")
        if self.steps >= self.max_steps:
            raise BudgetExceeded(self.deal_id, f"steps {self.steps} >= {self.max_steps}")
        if self.tokens > self.max_tokens:
            raise BudgetExceeded(self.deal_id, f"tokens {self.tokens} > {self.max_tokens}")
        if self.cost_minor > self.max_cost_minor:
            raise BudgetExceeded(
                self.deal_id, f"cost {self.cost_minor} > {self.max_cost_minor} minor USD"
            )

    def record_step(self) -> None:
        self.steps += 1

    def record_usage(self, prompt_tokens: int, completion_tokens: int, cost_minor: int) -> None:
        self.tokens += prompt_tokens + completion_tokens
        self.cost_minor += cost_minor

    def kill(self, reason: str) -> None:
        self.killed = True
        self.kill_reason = reason


class BudgetStatus(BaseModel):
    steps: int
    tokens: int
    cost_minor: int
    max_steps: int
    max_tokens: int
    max_cost_minor: int
    state: Literal["ok", "exceeded", "killed"]
