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
