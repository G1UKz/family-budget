from datetime import date
from decimal import Decimal

from app.categorize.engine import Categorizer, RuleSpec, TripSpec, merchant_of

RULES = [
    RuleSpec(1, "SHOP", "expense", "Продукты"),
    RuleSpec(2, "GYM", "expense", "Спорт", amount=Decimal("1000"), weekday=1),
    RuleSpec(3, "СБП", "expense", "Переводы людям"),
    RuleSpec(4, ".", "?", ""),
]
TRIPS = [TripSpec("Сочи", date(2026, 7, 1), date(2026, 7, 10), frozenset({"Продукты"}))]


def cat(overrides=None):
    return Categorizer(RULES, overrides or {}, TRIPS, r"(?i)testville")


def test_first_match_wins_and_refund():
    c = cat()
    assert c.decide(date(2026, 6, 2), Decimal("-10"), "SHOP 1", "").category == "Продукты"
    d = c.decide(date(2026, 6, 2), Decimal("10"), "SHOP 1", "")
    assert (d.type, d.category) == ("refund", "Продукты")


def test_amount_and_weekday_conditions():
    c = cat()
    monday, tuesday = date(2026, 6, 1), date(2026, 6, 2)
    assert c.decide(monday, Decimal("-1000"), "GYM", "").category == "Спорт"
    assert c.decide(tuesday, Decimal("-1000"), "GYM", "").needs_review
    assert c.decide(monday, Decimal("-999"), "GYM", "").needs_review


def test_incoming_transfer_becomes_income():
    d = cat().decide(date(2026, 6, 2), Decimal("500"), "СБП от", "")
    assert (d.type, d.category) == ("income", "Переводы от людей")


def test_override_and_trip():
    c = cat({(date(2026, 6, 3), Decimal("-5")): ("capital", "Сделка", "fix")})
    d = c.decide(date(2026, 6, 3), Decimal("-5"), "SHOP", "")
    assert (d.type, d.category, d.decided_by) == ("capital", "Сделка", "override")
    away = c.decide(date(2026, 7, 2), Decimal("-5"), "SHOP Sochi", "")
    assert away.category == "Поездки" and "Продукты" in away.note
    home = c.decide(date(2026, 7, 2), Decimal("-5"), "SHOP Testville", "")
    assert home.category == "Продукты"


def test_merchant_strips_numbers():
    m = merchant_of("Оплата товаров и услуг. SHOP 12345. РОССИЯ. Testville. 999999999999.", "")
    assert m == "SHOP 12345"
