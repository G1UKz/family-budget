import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import AccountIn, AccountOut, CategoryIn, CategoryOut, RuleIn, RuleOut
from app.db import get_db
from app.models import Account, Category, Rule
from app.security import current_user
from app.services.categorize import recategorize

router = APIRouter(prefix="/api", tags=["reference"], dependencies=[Depends(current_user)])


def _get(db: Session, model, oid: int):
    obj = db.get(model, oid)
    if not obj:
        raise HTTPException(404)
    return obj


@router.get("/accounts", response_model=list[AccountOut])
def accounts(db: Session = Depends(get_db)):
    return db.scalars(select(Account).order_by(Account.id)).all()


@router.post("/accounts", response_model=AccountOut)
def create_account(body: AccountIn, db: Session = Depends(get_db)):
    a = Account(**body.model_dump())
    db.add(a)
    db.commit()
    return a


@router.put("/accounts/{aid}", response_model=AccountOut)
def update_account(aid: int, body: AccountIn, db: Session = Depends(get_db)):
    a = _get(db, Account, aid)
    for k, v in body.model_dump().items():
        setattr(a, k, v)
    db.commit()
    return a


@router.get("/categories", response_model=list[CategoryOut])
def categories(db: Session = Depends(get_db)):
    return db.scalars(select(Category).order_by(Category.type, Category.name)).all()


@router.post("/categories", response_model=CategoryOut)
def create_category(body: CategoryIn, db: Session = Depends(get_db)):
    c = Category(**body.model_dump())
    db.add(c)
    db.commit()
    return c


def _validate(body: RuleIn) -> None:
    try:
        re.compile(body.pattern)
    except re.error as e:
        raise HTTPException(422, f"bad regex: {e}") from e


@router.get("/rules", response_model=list[RuleOut])
def rules(db: Session = Depends(get_db)):
    return db.scalars(select(Rule).order_by(Rule.priority, Rule.id)).all()


@router.post("/rules", response_model=RuleOut)
def create_rule(body: RuleIn, db: Session = Depends(get_db)):
    _validate(body)
    r = Rule(**body.model_dump(), origin="manual")
    db.add(r)
    db.commit()
    return r


@router.put("/rules/{rid}", response_model=RuleOut)
def update_rule(rid: int, body: RuleIn, db: Session = Depends(get_db)):
    _validate(body)
    r = _get(db, Rule, rid)
    for k, v in body.model_dump().items():
        setattr(r, k, v)
    db.commit()
    return r


@router.delete("/rules/{rid}")
def delete_rule(rid: int, db: Session = Depends(get_db)):
    db.delete(_get(db, Rule, rid))
    db.commit()
    return {"ok": True}


@router.post("/rules/apply")
def apply_rules(only_review: bool = False, db: Session = Depends(get_db)):
    """Re-run rules over automatically categorized operations (manual decisions are kept)."""
    return recategorize(db, only_review=only_review)
