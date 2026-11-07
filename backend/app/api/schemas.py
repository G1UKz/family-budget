from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LoginIn(BaseModel):
    username: str
    password: str
    code: str = Field(min_length=6, max_length=8)


class UserOut(ORM):
    id: int
    username: str
    display_name: str


class AccountIn(BaseModel):
    name: str
    kind: str = "checking"
    bank: str = ""
    mask: str = ""
    owner: str = ""
    in_balance: bool = True
    active: bool = True


class AccountOut(AccountIn, ORM):
    id: int


class CategoryIn(BaseModel):
    name: str
    type: str = "expense"


class CategoryOut(CategoryIn, ORM):
    id: int


class RuleIn(BaseModel):
    priority: int = 1000
    pattern: str
    type: str
    category: str
    amount: Decimal | None = None
    weekday: int | None = Field(None, ge=1, le=7)
    note: str = ""
    enabled: bool = True


class RuleOut(RuleIn, ORM):
    id: int
    origin: str


class TxOut(ORM):
    id: int
    account_id: int
    date: date
    processed: date | None
    amount: Decimal
    description: str
    counterparty: str
    merchant: str
    type: str
    category: str
    note: str
    status: str
    decided_by: str


class TxPage(BaseModel):
    total: int
    items: list[TxOut]


class TxDecision(BaseModel):
    type: str
    category: str
    note: str | None = None
    make_rule: bool = False
    rule_pattern: str | None = None


class SuggestionOut(ORM):
    id: int
    transaction_id: int
    type: str
    category: str
    confidence: float
    explanation: str
    rule_pattern: str
    model: str
    status: str


class ReviewItem(BaseModel):
    tx: TxOut
    suggestion: SuggestionOut | None


class ImportOut(ORM):
    id: int
    filename: str
    bank: str
    account_id: int
    period_start: date | None
    period_end: date | None
    opening_balance: Decimal | None
    closing_balance: Decimal | None
    stated_income: Decimal | None
    stated_expense: Decimal | None
    parsed_income: Decimal
    parsed_expense: Decimal
    reconciled: bool
    ops_total: int
    ops_new: int
    uploaded_by: str
