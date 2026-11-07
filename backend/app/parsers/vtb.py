"""VTB (retail) PDF statement parser.

Table columns: operation date | processing date | amount in operation currency |
incoming | outgoing | description | counterparty. Totals in the header are calculated
by processing date within the statement period.
"""

import re
from datetime import date, datetime
from decimal import Decimal
from typing import BinaryIO

from app.parsers.base import ParsedOp, ParsedStatement, StatementError

DATE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
BANK = "ВТБ"


def _money(s: str | None) -> Decimal:
    s = (s or "").replace("RUB", "").replace(" ", "").replace("\xa0", "").strip()
    return Decimal(s) if s else Decimal(0)


def _flat(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\n", " ")).strip()


def _d(s: str) -> date:
    return datetime.strptime(s.strip(), "%d.%m.%Y").date()


def _hdr(header: str, label: str) -> Decimal | None:
    m = re.search(label + r"\s+(-?[\d.]+)", header)
    return Decimal(m.group(1)) if m else None


def looks_like(header: str) -> bool:
    return "Период выписки" in header and ("ВТБ" in header or "Баланс на начало периода" in header)


def parse_rows(header: str, rows: list[list[str | None]]) -> ParsedStatement:
    """Pure function over extracted table rows; used by the PDF reader and tests."""
    ops: list[ParsedOp] = []
    for r in rows:
        if not r or not r[0] or not DATE.match(r[0].strip()):
            # description continued from the previous page
            if ops and r and not (r[0] or "").strip() and any(r[5:]):
                ops[-1].description = (ops[-1].description + " " + _flat(r[5] if len(r) > 5 else "")).strip()
            continue
        if len(r) < 6:
            raise StatementError(f"unexpected VTB row shape: {len(r)} columns")
        ops.append(
            ParsedOp(
                date=_d(r[0]),
                processed=_d(r[1]) if r[1] and DATE.match(r[1].strip()) else None,
                amount=_money(r[3]) + _money(r[4]),  # outgoing is already negative
                currency_amount=_flat(r[2]),
                description=_flat(r[5]),
                counterparty=_flat(r[6] if len(r) > 6 else ""),
            )
        )
    pm = re.search(r"Период выписки (\d{2}\.\d{2}\.\d{4}) - (\d{2}\.\d{2}\.\d{4})", header)
    acc = re.search(r"Номер сч[её]та (\d{20})", header)
    return ParsedStatement(
        bank=BANK,
        account_mask=acc.group(1)[-4:] if acc else None,
        period_start=_d(pm.group(1)) if pm else None,
        period_end=_d(pm.group(2)) if pm else None,
        opening_balance=_hdr(header, "Баланс на начало периода"),
        closing_balance=_hdr(header, "Баланс на конец периода"),
        stated_income=_hdr(header, "Поступления"),
        stated_expense=_hdr(header, "Расходные операции"),
        ops=ops,
    )


def parse_pdf(fp: str | BinaryIO) -> ParsedStatement:
    import pdfplumber

    with pdfplumber.open(fp) as pdf:
        header = pdf.pages[0].extract_text() or ""
        rows = [r for page in pdf.pages for table in page.extract_tables() for r in table]
    if not looks_like(header):
        raise StatementError("not a VTB statement")
    st = parse_rows(header, rows)
    if not st.ops:
        raise StatementError("no operations found")
    return st
