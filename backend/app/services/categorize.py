from sqlalchemy import select
from sqlalchemy.orm import Session

from app.categorize.engine import Categorizer, RuleSpec, TripSpec
from app.config import get_settings
from app.models import Account, Override, Rule, Transaction, Trip, TxStatus, TxType


def load_categorizer(db: Session) -> Categorizer:
    rules = [
        RuleSpec(r.id, r.pattern, r.type, r.category, r.amount, r.weekday)
        for r in db.scalars(select(Rule).where(Rule.enabled).order_by(Rule.priority, Rule.id))
    ]
    overrides = {(o.date, o.amount): (o.type, o.category, o.note) for o in db.scalars(select(Override))}
    trips = [
        TripSpec(t.name, t.start, t.end, frozenset(filter(None, t.categories.split(";")))) for t in db.scalars(select(Trip))
    ]
    return Categorizer(rules, overrides, trips, get_settings().home_city_regex)


def link_counter_account(db: Session, tx: Transaction) -> None:
    if tx.type not in (TxType.internal, TxType.savings):
        return
    text = f"{tx.description} {tx.counterparty}"
    for acc in db.scalars(select(Account).where(Account.mask != "", Account.id != tx.account_id)):
        if acc.mask in text:
            tx.counter_account_id = acc.id
            return


def apply(db: Session, tx: Transaction, cat: Categorizer) -> None:
    dec = cat.decide(tx.date, tx.amount, tx.description, tx.counterparty)
    tx.type, tx.category, tx.note, tx.rule_id, tx.decided_by = (
        dec.type,
        dec.category,
        dec.note,
        dec.rule_id,
        dec.decided_by,
    )
    tx.status = TxStatus.review if dec.needs_review else TxStatus.confirmed
    link_counter_account(db, tx)


def recategorize(db: Session, only_review: bool = False) -> dict[str, int]:
    """Re-run rules over automatically decided transactions (manual decisions are kept)."""
    cat = load_categorizer(db)
    q = select(Transaction).where(~Transaction.decided_by.like("user:%"), Transaction.date >= get_settings().start_date)
    if only_review:
        q = q.where(Transaction.status == TxStatus.review)
    changed = total = 0
    for tx in db.scalars(q):
        before = (tx.type, tx.category, tx.status)
        apply(db, tx, cat)
        total += 1
        changed += before != (tx.type, tx.category, tx.status)
    db.commit()
    return {"checked": total, "changed": changed}
