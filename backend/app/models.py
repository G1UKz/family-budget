"""Domain model.

Accounts are both own (checking, savings, cards, loans) and external.
Every statement line becomes a Transaction on one own account. Movements between own
accounts are typed ``internal``/``savings`` and carry ``counter_account_id``; they never
count as income or expense. Balances are reconciled per account and per statement.
"""

import datetime as dt
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

Money = Numeric(14, 2)


class TxType(StrEnum):
    expense = "expense"
    income = "income"
    refund = "refund"  # reduces the expense of its category
    internal = "internal"  # between own accounts, excluded from income/expense
    savings = "savings"  # to/from savings accounts: shown as "Отложили"
    capital = "capital"  # one-off capital events (real estate deal etc.)
    unknown = "?"  # needs a human decision


class TxStatus(StrEnum):
    confirmed = "confirmed"
    review = "review"


class AccountKind(StrEnum):
    checking = "checking"
    savings = "savings"
    card = "card"
    loan = "loan"
    cash = "cash"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(128), default="")
    password_hash: Mapped[str] = mapped_column(String(256))
    totp_secret: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    kind: Mapped[str] = mapped_column(String(16), default=AccountKind.checking)
    bank: Mapped[str] = mapped_column(String(64), default="")
    mask: Mapped[str] = mapped_column(String(8), default="")  # last 4 digits, used to match statements
    owner: Mapped[str] = mapped_column(String(64), default="")
    # Included into "money on accounts" reconciliation (checking + master accounts).
    in_balance: Mapped[bool] = mapped_column(Boolean, default=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    type: Mapped[str] = mapped_column(String(16), default=TxType.expense)


class Rule(Base):
    """First match by ``priority`` (ascending) wins, like the original rules.csv."""

    __tablename__ = "rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    priority: Mapped[int] = mapped_column(Integer, default=1000, index=True)
    pattern: Mapped[str] = mapped_column(Text)  # regex over "description | counterparty", case-insensitive
    type: Mapped[str] = mapped_column(String(16))
    category: Mapped[str] = mapped_column(String(128))
    amount: Mapped[Decimal | None] = mapped_column(Money)  # abs(amount) must equal
    weekday: Mapped[int | None] = mapped_column(Integer)  # 1=Mon .. 7=Sun
    note: Mapped[str] = mapped_column(Text, default="")
    origin: Mapped[str] = mapped_column(String(16), default="manual")  # manual | ai | import
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Override(Base):
    """Pinpoint fix for a specific operation: (date, amount) -> type/category."""

    __tablename__ = "overrides"
    __table_args__ = (UniqueConstraint("date", "amount"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Money)
    type: Mapped[str] = mapped_column(String(16))
    category: Mapped[str] = mapped_column(String(128))
    note: Mapped[str] = mapped_column(Text, default="")


class Trip(Base):
    __tablename__ = "trips"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    start: Mapped[dt.date] = mapped_column(Date)
    end: Mapped[dt.date] = mapped_column(Date)
    categories: Mapped[str] = mapped_column(Text)  # ";"-separated


class Import(Base):
    __tablename__ = "imports"
    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(256))
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    bank: Mapped[str] = mapped_column(String(32))
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    period_start: Mapped[dt.date | None] = mapped_column(Date)
    period_end: Mapped[dt.date | None] = mapped_column(Date)
    opening_balance: Mapped[Decimal | None] = mapped_column(Money)
    closing_balance: Mapped[Decimal | None] = mapped_column(Money)
    stated_income: Mapped[Decimal | None] = mapped_column(Money)
    stated_expense: Mapped[Decimal | None] = mapped_column(Money)
    parsed_income: Mapped[Decimal] = mapped_column(Money, default=0)
    parsed_expense: Mapped[Decimal] = mapped_column(Money, default=0)
    reconciled: Mapped[bool] = mapped_column(Boolean, default=False)
    ops_total: Mapped[int] = mapped_column(Integer, default=0)
    ops_new: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    account: Mapped[Account] = relationship()


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    counter_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))
    import_id: Mapped[int | None] = mapped_column(ForeignKey("imports.id"))
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    processed: Mapped[dt.date | None] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Money)
    description: Mapped[str] = mapped_column(Text, default="")
    counterparty: Mapped[str] = mapped_column(Text, default="")
    merchant: Mapped[str] = mapped_column(String(256), default="")
    type: Mapped[str] = mapped_column(String(16), default=TxType.unknown)
    category: Mapped[str] = mapped_column(String(128), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default=TxStatus.review, index=True)
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("rules.id", ondelete="SET NULL"))
    decided_by: Mapped[str] = mapped_column(String(64), default="")  # rule | override | trip | user:<name>
    account: Mapped[Account] = relationship(foreign_keys=[account_id])


class Suggestion(Base):
    """AI proposal for a transaction in review. Never applied without a human click."""

    __tablename__ = "suggestions"
    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(16))
    category: Mapped[str] = mapped_column(String(128))
    confidence: Mapped[float] = mapped_column(default=0.0)
    explanation: Mapped[str] = mapped_column(Text, default="")
    rule_pattern: Mapped[str] = mapped_column(Text, default="")  # proposed regex for a reusable rule
    model: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | accepted | rejected
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
