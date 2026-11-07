"""Admin CLI: `budget <command>` (inside the pod: `kubectl exec deploy/budget -- budget ...`)."""

import argparse
import csv
import getpass
import sys
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from app.db import Base, get_engine, session_factory
from app.models import Account, Category, Import, Override, Rule, Transaction, Trip, TxStatus, User
from app.security import hash_password, new_totp_secret, totp_uri


def _rows(path: str):
    with open(path, encoding="utf-8") as f:
        yield from csv.DictReader(line for line in f if not line.startswith("#"))


def cmd_init_db(_):
    """Create tables directly (dev/tests). In clusters use `alembic upgrade head`."""
    Base.metadata.create_all(get_engine())
    print("tables created")


def cmd_create_user(a):
    pw = a.password or getpass.getpass("password: ")
    with session_factory()() as db:
        u = db.scalar(select(User).where(User.username == a.username)) or User(username=a.username)
        u.display_name = a.display_name or a.username
        u.password_hash = hash_password(pw)
        u.totp_secret = new_totp_secret()
        db.add(u)
        db.commit()
        print("Add to an authenticator app (Google Authenticator, Aegis, 1Password):")
        print(totp_uri(u))
        try:
            import qrcode  # optional

            qr = qrcode.QRCode()
            qr.add_data(totp_uri(u))
            qr.print_ascii()
        except ImportError:
            pass


def cmd_import_rules(a):
    """Load rules.csv / overrides.csv / trips.csv (private data, kept outside the repo)."""
    with session_factory()() as db:
        if a.replace:
            db.query(Rule).filter(Rule.origin == "import").delete()
        n = 0
        for i, r in enumerate(_rows(a.rules)):
            db.add(
                Rule(
                    priority=1000 + i * 10,
                    pattern=r["pattern"],
                    type=r["type"],
                    category=r["category"],
                    note=r.get("note") or "",
                    origin="import",
                    amount=Decimal(r["amount"]) if r.get("amount") else None,
                    weekday=int(r["weekday"]) if r.get("weekday") else None,
                )
            )
            n += 1
            _ensure_category(db, r["category"], r["type"])
        if a.overrides:
            for r in _rows(a.overrides):
                d, amt = date.fromisoformat(r["date"]), Decimal(r["amount"])
                o = db.scalar(select(Override).where(Override.date == d, Override.amount == amt)) or Override(
                    date=d, amount=amt
                )
                o.type, o.category, o.note = r["type"], r["category"], r.get("note") or ""
                db.add(o)
                _ensure_category(db, r["category"], r["type"])
        if a.trips:
            for r in _rows(a.trips):
                if not db.scalar(select(Trip).where(Trip.name == r["name"], Trip.start == date.fromisoformat(r["start"]))):
                    db.add(
                        Trip(
                            name=r["name"],
                            start=date.fromisoformat(r["start"]),
                            end=date.fromisoformat(r["end"]),
                            categories=r["categories"],
                        )
                    )
        _ensure_category(db, "Поездки", "expense")
        _ensure_category(db, "Переводы от людей", "income")
        db.commit()
        print(f"rules: {n}")


def _ensure_category(db, name: str, typ: str):
    if name and typ != "?" and not db.scalar(select(Category).where(Category.name == name)):
        db.add(Category(name=name, type=typ))
        db.flush()


def cmd_account(a):
    with session_factory()() as db:
        acc = db.scalar(select(Account).where(Account.mask == a.mask)) if a.mask else None
        acc = acc or db.scalar(select(Account).where(Account.name == a.name)) or Account()
        acc.name, acc.kind, acc.bank, acc.mask, acc.owner = a.name, a.kind, a.bank, a.mask or "", a.owner
        acc.in_balance = not a.no_balance
        db.add(acc)
        db.commit()
        print(f"account #{acc.id} {acc.name}")


def cmd_import(a):
    from app.services.importer import DuplicateImport, import_statement

    with session_factory()() as db:
        for p in a.files:
            try:
                imp = import_statement(db, Path(p).read_bytes(), Path(p).name, "cli")
            except DuplicateImport:
                print(f"{p}: already imported")
                continue
            print(
                f"{p}: {imp.ops_new}/{imp.ops_total} new ops, account #{imp.account_id}, "
                f"reconciled={'OK' if imp.reconciled else 'MISMATCH'} "
                f"(income {imp.parsed_income}/{imp.stated_income}, expense {imp.parsed_expense}/{imp.stated_expense})"
            )


