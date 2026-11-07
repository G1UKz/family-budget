"""Deterministic categorization: rules -> sign fixes -> pinpoint overrides -> trips.

Mirrors the original classify.py semantics so migrated history stays consistent.
Anything that ends up with type "?" (or matches no rule) goes to the review queue.
"""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.models import TxType

PREFIX = re.compile(r"^(Оплата товаров и услуг|Оплата услуг коммерческих провайдеров)\.\s*")
LONG_NUMBER = re.compile(r"\b\d{10,}\b")


@dataclass(frozen=True)
class RuleSpec:
    id: int | None
    pattern: str
    type: str
    category: str
    amount: Decimal | None = None
    weekday: int | None = None

    def compiled(self) -> re.Pattern[str]:
        return re.compile(self.pattern, re.I)


@dataclass(frozen=True)
class TripSpec:
    name: str
    start: date
    end: date
    categories: frozenset[str]


@dataclass
class Decision:
    type: str
    category: str
    note: str = ""
    rule_id: int | None = None
    decided_by: str = ""

    @property
    def needs_review(self) -> bool:
        return self.type == TxType.unknown or not self.category


def merchant_of(description: str, counterparty: str) -> str:
    """Human-readable merchant without card/terminal numbers."""
    m = counterparty or PREFIX.sub("", description)[:80]
    m = LONG_NUMBER.sub("", m)
    m = re.sub(r"\.?\s*РОССИЯ\..*$", "", m)
    return m.strip(" .") or description[:60]


class Categorizer:
    def __init__(
        self,
        rules: list[RuleSpec],
        overrides: dict[tuple[date, Decimal], tuple[str, str, str]],
        trips: list[TripSpec],
        home_regex: str,
    ):
        self.rules = [(r, r.compiled()) for r in rules]
        self.overrides = overrides
        self.trips = trips
        self.home = re.compile(home_regex)

    def decide(self, d: date, amount: Decimal, description: str, counterparty: str) -> Decision:
        text = f"{description} | {counterparty}"
        dec = Decision(TxType.unknown, "", decided_by="none")
        for spec, rx in self.rules:
            if (
                rx.search(text)
                and (spec.amount is None or abs(amount) == spec.amount)
                and (spec.weekday is None or spec.weekday == d.isoweekday())
            ):
                dec = Decision(spec.type, spec.category, rule_id=spec.id, decided_by="rule")
                break
        if dec.type == TxType.expense and amount > 0:
            dec.type = TxType.refund  # a refund reduces the expense of its category
        if dec.category == "Переводы людям" and amount > 0:
            dec.type, dec.category = TxType.income, "Переводы от людей"
        if (d, amount) in self.overrides:
            t, c, n = self.overrides[(d, amount)]
            dec = Decision(t, c, n, decided_by="override")
        if dec.type in (TxType.expense, TxType.refund) and not self.home.search(description):
            for trip in self.trips:
                if trip.start <= d <= trip.end and dec.category in trip.categories:
                    dec.note, dec.category = f"поездка {trip.name}: {dec.category}", "Поездки"
                    dec.decided_by = "trip"
                    break
        return dec
