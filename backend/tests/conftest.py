import os
import tempfile
from pathlib import Path

_db = Path(tempfile.mkdtemp()) / "test.db"
os.environ["BUDGET_DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_db}")
os.environ["BUDGET_SECRET_KEY"] = "test"
os.environ.pop("BUDGET_ANTHROPIC_API_KEY", None)

import pyotp  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, get_engine, session_factory  # noqa: E402
from app.models import Category, Rule, User  # noqa: E402
from app.security import hash_password  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
SECRET = pyotp.random_base32()


@pytest.fixture(autouse=True)
def db():
    eng = get_engine()
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    with session_factory()() as s:
        s.add(User(username="ivan", display_name="Иван", password_hash=hash_password("pw"), totp_secret=SECRET))
        for name, typ in [
            ("Продукты", "expense"),
            ("Кафе и рестораны", "expense"),
            ("Поездки", "expense"),
            ("Зарплата", "income"),
            ("Между своими счетами", "internal"),
            ("Переводы людям", "expense"),
            ("Переводы от людей", "income"),
        ]:
            s.add(Category(name=name, type=typ))
        rules = [
            ("TEST MARKET", "expense", "Продукты"),
            ("COFFEE", "expense", "Кафе и рестораны"),
            ("Заработная плата", "income", "Зарплата"),
            ("между своими", "internal", "Между своими счетами"),
            (".", "?", ""),
        ]
        for i, (p, t, c) in enumerate(rules):
            s.add(Rule(priority=1000 + i, pattern=p, type=t, category=c))
        s.commit()
        yield s


@pytest.fixture
def client():
    from app.main import create_app

    c = TestClient(create_app())
    r = c.post("/api/auth/login", json={"username": "ivan", "password": "pw", "code": pyotp.TOTP(SECRET).now()})
    assert r.status_code == 200, r.text
    return c