def cmd_migrate_journal(a):
    """Carry categories from the legacy journal.csv onto imported transactions.

    Match key: (account by source name, date, amount, description prefix). Every journal
    row must find exactly one transaction; totals per month/type/category are then compared.
    """
    src_map = dict(s.split("=", 1) for s in a.source)  # "ВТБ=ВТБ основной"
    with session_factory()() as db:
        accs = {name: db.scalar(select(Account).where(Account.name == acc)) for name, acc in src_map.items()}
        missing = [n for n, acc in accs.items() if acc is None]
        if missing:
            sys.exit(f"unknown accounts for sources: {missing}")
        pool: dict[tuple, list[Transaction]] = defaultdict(list)
        for t in db.scalars(select(Transaction).order_by(Transaction.id)):
            pool[(t.account_id, t.date, t.amount)].append(t)
        matched, unmatched = 0, []
        expected: dict[tuple, Decimal] = defaultdict(Decimal)
        for r in _rows(a.journal):
            acc = accs.get(r["source"])
            if acc is None:
                unmatched.append(r)
                continue
            key = (acc.id, date.fromisoformat(r["date"]), Decimal(r["amount"]))
            cands = pool.get(key, [])
            desc = r["description"][:100]
            pick = next((t for t in cands if t.description[:100] == desc), cands[0] if cands else None)
            if pick is None:
                unmatched.append(r)
                continue
            cands.remove(pick)
            _ensure_category(db, r["category"], r["type"])
            pick.type, pick.category, pick.note = r["type"], r["category"], r.get("note") or ""
            pick.status = TxStatus.review if r["type"] == "?" else TxStatus.confirmed
            pick.decided_by = "user:migration"
            expected[(r["date"][:7], r["type"], r["category"])] += Decimal(r["amount"])
            matched += 1
        db.commit()
        # verification: totals per month/type/category in DB == journal
        actual: dict[tuple, Decimal] = defaultdict(Decimal)
        for t in db.scalars(select(Transaction).where(Transaction.decided_by == "user:migration")):
            actual[(t.date.strftime("%Y-%m"), t.type, t.category)] += t.amount
        diffs = {k: (expected[k], actual.get(k)) for k in expected if expected[k] != actual.get(k)}
        left = [t for ts in pool.values() for t in ts if t.date >= date.fromisoformat(a.since)]
        print(f"journal rows matched: {matched}, unmatched: {len(unmatched)}")
        print(f"category totals equal: {not diffs} ({len(expected)} month/type/category groups)")
        print(f"statement ops after {a.since} not in journal (left for rules/review): {len(left)}")
        for r in unmatched[:20]:
            print("  unmatched:", r["date"], r["source"], r["amount"], r["description"][:60])
        if unmatched or diffs:
            sys.exit(1)


def _json(obj):
    import json

    print(json.dumps(obj, ensure_ascii=False, indent=1, default=str))


def _tx(t: Transaction) -> dict:
    return {
        "id": t.id,
        "date": t.date,
        "processed": t.processed,
        "amount": t.amount,
        "account": t.account.name,
        "description": t.description,
        "counterparty": t.counterparty,
        "type": t.type,
        "category": t.category,
        "note": t.note,
        "status": t.status,
        "decided_by": t.decided_by,
    }


def cmd_report(a):
    """Read-only reports as JSON (same numbers as the web UI)."""
    from app.services import reports

    with session_factory()() as db:
        if a.kind == "categories":
            _json(reports.categories(db, a.month))
        else:
            _json(getattr(reports, a.kind)(db))


def cmd_imports(a):
    with session_factory()() as db:
        rows = db.scalars(select(Import).order_by(Import.id.desc()).limit(a.last)).all()
        _json(
            [
                {
                    "id": i.id,
                    "file": i.filename,
                    "account": i.account.name,
                    "period": [i.period_start, i.period_end],
                    "opening": i.opening_balance,
                    "closing": i.closing_balance,
                    "income": [i.parsed_income, i.stated_income],
                    "expense": [i.parsed_expense, i.stated_expense],
                    "reconciled": i.reconciled,
                    "ops": [i.ops_new, i.ops_total],
                    "created": i.created_at,
                }
                for i in rows
            ]
        )


def cmd_tx(a):
    """List operations (budget period only unless --all)."""
    from sqlalchemy import or_

    from app.config import get_settings

    s = select(Transaction)
    if not a.all:
        s = s.where(Transaction.date >= get_settings().start_date)
    if a.since:
        s = s.where(Transaction.date >= date.fromisoformat(a.since))
    if a.until:
        s = s.where(Transaction.date <= date.fromisoformat(a.until))
    if a.import_id:
        s = s.where(Transaction.import_id == a.import_id)
    if a.status:
        s = s.where(Transaction.status == a.status)
    if a.type:
        s = s.where(Transaction.type.in_(a.type.split(",")))
    if a.category:
        s = s.where(Transaction.category == a.category)
    if a.q:
        like = f"%{a.q}%"
        s = s.where(or_(Transaction.description.ilike(like), Transaction.counterparty.ilike(like)))
    with session_factory()() as db:
        _json([_tx(t) for t in db.scalars(s.order_by(Transaction.date, Transaction.id).limit(a.limit))])


