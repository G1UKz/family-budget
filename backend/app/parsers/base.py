from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass
class ParsedOp:
    date: date
    processed: date | None
    amount: Decimal  # positive = incoming, negative = outgoing
    description: str
    counterparty: str = ""
    currency_amount: str = ""


@dataclass
class ParsedStatement:
    bank: str
    account_mask: str | None
    period_start: date | None
    period_end: date | None
    opening_balance: Decimal | None
    closing_balance: Decimal | None
    stated_income: Decimal | None
    stated_expense: Decimal | None
    ops: list[ParsedOp] = field(default_factory=list)

    def counted(self) -> list[ParsedOp]:
        """Operations included in the bank's totals: processed within the statement period.

        Operations processed after the period end are listed in the statement but belong
        to the next period's totals.
        """
        end = self.period_end
        return [o for o in self.ops if end is None or o.processed is None or o.processed <= end]

    @property
    def parsed_income(self) -> Decimal:
        return sum((o.amount for o in self.counted() if o.amount > 0), Decimal(0))

    @property
    def parsed_expense(self) -> Decimal:
        return -sum((o.amount for o in self.counted() if o.amount < 0), Decimal(0))

    def reconcile(self) -> dict:
        checks = {
            "income": (self.parsed_income, self.stated_income),
            "expense": (self.parsed_expense, self.stated_expense),
        }
        if self.opening_balance is not None:
            checks["closing_balance"] = (
                self.opening_balance + self.parsed_income - self.parsed_expense,
                self.closing_balance,
            )
        result = {
            k: {"parsed": str(p), "stated": None if s is None else str(s), "ok": s is not None and p == s}
            for k, (p, s) in checks.items()
        }
        result["ok"] = all(v["ok"] for v in result.values() if isinstance(v, dict))
        return result


class StatementError(ValueError):
    pass
