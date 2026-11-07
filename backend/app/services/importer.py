import hashlib
import io
from collections import Counter
from typing import BinaryIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.categorize.engine import merchant_of
from app.config import get_settings
from app.models import Account, AccountKind, Import, Transaction
from app.parsers import detect_and_parse
from app.parsers.base import ParsedStatement
from app.services import categorize


class DuplicateImport(Exception):
    pass


def fingerprint(account_id: int, op, occurrence: int) -> str:
    raw = "|".join(map(str, (account_id, op.date, op.processed, op.amount, op.description, op.counterparty, occurrence)))
    return hashlib.sha256(raw.encode()).hexdigest()


def resolve_account(db: Session, st: ParsedStatement) -> Account:
    acc = db.scalar(select(Account).where(Account.mask == (st.account_mask or "")))
    if acc:
        return acc
    acc = Account(
        name=f"{st.bank} …{st.account_mask or '????'}", bank=st.bank, mask=st.account_mask or "", kind=AccountKind.checking
    )
    db.add(acc)
    db.flush()
    return acc


def import_statement(db: Session, data: bytes, filename: str, user: str = "") -> Import:
    sha = hashlib.sha256(data).hexdigest()
    if db.scalar(select(Import).where(Import.sha256 == sha)):
        raise DuplicateImport(filename)
    st = detect_and_parse(io.BytesIO(data))
    return store_statement(db, st, filename, sha, user)


def import_file(db: Session, fp: BinaryIO, filename: str, user: str = "") -> Import:
    return import_statement(db, fp.read(), filename, user)


def store_statement(db: Session, st: ParsedStatement, filename: str, sha: str, user: str = "") -> Import:
    acc = resolve_account(db, st)
    rec = st.reconcile()
    imp = Import(
        filename=filename,
        sha256=sha,
        bank=st.bank,
        account_id=acc.id,
        period_start=st.period_start,
        period_end=st.period_end,
        opening_balance=st.opening_balance,
        closing_balance=st.closing_balance,
        stated_income=st.stated_income,
        stated_expense=st.stated_expense,
        parsed_income=st.parsed_income,
        parsed_expense=st.parsed_expense,
        reconciled=rec["ok"],
        ops_total=len(st.ops),
        uploaded_by=user,
    )
    db.add(imp)
    db.flush()
    cat = categorize.load_categorizer(db)
    start = get_settings().start_date
    seen: Counter[tuple] = Counter()
    existing = set(db.scalars(select(Transaction.fingerprint).where(Transaction.account_id == acc.id)))
    new = 0
    for op in st.ops:
        key = (op.date, op.processed, op.amount, op.description, op.counterparty)
        seen[key] += 1
        fp = fingerprint(acc.id, op, seen[key])
        if fp in existing:
            continue  # overlapping statements: already imported
        tx = Transaction(
            fingerprint=fp,
            account_id=acc.id,
            import_id=imp.id,
            date=op.date,
            processed=op.processed,
            amount=op.amount,
            description=op.description,
            counterparty=op.counterparty,
            merchant=merchant_of(op.description, op.counterparty),
        )
        if op.date >= start:
            categorize.apply(db, tx, cat)
        else:
            # kept for balance reconciliation, excluded from the budget by date
            tx.status, tx.decided_by, tx.note = "confirmed", "before-start", "до начала учёта"
        db.add(tx)
        new += 1
    imp.ops_new = new
    db.commit()
    return imp
