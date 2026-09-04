"""Indicative token pricing for the cost column of the comparison table.

These are **placeholder list prices** for the synthetic PoC run. Replace the
``candidate`` keys and per-MTok values with the real provider/model prices
(and confirm current pricing) before treating any cost figure as decision-grade.
Costs are USD per 1,000,000 tokens.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from auto_scoring.domain.ai_provider import TokenUsage


@dataclass(frozen=True)
class Price:
    """USD per 1,000,000 tokens."""

    input_per_mtok_usd: float
    output_per_mtok_usd: float


# Placeholder — NOT real vendor prices. Keyed by the synthetic candidate id.
PRICES: dict[str, Price] = {
    "synthetic-a": Price(input_per_mtok_usd=1.25, output_per_mtok_usd=5.00),
    "synthetic-b": Price(input_per_mtok_usd=3.00, output_per_mtok_usd=15.00),
}


def estimate_cost_usd(usages: Iterable[TokenUsage], price: Price) -> float:
    """Total USD for the given token usages at ``price``."""
    total = 0.0
    for usage in usages:
        total += usage.input_tokens / 1_000_000 * price.input_per_mtok_usd
        total += usage.output_tokens / 1_000_000 * price.output_per_mtok_usd
    return total
