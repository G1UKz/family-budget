"""Human decision on a transaction (web UI and CLI share this)."""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category, Rule, Suggestion, Transaction, TxStatus
from app.services.categorize import link_counter_account


class DecisionError(ValueError):
    pass


def decide(
    db: Session,
    tx: Transaction,
    type: str,
    category: str,
    who: str,
    note: str | None = None,
    make_rule: bool = False,
    rule_pattern: str | None = None,
) -> None:
    valid = {c.name for c in db.scalars(select(Category))}
    if type != "?" and category not in valid:
        raise DecisionError(f"unknown category {category!r}")
    pattern = None
    if make_rule:
        pattern = rule_pattern or re.escape(tx.merchant or tx.description[:40])
        try:
            re.compile(pattern)
        except re.error as e:
            raise DecisionError(f"bad regex: {e}") from e
    tx.type, tx.category = type, category
    if note is not None:
        tx.note = note
    tx.status = TxStatus.review if type == "?" else TxStatus.confirmed
    tx.decided_by = who
    link_counter_account(db, tx)
    if pattern:
        # new rules go before the generic catch-alls
        db.add(
            Rule(
                priority=100,
                pattern=pattern,
                type=type,
                category=category,
                origin="review",
                note=f"из разбора операции {tx.date}",
            )
        )
    for s in db.scalars(select(Suggestion).where(Suggestion.transaction_id == tx.id, Suggestion.status == "pending")):
        s.status = "accepted" if (s.type, s.category) == (type, category) else "rejected"
