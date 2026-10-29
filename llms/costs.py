"""Session-local USD accounting; unknown costs are never reported as zero."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from threading import Lock
from typing import Any
from uuid import uuid4

from llms.config import CostPolicy, Price


class BudgetExceeded(RuntimeError):
    pass


class PricingUnavailable(RuntimeError):
    pass


@dataclass
class Usage:
    # Input includes cache reads/writes. Output includes reasoning; reasoning is a subset.
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0
    cache_write_5m_tokens: int = 0
    cache_write_1h_tokens: int = 0
    reasoning_tokens: int = 0
    raw: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        values = [
            self.input_tokens,
            self.output_tokens,
            self.cached_input_tokens,
            self.cache_write_5m_tokens,
            self.cache_write_1h_tokens,
            self.reasoning_tokens,
        ]
        if any(not isinstance(x, int) or x < 0 for x in values):
            raise ValueError("Invalid provider token usage")
        if (
            sum(values[2:5]) > self.input_tokens
            or self.reasoning_tokens > self.output_tokens
        ):
            raise ValueError("Inconsistent provider token usage")


def usage_cost(usage: Usage, price: Price | None) -> Decimal | None:
    if price is None:
        return None
    ordinary_input = (
        usage.input_tokens
        - usage.cached_input_tokens
        - usage.cache_write_5m_tokens
        - usage.cache_write_1h_tokens
    )
    categories = (
        (ordinary_input, price.input_per_million),
        (usage.output_tokens, price.output_per_million),
        (usage.cached_input_tokens, price.cached_input_per_million),
        (usage.cache_write_5m_tokens, price.cache_write_5m_per_million),
        (usage.cache_write_1h_tokens, price.cache_write_1h_per_million),
    )
    if any(tokens and rate is None for tokens, rate in categories):
        return None
    return (
        sum(
            (Decimal(tokens) * (rate or Decimal(0)) for tokens, rate in categories),
            Decimal(0),
        )
        / 1_000_000
    )


@dataclass
class CostRecord:
    id: str
    provider: str
    model: str
    task_id: str | None
    estimated_cost: Decimal | None
    estimated_input_tokens: int
    estimated_output_tokens: int
    pricing: dict[str, Any] | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    status: str = "reserved"
    cost: Decimal | None = None
    usage: Usage | None = None
    response_id: str | None = None
    request_id: str | None = None
    raw_usage: dict[str, Any] | None = None
    error: str | None = None
    request_group_id: str | None = None
    attempt: int = 1
    outcome: str = "pending"
    duration_ms: int | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)


class CostTracker:
    def __init__(self, policy: CostPolicy, pricing: list[Price]):
        self.policy = policy
        self.pricing = {(p.provider, p.model): p for p in pricing}
        self.session_id = str(uuid4())
        self.records: list[CostRecord] = []
        self._lock = Lock()

    def reserve(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        task_id: str | None = None,
    ) -> CostRecord:
        price = self.pricing.get((provider, model))
        estimate = None
        if price:
            # Do not assume a cache hit, or that cache writes cost ordinary input rates.
            input_rate = max(
                p
                for p in (
                    price.input_per_million,
                    price.cached_input_per_million,
                    price.cache_write_5m_per_million,
                    price.cache_write_1h_per_million,
                )
                if p is not None
            )
            estimate = (
                Decimal(input_tokens) * input_rate
                + Decimal(output_tokens) * price.output_per_million
            ) / 1_000_000
        with self._lock:
            if self.policy.enforced:
                if estimate is None:
                    raise PricingUnavailable(
                        f"No pricing configured for {provider}/{model}; request not sent"
                    )
                if any(r.status == "unknown" for r in self.records):
                    raise BudgetExceeded(
                        "Unreconciled request usage/cost; session stopped to avoid untracked spend"
                    )
                if self.policy.task_budget is not None and not task_id:
                    raise BudgetExceeded(
                        "task_budget requires an explicit accounting task_id"
                    )
                limits = (
                    (self.policy.request_budget, Decimal(0), "request"),
                    (self.policy.session_budget, self._committed(), "session"),
                    (self.policy.task_budget, self._committed(task_id), "task"),
                )
                for limit, spent, scope in limits:
                    if limit is not None and spent + estimate > limit:
                        raise BudgetExceeded(
                            f"{scope.capitalize()} budget exceeded: ${spent} committed + ${estimate} reserved > ${limit}"
                        )
            record = CostRecord(
                str(uuid4()),
                provider,
                model,
                task_id,
                estimate,
                input_tokens,
                output_tokens,
                pricing=price.model_dump(mode="json") if price else None,
            )
            self.records.append(record)
            return record

    def _committed(self, task_id: str | None = None) -> Decimal:
        return sum(
            (
                r.cost if r.cost is not None else r.estimated_cost or Decimal(0)
                for r in self.records
                if task_id is None or r.task_id == task_id
            ),
            Decimal(0),
        )

    def reconcile(
        self,
        record: CostRecord,
        usage: Usage | None,
        model: str,
        response_id: str | None,
        error: str | None = None,
    ):
        with self._lock:
            # Model aliases often resolve to a snapshot. Prefer snapshot pricing;
            # otherwise use the explicitly configured price for the requested alias.
            price = self.pricing.get((record.provider, model)) or self.pricing.get(
                (record.provider, record.model)
            )
            record.model = model
            record.usage = usage
            record.response_id = response_id
            record.error = error
            record.pricing = price.model_dump(mode="json") if price else None
            record.cost = usage_cost(usage, price) if usage else None
            record.status = "reported" if record.cost is not None else "unknown"

    def summary(self) -> dict[str, Any]:
        with self._lock:
            return {
                "session_id": self.session_id,
                "currency": self.policy.currency,
                "requests": len(self.records),
                "input_tokens": sum(
                    r.usage.input_tokens for r in self.records if r.usage
                ),
                "output_tokens": sum(
                    r.usage.output_tokens for r in self.records if r.usage
                ),
                "known_cost": str(
                    sum(
                        (r.cost for r in self.records if r.cost is not None), Decimal(0)
                    )
                ),
                "committed_cost": str(self._committed()),
                "unknown_requests": sum(r.status == "unknown" for r in self.records),
                "session_budget": str(self.policy.session_budget)
                if self.policy.session_budget is not None
                else None,
                "tasks": {
                    task: {
                        "known_cost": str(
                            sum(
                                (
                                    r.cost
                                    for r in self.records
                                    if r.task_id == task and r.cost is not None
                                ),
                                Decimal(0),
                            )
                        ),
                        "committed_cost": str(self._committed(task)),
                        "unknown_requests": sum(
                            r.task_id == task and r.status == "unknown"
                            for r in self.records
                        ),
                    }
                    for task in sorted(
                        {r.task_id for r in self.records if r.task_id is not None}
                    )
                },
            }

    def record_json(self, record: CostRecord):
        return asdict(record) | {"summary": self.summary()}
