# Runbook

## 0. Что нужно заранее

- VDS: 2 vCPU / 4 ГБ RAM / 80 ГБ NVMe, Ubuntu 24.04, доступ root по SSH-ключу — профиль «для дома» (полный мониторинг выключен). С полным мониторингом и запасом — 4 vCPU / 8 ГБ.
- Домен/поддомен с A-записью на IP сервера (для Let's Encrypt).
- S3-совместимое хранилище **вне** VDS для restic (например, Yandex Object Storage / Backblaze B2): бакет + ключи. Можно позже: без него бэкапы выключены (`backup.enabled: false`), а `bootstrap.sh` пропускает секрет бэкапов при пустом ответе.
- Ключ Anthropic API (необязательно).
- Менеджер паролей для unseal-ключей Vault и пароля restic.

## 1. Подготовка сервера (Ansible)

```bash
cd deploy/ansible
cp inventory.example.ini inventory.ini        # IP, admin_user, ssh-ключ, admin_cidrs
ansible-galaxy collection install -r requirements.yml
ansible-playbook site.yml --check --diff        # сначала сухой прогон
ansible-playbook site.yml                         # первый запуск: ansible_user=root в инвентаре
```

Первый play подключается под root и запрещает вход под root; следующие play'и подключаются под `admin_user`. Для повторных запусков поставить в инвентаре `ansible_user=<admin_user>`. Проверено на Ubuntu 24.04 (ssh через socket activation: плейбук создаёт `/run/sshd` для `sshd -t`).

Плейбук: обновления + unattended-upgrades, пользователь с ключом, SSH без паролей и root, fail2ban, ufw (наружу только 80/443, SSH и 6443 — только с `admin_cidrs`), k3s с шифрованием секретов в etcd, Argo CD через k3s HelmChart и root-приложение. Kubeconfig сохраняется в `deploy/ansible/kubeconfig-<host>` (git-ignored). Подключить к kubie (контекст `family-budget`) и удалить исходник:

```bash
umask 077
sed -e 's/127\.0\.0\.1/<IP>/' -e 's/: default$/: family-budget/' -e 's/^- name: default$/- name: family-budget/' \
    -e 's/^  name: default$/  name: family-budget/' kubeconfig-budget-1 > ~/.kube/kubie/family-budget.yaml
rm -P kubeconfig-budget-1
kubie ctx family-budget
kubectl -n argocd get applications            # root → платформа → family-budget
```

Это admin-сертификат k3s (cluster-admin): хранить только на своей машине.

**Доступ только через бастион.** Когда SSH и 6443 не должны торчать в интернет, в инвентаре:
`admin_cidrs=["<IP бастиона>/32"]` и `ansible_ssh_common_args="-o ProxyJump=<бастион>"`, затем
`ansible-playbook site.yml` — добавит правила для бастиона и удалит открытые (`0.0.0.0/0`).
На своей машине:

```bash
# ~/.ssh/config: Host budget-k3s → HostName <IP>, ProxyJump <бастион>
ssh -fN -o ExitOnForwardFailure=yes -L 127.0.0.1:16443:<IP>:6443 <бастион>   # туннель к API
sed -i '' 's|server: https://<IP>:6443|server: https://127.0.0.1:16443|' ~/.kube/kubie/family-budget.yaml
kubie ctx family-budget      # сертификат k3s уже содержит 127.0.0.1 в SAN
```

Новые агенты (`k3s_agents`) ходят к серверу на 6443 — их IP тоже добавить в `admin_cidrs`.

## 2. Vault

Vault поднимается запечатанным. После того как Application `vault` стал Healthy/Progressing:

```bash
deploy/vault/bootstrap.sh
```

Скрипт идемпотентен (можно перезапускать: попросит токен с правами администратора). Шаги: init (5 ключей, порог 3) → unseal → KV v2 `kv/` → Kubernetes auth → политики и роли для External Secrets и снапшотов → секреты `kv/family-budget/app` (случайный `secret_key`, ключ Anthropic, регэксп домашнего города `home_city_regex`) и `kv/family-budget/backup` (restic-репозиторий, сгенерированный пароль, S3-ключи). Unseal-ключи, root-токен и пароль restic — сразу в менеджер паролей, `vault-init.json` удалить (`shred -u`).

После перезагрузки узла/пода Vault снова запечатан → ESO не обновляет секреты (уже созданные k8s Secrets продолжают работать): `deploy/vault/unseal.sh`.

Если ExternalSecret успел упасть до bootstrap'а (`SecretSyncedError`), подтолкнуть: `kubectl -n budget annotate externalsecret family-budget force-sync=$(date +%s) --overwrite`.

## 3. Приложение

В `deploy/helm/family-budget/values-prod.yaml` указать домен. Без своего домена подходит `budget.<IP>.sslip.io` (резолвится в IP, Let's Encrypt выдаёт сертификат). Email в `deploy/platform/cluster-issuer.yaml` необязателен (уведомления об истечении; cert-manager продлевает сам). Пуш в `main` → CI собирает образы, коммитит тег → Argo CD синхронизирует.

```bash
kubectl -n budget exec -it deploy/family-budget -- budget create-user ivan --display-name Иван
kubectl -n budget exec -it deploy/family-budget -- budget create-user partner --display-name Партнёр
```

Перенос данных: правила и выписки загружаются через UI или `kubectl cp` + `budget import-rules` / `budget import` / `budget migrate-journal` (см. README).

### Перенос готовой базы (например, из локального docker compose)

```bash
docker compose exec -T db pg_dump -U budget -d budget -Fc --no-owner --no-acl > private/budget.dump
kubectl -n argocd patch application family-budget --type merge -p '{"spec":{"syncPolicy":{"automated":null}}}'
kubectl -n budget scale deploy/family-budget --replicas=0
kubectl -n budget exec -i family-budget-db-1 -c postgres -- \
  pg_restore -d budget --clean --if-exists --no-owner --no-acl --role=budget < private/budget.dump
# сверить: одинаковые count(*) и sum(amount) по type на обеих сторонах
kubectl -n argocd patch application family-budget --type merge \
  -p '{"spec":{"syncPolicy":{"automated":{"prune":true,"selfHeal":true}}}}'   # Argo вернёт replicas=1
```

Пользователи и их TOTP переезжают вместе с базой.

## 4. Бэкапы

> Сейчас выключены: нет S3. Включение: бакет → `deploy/vault/bootstrap.sh` (ответить про S3) → `backup.enabled: true` в `values-prod.yaml` → раскомментировать `deploy/platform/vault-snapshot.yaml` → push. До этого данные живут только на диске VDS.

| Что | Как | Когда |
|---|---|---|
| Postgres | `pg_dump -Fc` → restic (тег `<release>`), retention 7d/5w/12m, `restic check` 5% | ежедневно 03:15 |
| Проверка восстановления | restic restore latest → временный Postgres в поде → `pg_restore` → проверки (есть операции, импорты) | воскресенье 04:45 |
| Vault | `vault operator raft snapshot` → restic (тег `vault`) | ежедневно 03:30 |

Алерты: `BudgetBackupFailed`, `BudgetBackupMissing` (>36 ч без успешного бэкапа).

Ручной запуск: `kubectl -n budget create job --from=cronjob/family-budget-backup manual-$(date +%s)`.

### Восстановление БД

```bash
export RESTIC_REPOSITORY=... RESTIC_PASSWORD=... AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=...
restic snapshots --tag family-budget
restic restore latest --tag family-budget --target ./restore
kubectl -n budget scale deploy/family-budget --replicas=0
kubectl -n budget cp ./restore/work/budget.dump family-budget-db-1:/var/lib/postgresql/data/budget.dump
kubectl -n budget exec family-budget-db-1 -- pg_restore --clean --if-exists --no-owner -d budget /var/lib/postgresql/data/budget.dump
kubectl -n budget scale deploy/family-budget --replicas=1
```

### Полная потеря сервера

1. Новый VDS → шаг 1 (Ansible). Argo CD сам поднимет всё из Git.
2. Vault: init не делать; восстановить снапшот: `restic restore latest --tag vault`, затем `vault operator raft snapshot restore -force vault.snap` и unseal **старыми** ключами.
3. ESO создаст секреты → приложение стартует на пустой БД → восстановить БД (выше).

## 5. Мониторинг

**Сейчас (профиль «для дома», 4 ГБ):**
- liveness/readiness-пробы приложения (`/healthz`, `/readyz`) — k8s сам перезапускает зависший под;
- `kubectl top nodes|pods` — встроенный в k3s metrics-server;
- статус синхронизации и здоровья приложений в Argo CD: `kubectl -n argocd get applications` или UI через `kubectl -n argocd port-forward svc/argo-cd-argocd-server 8080:80`;
- метрики приложения `/metrics` (http_requests_total, латентность) отдаются всегда, их просто никто не собирает.

**Продакшн (готово, закомментировано):** VictoriaMetrics + vmalert + Alertmanager + Grafana (~0,8–1 ГБ RAM), ServiceMonitor приложения, CNPG PodMonitor, алерты `BudgetHighErrorRate`, `BudgetBackupFailed`, `BudgetBackupMissing`. Включение:
1. раскомментировать `deploy/argocd/apps/monitoring.yaml`;
2. `metrics.serviceMonitor: true` в `deploy/helm/family-budget/values-prod.yaml`;
3. push в main — Argo CD поднимет стек. Grafana: `kubectl -n monitoring port-forward svc/monitoring-grafana 3000:80`.

CRD Prometheus Operator ставятся всегда (`prometheus-operator-crds`, без подов), поэтому включение не требует ручных шагов.

## 6. Рост до нескольких узлов

Добавить хосты в `[k3s_agents]` → `ansible-playbook site.yml`. Затем `postgres.cnpg.instances: 2` (реплика на другом узле), для HA control plane — 3 сервера с `cluster-init` и Vault `ha.replicas: 3`. Хранилище `local-path` привязано к узлу: для переносимых томов — Longhorn.
