from datetime import date
from decimal import Decimal

import pytest

from app.parsers import detect_and_parse
from app.parsers.base import StatementError
from app.parsers.vtb import parse_rows
from tests.conftest import FIXTURES

HEADER = """Номер счёта 40817810000000004321
Период выписки 01.06.2026 - 30.06.2026
Баланс на начало периода 1000.00 RUB
Поступления 500.00 RUB
Расходные операции 300.00 RUB
Баланс на конец периода 1200.00 RUB"""


def test_parse_rows_and_reconcile():
    rows = [
        ["Дата", "Обработка", "Сумма", "Приход", "Расход", "Описание", "Контрагент"],
        ["01.06.2026", "01.06.2026", "500 RUB", "500.00", "", "Зачисление", "Кто-то"],
        ["02.06.2026", "03.06.2026", "-300 RUB", "", "-300.00", "Оплата\nтоваров", ""],
        [None, None, None, None, None, "продолжение", None],
        # processed after the period end: listed, not in the bank totals
        ["30.06.2026", "01.07.2026", "-50 RUB", "", "-50.00", "Поздняя", ""],
    ]
    st = parse_rows(HEADER, rows)
    assert st.account_mask == "4321"
    assert len(st.ops) == 3
    assert st.ops[1].description == "Оплата товаров продолжение"
    assert st.parsed_income == Decimal("500.00") and st.parsed_expense == Decimal("300.00")
    assert st.reconcile()["ok"]


def test_reconcile_detects_mismatch():
    rows = [["01.06.2026", "01.06.2026", "", "400.00", "", "x", ""]]
    rec = parse_rows(HEADER, rows).reconcile()
    assert not rec["ok"] and not rec["income"]["ok"]


def test_synthetic_pdf():
    st = detect_and_parse(str(FIXTURES / "vtb_synthetic.pdf"))
    assert st.bank == "ВТБ" and st.account_mask == "1234"
    assert st.period_start == date(2026, 6, 1) and len(st.ops) == 6
    assert st.reconcile()["ok"]


def test_unknown_pdf(tmp_path):
    from reportlab.pdfgen import canvas

    p = tmp_path / "x.pdf"
    c = canvas.Canvas(str(p))
    c.drawString(100, 750, "hello")
    c.save()
    with pytest.raises(StatementError):
        detect_and_parse(str(p))
