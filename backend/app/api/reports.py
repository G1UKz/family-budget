from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.security import current_user
from app.services import reports

router = APIRouter(prefix="/api/reports", tags=["reports"], dependencies=[Depends(current_user)])


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    return reports.summary(db)


@router.get("/months")
def months(db: Session = Depends(get_db)):
    return reports.months(db)


@router.get("/categories")
def categories(month: str | None = None, db: Session = Depends(get_db)):
    return reports.categories(db, month)


@router.get("/balances")
def balances(db: Session = Depends(get_db)):
    return reports.balances(db)