def cmd_review(_):
    """Review queue with pending AI suggestions."""
    from app.config import get_settings
    from app.models import Suggestion

    with session_factory()() as db:
        txs = db.scalars(
            select(Transaction)
            .where(Transaction.status == TxStatus.review, Transaction.date >= get_settings().start_date)
            .order_by(Transaction.date)
        ).all()
        sug = {
            s.transaction_id: s
            for s in db.scalars(
                select(Suggestion).where(Suggestion.transaction_id.in_([t.id for t in txs]), Suggestion.status == "pending")
            )
        }
        out = []
        for t in txs:
            row = _tx(t)
            if s := sug.get(t.id):
                row["suggestion"] = {
                    "id": s.id,
                    "type": s.type,
                    "category": s.category,
                    "confidence": s.confidence,
                    "explanation": s.explanation,
                    "rule_pattern": s.rule_pattern,
                }
            out.append(row)
        _json(out)


def cmd_set(a):
    """Decide one operation: type + category (+ note, + reusable rule)."""
    from app.services.decide import DecisionError, decide

    with session_factory()() as db:
        tx = db.get(Transaction, a.id)
        if tx is None:
            sys.exit(f"transaction {a.id} not found")
        try:
            decide(
                db,
                tx,
                a.type,
                a.category,
                f"user:{a.by}:cli",
                note=a.note,
                make_rule=a.rule is not None,
                rule_pattern=a.rule or None,
            )
        except DecisionError as e:
            sys.exit(str(e))
        db.commit()
        _json(_tx(tx))


def cmd_suggest(a):
    """Ask the AI for suggestions on the review queue (needs the Anthropic key)."""
    from app.services.suggest import get_suggester, suggest_pending

    s = get_suggester()
    if s is None:
        sys.exit("AI is not configured (BUDGET_ANTHROPIC_API_KEY)")
    with session_factory()() as db:
        print(f"suggestions created: {suggest_pending(db, s, a.limit)}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="budget")
    sub = p.add_subparsers(required=True)
    sub.add_parser("init-db").set_defaults(fn=cmd_init_db)
    s = sub.add_parser("create-user")
    s.add_argument("username")
    s.add_argument("--display-name", default="")
    s.add_argument("--password", help="omit to be prompted")
    s.set_defaults(fn=cmd_create_user)
    s = sub.add_parser("import-rules")
    s.add_argument("rules")
    s.add_argument("--overrides")
    s.add_argument("--trips")
    s.add_argument("--replace", action="store_true")
    s.set_defaults(fn=cmd_import_rules)
    s = sub.add_parser("account", help="create/update an account")
    s.add_argument("name")
    s.add_argument("--kind", default="checking")
    s.add_argument("--bank", default="")
    s.add_argument("--mask", default="")
    s.add_argument("--owner", default="")
    s.add_argument("--no-balance", action="store_true")
    s.set_defaults(fn=cmd_account)
    s = sub.add_parser("import", help="import PDF statements")
    s.add_argument("files", nargs="+")
    s.set_defaults(fn=cmd_import)
    s = sub.add_parser("migrate-journal")
    s.add_argument("journal")
    s.add_argument("--source", action="append", required=True, help='journal source=account name, e.g. "ВТБ=Основной"')
    s.add_argument("--since", default="2026-06-01")
    s.set_defaults(fn=cmd_migrate_journal)
    s = sub.add_parser("report", help="reports as JSON")
    s.add_argument("kind", choices=["summary", "months", "categories", "balances"])
    s.add_argument("--month", help="YYYY-MM, for categories")
    s.set_defaults(fn=cmd_report)
    s = sub.add_parser("imports", help="recent statement imports as JSON")
    s.add_argument("--last", type=int, default=10)
    s.set_defaults(fn=cmd_imports)
    s = sub.add_parser("tx", help="list operations as JSON")
    s.add_argument("--since")
    s.add_argument("--until")
    s.add_argument("--import-id", type=int)
    s.add_argument("--status", choices=["review", "confirmed"])
    s.add_argument("--type", help="comma-separated")
    s.add_argument("--category")
    s.add_argument("-q", help="substring of description/counterparty")
    s.add_argument("--limit", type=int, default=500)
    s.add_argument("--all", action="store_true", help="include operations before the budget start")
    s.set_defaults(fn=cmd_tx)
    sub.add_parser("review", help="review queue as JSON").set_defaults(fn=cmd_review)
    s = sub.add_parser("set", help="decide an operation")
    s.add_argument("id", type=int)
    s.add_argument("type", choices=["expense", "income", "refund", "internal", "savings", "capital", "?"])
    s.add_argument("category")
    s.add_argument("--note")
    s.add_argument("--rule", nargs="?", const="", help="also create a rule (optional regex)")
    s.add_argument("--by", default="ivan", help="whose decision; stored as user:<by>:cli and kept by rule re-runs")
    s.set_defaults(fn=cmd_set)
    s = sub.add_parser("suggest", help="AI suggestions for the review queue")
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(fn=cmd_suggest)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
