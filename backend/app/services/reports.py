"""Budget reports. Budget is by operation date from settings.start_date; balances by processing date."""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Account, Import, Transaction, TxType

WIFE = "Переводы жене"
Z = Decimal(0)


def _month(d: date) -> str:
    return d.strftime("%Y-%m")


def budget_ops(db: Session):
    return db.scalars(
        select(Transaction)
        .where(Transaction.date >= get_settings().start_date)
        .order_by(Transaction.date.desc(), Transaction.id.desc())
    )


def months(db: Session) -> list[dict]:
    """Per-month flows. Signs: income/expense/savings/wife are positive amounts of money moved."""
    by: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for t in budget_ops(db):
        o, a = by[_month(t.date)], t.amount
        if t.type == TxType.capital:
            o["capital"] += a
        elif t.type == TxType.internal and t.category == WIFE:
            o["wife"] -= a
        elif t.type == TxType.internal:
            o["other"] += a
        elif t.type == TxType.income:
            o["income"] += a
        elif t.type == TxType.savings:
            o["savings"] -= a
            o["sav:" + t.category] -= a
        elif t.type in (TxType.expense, TxType.refund):
            o["expense"] -= a
        else:
            o["unknown"] -= a
    out = []
    for m in sorted(by):
        o = by[m]
        row = {
            "month": m,
            **{k: str(o.get(k, Z)) for k in ("income", "expense", "savings", "wife", "capital", "other", "unknown")},
        }
        row["net"] = str(o["income"] - o["expense"])
        row["savings_by_account"] = {k[4:]: str(v) for k, v in o.items() if k.startswith("sav:")}
        out.append(row)
    return out


def categories(db: Session, month: str | None = None) -> list[dict]:
    agg: dict[str, Decimal] = defaultdict(Decimal)
    cnt: dict[str, int] = defaultdict(int)
    for t in budget_ops(db):
        if t.type in (TxType.expense, TxType.refund) and (month is None or _month(t.date) == month):
            agg[t.category] -= t.amount
            cnt[t.category] += 1
    return sorted(
        ({"category": c, "amount": str(v), "count": cnt[c]} for c, v in agg.items()), key=lambda r: -Decimal(r["amount"])
    )


def balances(db: Session) -> list[dict]:
    """Reconciliation per month for accounts in the balance.

    start + income - expense - savings - wife + capital + other + shift = end, where
    ``end`` is computed from statement opening balance and processed operations, and
    ``shift`` covers operations whose operation date and processing date fall in
    different months (or before the budget start).
    """
    accs = {a.id for a in db.scalars(select(Account).where(Account.in_balance))}
    if not accs:
        return []
    # earliest statement per account gives the opening balance
    opening: dict[int, tuple[date, Decimal]] = {}
    for imp in db.scalars(select(Import).order_by(Import.period_start)):
        if imp.account_id in accs and imp.opening_balance is not None and imp.account_id not in opening:
            opening[imp.account_id] = (imp.period_start, imp.opening_balance)
    flows: dict[str, Decimal] = defaultdict(Decimal)
    for t in db.scalars(select(Transaction).where(Transaction.account_id.in_(opening))):
        start_acc = opening[t.account_id][0]
        p = t.processed or t.date
        if p >= start_acc:
            flows[_month(p)] += t.amount
    run = sum((v for _, v in opening.values()), Z)
    mrows = {r["month"]: r for r in months(db)}
    out = []
    for m in sorted(mrows):
        r = mrows[m]
        end = run + flows.get(m, Z)
        f = (
            Decimal(r["income"])
            - Decimal(r["expense"])
            - Decimal(r["savings"])
            - Decimal(r["wife"])
            + Decimal(r["capital"])
            + Decimal(r["other"])
            - Decimal(r["unknown"])
        )
        out.append(
            {
                "month": m,
                "start": str(run),
                "income": r["income"],
                "expense": r["expense"],
                "savings": r["savings"],
                "wife": r["wife"],
                "capital": r["capital"],
                "other": r["other"],
                "unknown": r["unknown"],
                "shift": str(end - run - f),
                "end": str(end),
            }
        )
        run = end
    return out


def summary(db: Session) -> dict:
    ms = months(db)
    from app.models import TxStatus

    review = (
        db.query(Transaction)
        .filter(Transaction.status == TxStatus.review, Transaction.date >= get_settings().start_date)
        .count()
    )
    return {
        "last": ms[-1] if ms else None,
        "prev": ms[-2] if len(ms) > 1 else None,
        "review_count": review,
        "start_date": str(get_settings().start_date),
    }
