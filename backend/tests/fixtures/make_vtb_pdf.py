"""Generate a synthetic VTB-like statement (no real data) for parser tests.

python tests/fixtures/make_vtb_pdf.py tests/fixtures/vtb_synthetic.pdf [font.ttf]
"""

import sys

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

FONTS = ["/System/Library/Fonts/Supplemental/Arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]

OPS = [
    # date, processed, amount text, incoming, outgoing, description, counterparty
    (
        "02.06.2026",
        "03.06.2026",
        "-450.00 RUB",
        "",
        "-450.00",
        "Оплата товаров и услуг. TEST MARKET 01. РОССИЯ. Testville. 111111111111.",
        "",
    ),
    ("05.06.2026", "05.06.2026", "100000.00 RUB", "100000.00", "", "Заработная плата за май", "ООО ПРИМЕР"),
    (
        "10.06.2026",
        "11.06.2026",
        "-1200.50 RUB",
        "",
        "-1200.50",
        "Оплата товаров и услуг. COFFEE PLACE. РОССИЯ. Moscow. 222222222222.",
        "",
    ),
    ("15.06.2026", "15.06.2026", "-20000.00 RUB", "", "-20000.00", "Перевод между своими счетами", "Счёт *9999"),
    ("20.06.2026", "20.06.2026", "-777.00 RUB", "", "-777.00", "Перевод по СБП. Неизвестный получатель Т.", "Тест Т."),
    (
        "30.06.2026",
        "01.07.2026",
        "-300.00 RUB",
        "",
        "-300.00",
        "Оплата товаров и услуг. TEST MARKET 01. РОССИЯ. Testville. 333333333333.",
        "",
    ),
]


def main(out: str, font: str | None = None):
    font = font or next(f for f in FONTS if __import__("os").path.exists(f))
    pdfmetrics.registerFont(TTFont("F", font))
    st = ParagraphStyle("p", fontName="F", fontSize=9)
    inc = sum(float(o[3] or 0) for o in OPS if o[1] <= "30.06.2026" or o[1][3:5] == "06")
    out_sum = -sum(float(o[4] or 0) for o in OPS if o[1][3:5] == "06")
    start = 5000.00
    end = start + inc - out_sum
    header = [
        "Выписка по счёту (синтетическая, для тестов) Банк ВТБ (ПАО)",
        "Номер счёта 40817810000000001234",
        "Период выписки 01.06.2026 - 30.06.2026",
        f"Баланс на начало периода {start:.2f} RUB",
        f"Поступления {inc:.2f} RUB",
        f"Расходные операции {out_sum:.2f} RUB",
        f"Баланс на конец периода {end:.2f} RUB",
    ]
    cell = ParagraphStyle("c", fontName="F", fontSize=7)
    data = [["Дата операции", "Дата обработки", "Сумма", "Приход", "Расход", "Описание", "Контрагент"]]
    data += [[o[0], o[1], o[2], o[3], o[4], Paragraph(o[5], cell), Paragraph(o[6], cell)] for o in OPS]
    t = Table(data, colWidths=[70, 70, 80, 60, 60, 300, 110])
    t.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("FONTNAME", (0, 0), (-1, -1), "F"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
            ]
        )
    )
    doc = SimpleDocTemplate(out, pagesize=landscape(A4))
    doc.build([Paragraph(h, st) for h in header] + [t])


if __name__ == "__main__":
    main(*sys.argv[1:])
