import json

from app import cli
from tests.conftest import FIXTURES


def _run(capsys, *argv):
    cli.main(list(argv))
    return capsys.readouterr().out


def test_cli_import_review_set_report(capsys):
    _run(capsys, "import", str(FIXTURES / "vtb_synthetic.pdf"))
    imports = json.loads(_run(capsys, "imports"))
    assert len(imports) == 1 and imports[0]["reconciled"]
    review = json.loads(_run(capsys, "review"))
    assert review, "synthetic statement has an unmatched operation"
    t = review[0]
    out = json.loads(_run(capsys, "set", str(t["id"]), "expense", "Продукты", "--note", "test", "--rule"))
    assert out["status"] == "confirmed" and out["decided_by"] == "user:ivan:cli"
    assert all(r["id"] != t["id"] for r in json.loads(_run(capsys, "review")))
    months = json.loads(_run(capsys, "report", "months"))
    assert months and "expense" in months[0]
    assert json.loads(_run(capsys, "tx", "--import-id", str(imports[0]["id"])))


def test_cli_set_rejects_unknown_category(capsys):
    _run(capsys, "import", str(FIXTURES / "vtb_synthetic.pdf"))
    tid = json.loads(_run(capsys, "tx", "--all"))[0]["id"]
    try:
        cli.main(["set", str(tid), "expense", "Нет такой"])
    except SystemExit as e:
        assert "unknown category" in str(e)
    else:
        raise AssertionError("expected exit")


def test_cli_decision_survives_rule_rerun(capsys):
    from app.services.categorize import recategorize
    from tests.conftest import session_factory

    _run(capsys, "import", str(FIXTURES / "vtb_synthetic.pdf"))
    t = json.loads(_run(capsys, "review"))[0]
    _run(capsys, "set", str(t["id"]), "expense", "Переводы людям")
    with session_factory()() as db:
        recategorize(db)
    after = json.loads(_run(capsys, "tx", "--all"))
    assert next(r for r in after if r["id"] == t["id"])["category"] == "Переводы людям"


def test_cli_trip_moves_purchases_to_trips(capsys):
    _run(capsys, "import", str(FIXTURES / "vtb_synthetic.pdf"))
    food = [r for r in json.loads(_run(capsys, "tx")) if r["category"] == "Продукты"]
    assert food
    d = food[0]["date"]
    _run(capsys, "trip", "add", "Тестовая поездка", d, d, "Продукты")
    assert json.loads(_run(capsys, "trip", "list"))[0]["name"] == "Тестовая поездка"
    moved = next(r for r in json.loads(_run(capsys, "tx")) if r["id"] == food[0]["id"])
    assert moved["category"] == "Поездки" and "Тестовая поездка" in moved["note"]
    tid = json.loads(_run(capsys, "trip", "list"))[0]["id"]
    _run(capsys, "trip", "rm", str(tid))
    back = next(r for r in json.loads(_run(capsys, "tx")) if r["id"] == food[0]["id"])
    assert back["category"] == "Продукты"


def test_cli_trip_rejects_unknown_category(capsys):
    try:
        cli.main(["trip", "add", "X", "2026-07-01", "2026-07-02", "Нет такой"])
    except SystemExit as e:
        assert "unknown categories" in str(e)
    else:
        raise AssertionError("expected exit")
