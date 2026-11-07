from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.schemas import ImportOut, ReviewItem, SuggestionOut, TxDecision, TxOut, TxPage
from app.config import get_settings
from app.db import get_db
from app.models import Import, Suggestion, Transaction, TxStatus, User
from app.parsers.base import StatementError
from app.security import current_user
from app.services import importer
from app.services.decide import DecisionError
from app.services.decide import decide as decide_tx
from app.services.suggest import get_suggester, suggest_pending

router = APIRouter(prefix="/api", tags=["transactions"])
MAX_UPLOAD = 20 * 1024 * 1024


@router.get("/transactions", response_model=TxPage)
def transactions(
    month: str | None = None,
    category: str | None = None,
    type: str | None = None,
    q: str | None = None,
    account_id: int | None = None,
    status: str | None = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
):
    s = select(Transaction).where(Transaction.date >= get_settings().start_date)
    if month:
        y, m = map(int, month.split("-"))
        s = s.where(func.extract("year", Transaction.date) == y, func.extract("month", Transaction.date) == m)
    if category:
        s = s.where(Transaction.category == category)
    if type:
        s = s.where(Transaction.type.in_(type.split(",")))
    if account_id:
        s = s.where(Transaction.account_id == account_id)
    if status:
        s = s.where(Transaction.status == status)
    if q:
        like = f"%{q}%"
        s = s.where(
            or_(
                Transaction.description.ilike(like),
                Transaction.counterparty.ilike(like),
                Transaction.category.ilike(like),
                Transaction.note.ilike(like),
            )
        )
    total = db.scalar(select(func.count()).select_from(s.subquery()))
    items = db.scalars(s.order_by(Transaction.date.desc(), Transaction.id.desc()).limit(limit).offset(offset)).all()
    return TxPage(total=total or 0, items=items)


def _decide(db: Session, tx: Transaction, body: TxDecision, user: User) -> None:
    try:
        decide_tx(
            db,
            tx,
            body.type,
            body.category,
            f"user:{user.username}",
            note=body.note,
            make_rule=body.make_rule,
            rule_pattern=body.rule_pattern,
        )
    except DecisionError as e:
        raise HTTPException(422, str(e)) from e


@router.put("/transactions/{tid}", response_model=TxOut)
def decide(tid: int, body: TxDecision, db: Session = Depends(get_db), user: User = Depends(current_user)):
    tx = db.get(Transaction, tid)
    if not tx:
        raise HTTPException(404)
    _decide(db, tx, body, user)
    db.commit()
    return tx


@router.get("/review", response_model=list[ReviewItem])
def review(db: Session = Depends(get_db), _: User = Depends(current_user)):
    txs = db.scalars(
        select(Transaction)
        .where(Transaction.status == TxStatus.review, Transaction.date >= get_settings().start_date)
        .order_by(Transaction.date.desc())
    ).all()
    sug = {
        s.transaction_id: s
        for s in db.scalars(
            select(Suggestion)
            .where(Suggestion.transaction_id.in_([t.id for t in txs]), Suggestion.status == "pending")
            .order_by(Suggestion.id)
        )
    }
    return [
        ReviewItem(tx=TxOut.model_validate(t), suggestion=SuggestionOut.model_validate(sug[t.id]) if t.id in sug else None)
        for t in txs
    ]


@router.post("/review/suggest")
def run_suggestions(limit: int = Query(20, le=100), db: Session = Depends(get_db), _: User = Depends(current_user)):
    s = get_suggester()
    if s is None:
        raise HTTPException(503, "AI is not configured (BUDGET_ANTHROPIC_API_KEY)")
    return {"created": suggest_pending(db, s, limit)}


@router.post("/review/{sid}/accept", response_model=TxOut)
def accept(sid: int, make_rule: bool = False, db: Session = Depends(get_db), user: User = Depends(current_user)):
    s = db.get(Suggestion, sid)
    if not s or s.status != "pending":
        raise HTTPException(404)
    tx = db.get(Transaction, s.transaction_id)
    _decide(
        db, tx, TxDecision(type=s.type, category=s.category, make_rule=make_rule, rule_pattern=s.rule_pattern or None), user
    )
    tx.note = (tx.note + " " if tx.note else "") + "AI: " + s.explanation
    s.status = "accepted"
    db.commit()
    return tx


@router.post("/review/{sid}/reject")
def reject(sid: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    s = db.get(Suggestion, sid)
    if not s:
        raise HTTPException(404)
    s.status = "rejected"
    db.commit()
    return {"ok": True}


@router.get("/imports", response_model=list[ImportOut])
def imports(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return db.scalars(select(Import).order_by(Import.id.desc())).all()


@router.post("/imports", response_model=ImportOut)
async def upload(file: UploadFile, db: Session = Depends(get_db), user: User = Depends(current_user)):
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "file too large")
    if not data.startswith(b"%PDF"):
        raise HTTPException(415, "only PDF statements are supported")
    try:
        return importer.import_statement(db, data, file.filename or "statement.pdf", user.username)
    except importer.DuplicateImport as e:
        raise HTTPException(409, "this file was already imported") from e
    except StatementError as e:
        raise HTTPException(422, str(e)) from e
