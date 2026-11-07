# Family Budget

Self-hosted сервис семейного бюджета: импорт банковских выписок со сверкой с банком, детерминированные правила категоризации и AI-подсказки (Claude) для неопознанных операций с подтверждением человеком. Развёртывание — GitOps (Argo CD) в single-node k3s на VDS.

> Pet-project: рабочий инструмент для семьи и полигон для DevOps/SRE-практик — CI/CD, GitOps, секреты в Vault, бэкапы с проверкой восстановления, мониторинг и алерты.

## Возможности

- **Импорт PDF-выписок** (ВТБ; парсеры Сбера и Т-Банка — по образцам). Сверка с шапкой выписки: поступления, расходы и остаток на конец должны совпасть до копейки, иначе выписка помечается ✗. Повторная загрузка и пересекающиеся периоды не создают дублей (fingerprint операции).
- **Правила**: регулярка по «описание | контрагент» + необязательные сумма и день недели; первое совпадение по приоритету. Точечные исправления (дата + сумма) и поездки (траты вне домашнего города в даты поездки → «Поездки»).
- **Очередь разбора**: всё, что не распознали правила, ждёт человека. Кнопка «Подсказать с AI» просит у Claude категорию, объяснение и регулярку для будущего правила. **AI ничего не записывает сам** — только «Да» / «Да + правило» / «Нет».
- **Дашборд**: итоги месяца с динамикой, доходы/траты/отложили по месяцам, категории с переходом к операциям, сверка остатка на счетах по месяцам.
- **Учёт**: внутренние переводы и накопления не считаются тратами; возвраты уменьшают свою категорию; бюджет по дате операции, остатки — по дате проведения банком.
- **Вход**: логин + пароль (argon2) + TOTP, ограничение попыток, cookie `Secure`/`SameSite=Strict`.

## Архитектура

```
 GitHub ── push ──► GitHub Actions ──► GHCR (app, backup images)
   ▲                  │ lint · tests (SQLite+Postgres) · alembic check
   │                  │ helm lint · kubeconform · ansible-lint · shellcheck
   │                  │ privacy check · gitleaks · trivy
   └── commit tag ◄───┘ (gitops-bump)
   │
   ▼ watches
 Argo CD (app of apps) ──► k3s single node (VDS)
   ├─ cert-manager ── Let's Encrypt ── Traefik Ingress ── family-budget (FastAPI + React SPA)
   ├─ CloudNativePG ── Postgres 17 ◄──────────────────────┘
   ├─ Vault (raft) ──► External Secrets ──► k8s Secrets (app key, Anthropic key, restic creds)
   ├─ VictoriaMetrics stack (vmagent, vmsingle, vmalert, alertmanager, grafana)
   └─ CronJobs: pg_dump → restic (S3, off-site) · weekly restore-check · Vault raft snapshot → restic
```

| Слой | Технологии |
|---|---|
| Backend | Python 3.13, FastAPI, SQLAlchemy 2, Alembic, pdfplumber, Anthropic SDK |
| Frontend | React 18, TypeScript, Vite, Recharts |
| Данные | PostgreSQL 17 (CloudNativePG) |
| Платформа | k3s, Argo CD, Helm, cert-manager, Traefik, Vault + External Secrets Operator |
| Наблюдаемость | Prometheus-метрики приложения, VictoriaMetrics, Grafana, PrometheusRule-алерты |
| Инфраструктура как код | Ansible (hardening VDS, k3s), Helm-чарт, Argo CD Applications |

Структура репозитория:

```
backend/          FastAPI-приложение, парсеры, правила, AI, CLI `budget`, тесты, миграции
frontend/         React SPA (собирается в тот же образ)
deploy/helm/      Helm-чарт приложения (Deployment, CNPG Cluster, ExternalSecrets, backup CronJobs, алерты)
deploy/argocd/    root app-of-apps и Applications платформы
deploy/platform/  ClusterIssuer, ClusterSecretStore, снапшоты Vault
deploy/vault/     bootstrap.sh / unseal.sh
deploy/ansible/   подготовка VDS и установка k3s + Argo CD
deploy/backup/    образ pg_dump + restic, скрипт бэкапа и проверки восстановления
docs/             runbook
```

### Модель данных

