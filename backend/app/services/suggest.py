import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.categorize.llm import AnthropicSuggester, Suggester, TxView
from app.config import get_settings
from app.models import Category, Suggestion, Transaction, TxStatus


def get_suggester() -> Suggester | None:
    s = get_settings()
    return AnthropicSuggester(s.anthropic_api_key, s.llm_model, s.llm_effort) if s.anthropic_api_key else None


def _view(t: Transaction) -> TxView:
    return TxView(str(t.date), str(t.amount), t.description, t.counterparty)


def examples_for(db: Session, tx: Transaction, limit: int = 8) -> list[tuple[TxView, str, str]]:
    words = [w for w in re.findall(r"[\wА-Яа-я]{4,}", tx.merchant or tx.description)][:2]
    q = select(Transaction).where(Transaction.status == TxStatus.confirmed, Transaction.category != "")
    rows: list[Transaction] = []
    for w in words:
        rows += db.scalars(q.where(Transaction.description.ilike(f"%{w}%")).limit(limit)).all()
    if len(rows) < 3:
        rows += db.scalars(
            q.where((Transaction.amount < 0) == (tx.amount < 0)).order_by(Transaction.date.desc()).limit(limit)
        ).all()
    seen, out = set(), []
    for r in rows:
        if r.id not in seen and r.id != tx.id:
            seen.add(r.id)
            out.append((_view(r), r.type, r.category))
    return out[:limit]


def suggest_pending(db: Session, suggester: Suggester, limit: int = 20) -> int:
    """Create suggestions for review transactions that have none yet."""
    cats = [(c.name, c.type) for c in db.scalars(select(Category).order_by(Category.name))]
    has = select(Suggestion.transaction_id)
    txs = db.scalars(
        select(Transaction)
        .where(
            Transaction.status == TxStatus.review, Transaction.date >= get_settings().start_date, Transaction.id.not_in(has)
        )
        .order_by(Transaction.date.desc())
        .limit(limit)
    ).all()
    made = 0
    for tx in txs:
        p = suggester.suggest(_view(tx), cats, examples_for(db, tx))
        if p is None:
            continue
        pattern = p.rule_pattern
        try:
            if pattern:
                re.compile(pattern)
        except re.error:
            pattern = ""
        db.add(
            Suggestion(
                transaction_id=tx.id,
                type=p.type,
                category=p.category,
                confidence=p.confidence,
                explanation=p.explanation,
                rule_pattern=pattern,
                model=p.model,
            )
        )
        made += 1
    db.commit()
    return made
