import pyotp
from fastapi.testclient import TestClient

from app.categorize.llm import Proposal
from app.main import create_app
from tests.conftest import FIXTURES, SECRET


def upload(client):
    with open(FIXTURES / "vtb_synthetic.pdf", "rb") as f:
        return client.post("/api/imports", files={"file": ("st.pdf", f, "application/pdf")})


def test_auth_required_and_totp():
    c = TestClient(create_app())
    assert c.get("/api/reports/summary").status_code == 401
    bad = c.post("/api/auth/login", json={"username": "ivan", "password": "pw", "code": "000000"})
    assert bad.status_code == 401
    ok = c.post("/api/auth/login", json={"username": "ivan", "password": "pw", "code": pyotp.TOTP(SECRET).now()})
    assert ok.status_code == 200
    assert c.get("/api/auth/me").json()["username"] == "ivan"


def test_import_reconciles_and_dedupes(client):
    r = upload(client)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reconciled"] and body["ops_new"] == 6
    assert upload(client).status_code == 409
    txs = client.get("/api/transactions").json()
    assert txs["total"] == 6
    cats = {t["description"][:30]: t["category"] for t in txs["items"]}
    assert "Продукты" in cats.values() and "Зарплата" in cats.values()


def test_review_queue_with_ai_suggestion_and_rule(client, monkeypatch):
    upload(client)
    queue = client.get("/api/review").json()
    assert len(queue) == 1 and "СБП" in queue[0]["tx"]["description"]
    assert client.post("/api/review/suggest").status_code == 503  # no API key configured

    class Fake:
        def suggest(self, tx, categories, examples):
            assert ("Переводы людям", "expense") in categories
            return Proposal(
                "expense", "Переводы людям", 0.7, "Перевод частному лицу по СБП", r"Неизвестный получатель", "fake"
            )

    monkeypatch.setattr("app.api.tx.get_suggester", lambda: Fake())
    assert client.post("/api/review/suggest").json() == {"created": 1}
    item = client.get("/api/review").json()[0]
    s = item["suggestion"]
    assert s["category"] == "Переводы людям"
    # nothing is applied until a human accepts
    assert client.get("/api/transactions?status=review").json()["total"] == 1
    r = client.post(f"/api/review/{s['id']}/accept?make_rule=true")
    assert r.status_code == 200 and r.json()["status"] == "confirmed"
    assert client.get("/api/review").json() == []
    rules = client.get("/api/rules").json()
    assert any(x["pattern"] == "Неизвестный получатель" and x["origin"] == "review" for x in rules)


def test_manual_decision_and_reports(client):
    upload(client)
    tid = client.get("/api/review").json()[0]["tx"]["id"]
    r = client.put(f"/api/transactions/{tid}", json={"type": "expense", "category": "Переводы людям"})
    assert r.status_code == 200
    assert client.put(f"/api/transactions/{tid}", json={"type": "expense", "category": "Нет такой"}).status_code == 422
    months = client.get("/api/reports/months").json()
    june = next(m for m in months if m["month"] == "2026-06")
    assert june["income"] == "100000.00"
    cats = client.get("/api/reports/categories?month=2026-06").json()
    assert {c["category"]: c["amount"] for c in cats}["Кафе и рестораны"] == "1200.50"
    bal = client.get("/api/reports/balances").json()
    assert bal[0]["start"] == "5000.00"
    # manual decisions survive re-applying rules
    client.post("/api/rules/apply")
    assert client.get("/api/transactions?status=review").json()["total"] == 0


def test_bad_regex_rejected(client):
    r = client.post("/api/rules", json={"pattern": "(", "type": "expense", "category": "Продукты"})
    assert r.status_code == 422


def test_health():
    c = TestClient(create_app())
    assert c.get("/healthz").json() == {"ok": True}
    assert c.get("/readyz").status_code == 200
    assert c.get("/metrics").status_code == 200
    assert c.get("/metrics", headers={"X-Forwarded-For": "203.0.113.5"}).status_code == 404


def test_api_docs_only_in_dev(monkeypatch):
    from app.config import get_settings

    assert TestClient(create_app()).get("/api/openapi.json").status_code == 200
    monkeypatch.setenv("BUDGET_ENV", "prod")
    monkeypatch.setenv("BUDGET_SECRET_KEY", "x" * 40)
    get_settings.cache_clear()
    try:
        c = TestClient(create_app())
        assert c.get("/api/openapi.json").status_code != 200 or "openapi" not in c.get("/api/openapi.json").text
        assert "swagger" not in c.get("/api/docs").text.lower()
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
