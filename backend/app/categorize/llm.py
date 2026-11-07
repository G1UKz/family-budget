"""AI suggestions for transactions the rules could not categorize.

The model only *proposes* a category with an explanation and an optional reusable rule
pattern; a human accepts or rejects it in the review queue.
"""

import json
import logging
from dataclasses import dataclass
from typing import Protocol

import anthropic

log = logging.getLogger(__name__)

SYSTEM = """Ты помогаешь вести семейный бюджет (Россия, рубли). Тебе дают одну банковскую операцию,
список допустимых категорий с типами и несколько уже размеченных похожих операций.
Выбери тип и категорию строго из списка. Типы: expense — трата, income — доход,
internal — перевод между своими счетами, savings — пополнение/снятие накоплений,
capital — разовая крупная сделка, "?" — если по описанию определить нельзя.
Переводы конкретным людям по СБП без ясного назначения — "Переводы людям".
Объясни выбор одним коротким предложением по-русски. Если у продавца устойчивое
название, предложи регулярное выражение rule_pattern (без учёта регистра) для правила,
которое поймает его будущие операции, иначе пустую строку. Не выдумывай категории."""

SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": ["expense", "income", "internal", "savings", "capital", "?"]},
        "category": {"type": "string"},
        "confidence": {"type": "number"},
        "explanation": {"type": "string"},
        "rule_pattern": {"type": "string"},
    },
    "required": ["type", "category", "confidence", "explanation", "rule_pattern"],
    "additionalProperties": False,
}


@dataclass
class Proposal:
    type: str
    category: str
    confidence: float
    explanation: str
    rule_pattern: str
    model: str


@dataclass
class TxView:
    date: str
    amount: str
    description: str
    counterparty: str


class Suggester(Protocol):
    def suggest(
        self, tx: TxView, categories: list[tuple[str, str]], examples: list[tuple[TxView, str, str]]
    ) -> Proposal | None: ...


class AnthropicSuggester:
    def __init__(self, api_key: str, model: str, effort: str = "low"):
        self.client = anthropic.Anthropic(api_key=api_key, max_retries=3, timeout=60)
        self.model = model
        self.effort = effort

    def suggest(self, tx, categories, examples):
        cats = "\n".join(f"- {name} ({typ})" for name, typ in categories)
        ex = (
            "\n".join(f"- {e.date} {e.amount} | {e.description} | {e.counterparty} => {t} / {c}" for e, t, c in examples)
            or "(нет)"
        )
        prompt = (
            f"Категории:\n{cats}\n\nПохожие размеченные операции:\n{ex}\n\n"
            f"Операция: {tx.date}, сумма {tx.amount} ₽\nОписание: {tx.description}\n"
            f"Контрагент: {tx.counterparty or '—'}"
        )
        try:
            resp = self.client.beta.messages.create(
                model=self.model,
                max_tokens=2048,
                system=SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": SCHEMA}},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.APIConnectionError as e:
            log.warning("LLM unreachable: %s", e)
            return None
        except anthropic.APIStatusError as e:
            log.warning("LLM error %s: %s", e.status_code, e.message)
            return None
        if resp.stop_reason == "refusal":
            log.info("LLM declined to categorize transaction")
            return None
        text = next((b.text for b in resp.content if b.type == "text"), None)
        if not text:
            return None
        data = json.loads(text)
        valid = {name for name, _ in categories}
        if data["type"] != "?" and data["category"] not in valid:
            data["type"], data["category"] = "?", ""
        return Proposal(
            data["type"], data["category"], float(data["confidence"]), data["explanation"], data["rule_pattern"], resp.model
        )
