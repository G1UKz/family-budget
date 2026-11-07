# База данных

PostgreSQL 17 (в кластере — CloudNativePG `family-budget-db`, база `budget`; локально — `docker compose`).
Модели — `backend/app/models.py`, миграции — Alembic в `backend/migrations/versions/`
(применяются init-контейнером `migrate` перед стартом приложения). Тесты гоняются на SQLite.

Суммы — `NUMERIC(14,2)`, рубли, со знаком: минус — деньги ушли со счёта, плюс — пришли.

## Схема

```mermaid
erDiagram
    accounts ||--o{ imports : "выписки счёта"
    accounts ||--o{ transactions : "account_id"
    accounts |o--o{ transactions : "counter_account_id"
    imports ||--o{ transactions : "import_id"
    rules |o--o{ transactions : "rule_id (SET NULL)"
    transactions ||--o{ suggestions : "CASCADE"

    users {
        int id PK
        string username UK
        string display_name
        string password_hash "argon2"
        string totp_secret
        timestamptz created_at
    }
    accounts {
        int id PK
        string name UK
        string kind "checking|savings|card|loan|cash"
        string bank
        string mask "последние 4 цифры"
        string owner
        bool in_balance "участвует в сверке остатков"
        bool active
    }
    categories {
        int id PK
        string name UK
        string type "тип по умолчанию"
    }
    rules {
        int id PK
        int priority "по возрастанию, первое совпадение"
        text pattern "regex по описанию и контрагенту"
        string type
        string category
        numeric amount "опционально: точная сумма"
        int weekday "опционально: 1=пн..7=вс"
        text note
        string origin "manual|import|review|ai"
        bool enabled
    }
    overrides {
        int id PK
        date date "UK вместе с amount"
        numeric amount
        string type
        string category
        text note
    }
    trips {
        int id PK
        string name
        date start
        date end
        text categories "через ;"
    }
    imports {
        int id PK
        string filename
        string sha256 UK "защита от повторной загрузки"
        string bank
        int account_id FK
        date period_start
        date period_end
        numeric opening_balance
        numeric closing_balance
        numeric stated_income "из шапки выписки"
        numeric stated_expense
        numeric parsed_income "посчитано по операциям"
        numeric parsed_expense
        bool reconciled
        int ops_total
        int ops_new
        string uploaded_by
        timestamptz created_at
    }
    transactions {
        int id PK
        string fingerprint UK "дедупликация между выписками"
        int account_id FK
        int counter_account_id FK "свой счёт на другой стороне"
        int import_id FK
        date date "дата операции: по ней бюджет"
        date processed "дата обработки: по ней итоги банка"
        numeric amount
        text description
        text counterparty
        string merchant
        string type
        string category
        text note
        string status "confirmed|review"
        int rule_id FK
        string decided_by "rule|override|trip|none|user:..."
    }
    suggestions {
        int id PK
        int transaction_id FK
        string type
        string category
        float confidence
        text explanation
        text rule_pattern
        string model
        string status "pending|accepted|rejected"
        timestamptz created_at
    }
```

## Типы операций (`transactions.type`)

| Тип | Смысл | В отчётах |
|---|---|---|
| `expense` | трата | расход категории |
| `refund` | возврат (трата с плюсом) | уменьшает расход своей категории |
| `income` | доход, кэшбэк | доход |
| `savings` | на накопительный счёт / обратно | строка «Отложили», не расход |
| `internal` | между своими счетами, переводы жене | исключаются (жене — отдельной строкой) |
| `capital` | разовые крупные события (сделка с недвижимостью) | отдельная строка «разовые» |
| `?` | не определено | очередь разбора (`status = review`) |

## Как операция получает категорию

1. **Импорт** (`services/importer.py`): парсер выписки → строки с `fingerprint`. Уже известные отпечатки пропускаются, поэтому пересекающиеся периоды не дублируются. Итоги сверяются с шапкой (`imports.reconciled`).
2. **Правила** (`categorize/engine.py`): первое совпадение по `priority`. Затем поправки знака (трата с плюсом → `refund`, «Переводы людям» с плюсом → «Переводы от людей»), затем `overrides` по (дата, сумма), затем `trips`: покупки указанных категорий вне домашнего города (`BUDGET_HOME_CITY_REGEX`) в даты поездки → «Поездки».
3. **Ничего не подошло** → `type = ?`, `status = review`. ИИ может создать `suggestions`, но применяются они только по решению человека.
4. **Решение человека** (веб или `budget set`) → `decided_by = user:…`. Повторный прогон правил (`rules/apply`, `budget trip add/rm`) такие операции не трогает.

Бюджетный период начинается с `BUDGET_START_DATE` (по умолчанию 01.06.2026): операции раньше хранятся, но в отчёты не идут.

## Где что лежит

- Личные данные (операции, имена контрагентов, правила с именами) — только в БД. В репозитории их нет, тесты — на синтетической выписке `backend/tests/fixtures/`.
- Пароли — argon2. `totp_secret` хранится как есть: БД доступна только внутри кластера.
- Бэкапы: CronJob `pg_dump` → restic → S3 (`deploy/helm/family-budget/templates/backup.yaml`), включается `backup.enabled`. Сейчас выключено, см. `docs/operations.md`.