Счета (свои: текущие, мастер-счёт, накопительные, кредиты), операции (одна строка выписки = операция на своём счёте; переводы между своими счетами типизируются `internal`/`savings` и связываются со счётом-корреспондентом), импорты (реквизиты выписки и результат сверки), правила, точечные исправления, поездки, AI-подсказки со статусом. Типы операций: `expense`, `income`, `refund`, `internal`, `savings`, `capital`, `?`.

## Локальный запуск

```bash
cp .env.example .env            # по желанию: BUDGET_ANTHROPIC_API_KEY
docker compose up --build -d
docker compose exec app budget create-user ivan --display-name Иван   # покажет otpauth:// для приложения-аутентификатора
open http://localhost:8000
```

Разработка без Docker: `python -m venv .venv && .venv/bin/pip install -e "backend[dev]"`, `cd backend && ../.venv/bin/pytest`, фронт — `cd frontend && npm i && npm run dev` (проксирует `/api` на :8000).

### CLI

```bash
budget account "ВТБ основной" --bank ВТБ --mask 1234          # счёт; выписки сопоставляются по последним 4 цифрам
budget import-rules rules.csv --overrides overrides.csv --trips trips.csv
budget import vtb_2026-06-01_2026-10-31.pdf                     # печатает результат сверки
budget migrate-journal journal.csv --source "ВТБ=ВТБ основной"  # перенос истории
```

## Перенос истории из journal.csv

Старый учёт вёлся скриптами и CSV вне репозитория. Порядок переноса:

1. Завести счета (`budget account`) и загрузить правила (`budget import-rules`).
2. Импортировать исходные PDF-выписки за тот же период — они дают даты проведения, остатки и сверку.
3. `budget migrate-journal journal.csv --source ...` — переносит тип, категорию и заметку на совпавшие операции (ключ: счёт, дата, сумма, описание) и сверяет итоги по группам «месяц × тип × категория».

Проверено на реальных данных (01.06–31.10.2026): обе выписки сошлись с банком; движок правил сервиса независимо разметил все 661 операцию так же, как старый журнал; миграция — 661/661 совпадений, итоги по 138 группам равны; остатки по месяцам совпадают со старым дашбордом.

## Приватность

Репозиторий публичный, поэтому в нём нет и не будет: выписок, журнала, правил с именами людей, номеров счетов и карт, ключей. Правила и данные живут только в БД. Тесты используют синтетическую выписку (`backend/tests/fixtures/make_vtb_pdf.py`). CI падает, если в git попадёт PDF кроме фикстуры, `journal/rules/overrides/trips.csv`, `.env`, kubeconfig или число, похожее на номер счёта/карты (`scripts/check-private-data.sh`), плюс gitleaks.

## AI-категоризация

`backend/app/categorize/llm.py`: одна операция → Claude с списком допустимых категорий и несколькими похожими уже размеченными операциями. Ответ — строгий JSON по схеме (structured outputs): тип, категория, уверенность, объяснение, регулярка для правила. Категория вне списка отбрасывается, некорректная регулярка игнорируется. Модель настраивается `BUDGET_LLM_MODEL` (по умолчанию `claude-opus-5-5`, effort `low`), включён server-side fallback на случай отказа модели. Без ключа сервис работает, просто без подсказок.

## Развёртывание на VDS

См. [docs/operations.md](docs/operations.md): подготовка сервера Ansible'ом, bootstrap Vault, первый деплой, бэкап и восстановление, распечатка Vault после перезагрузки, рост до нескольких узлов.

Почему один узел: для HA control plane k3s с embedded etcd нужно 3 сервера, а с данными на локальном диске HA ещё и требует реплик Postgres. Нагрузка — два пользователя, поэтому сейчас один узел, но всё готово к росту: Ansible-инвентарь с группой агентов, `postgres.cnpg.instances`, Vault на raft.

## Roadmap

- Сбор выписок из почтового ящика (IMAP CronJob) — вместо ручной загрузки.
- Парсеры Сбера и Т-Банка (по образцам выписок), CSV-импорт.
- Telegram-уведомления Alertmanager и о новых операциях в разборе.
- Сверка по каждому счёту отдельно и учёт долгов (ипотека, автокредит) как счетов-обязательств.
