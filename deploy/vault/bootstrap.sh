#!/usr/bin/env bash
# One-time Vault initialization after Argo CD has deployed the vault chart.
# Run from the admin laptop with kubectl pointing at the cluster.
#   ./deploy/vault/bootstrap.sh
# Prints unseal keys and root token ONCE: put them into your password manager
# (not on the server, not into Git). Then delete the local file it writes.
set -euo pipefail
NS=vault
POD=vault-0
# v: no stdin (so it never swallows the script's input); vin: stdin passed through (policies via heredoc)
v() { kubectl -n "$NS" exec "$POD" -- env VAULT_ADDR=http://127.0.0.1:8200 ${VAULT_TOKEN:+VAULT_TOKEN=$VAULT_TOKEN} vault "$@" </dev/null; }
vin() { kubectl -n "$NS" exec -i "$POD" -- env VAULT_ADDR=http://127.0.0.1:8200 ${VAULT_TOKEN:+VAULT_TOKEN=$VAULT_TOKEN} vault "$@"; }

# `vault status` exits 2 while sealed: capture the JSON regardless of the exit code
STATUS=$(v status -format=json || true)
if grep -q '"initialized": false' <<<"$STATUS"; then
  umask 077
  v operator init -key-shares=5 -key-threshold=3 -format=json > vault-init.json
  echo ">>> vault-init.json written: move unseal keys + root token to a password manager, then: shred -u vault-init.json"
  for i in 0 1 2; do v operator unseal "$(python3 -c "import json;print(json.load(open('vault-init.json'))['unseal_keys_b64'][$i])")" >/dev/null; done
  VAULT_TOKEN=$(python3 -c "import json;print(json.load(open('vault-init.json'))['root_token'])")
else
  read -rsp "Vault token with admin rights: " VAULT_TOKEN; echo
fi
export VAULT_TOKEN

# capture first: `grep -q` + pipefail would turn an early exit (SIGPIPE) into a false negative
grep -q '^kv/' <<<"$(v secrets list)" || v secrets enable -path=kv kv-v2
grep -q '^kubernetes/' <<<"$(v auth list)" || v auth enable kubernetes
v write auth/kubernetes/config kubernetes_host=https://kubernetes.default.svc

vin policy write external-secrets - <<'POL'
path "kv/data/family-budget/*" { capabilities = ["read"] }
path "kv/metadata/family-budget/*" { capabilities = ["read", "list"] }
POL
vin policy write vault-snapshot - <<'POL'
path "sys/storage/raft/snapshot" { capabilities = ["read"] }
POL
v write auth/kubernetes/role/external-secrets bound_service_account_names=external-secrets \
  bound_service_account_namespaces=external-secrets policies=external-secrets ttl=1h
v write auth/kubernetes/role/vault-snapshot bound_service_account_names=vault-snapshot \
  bound_service_account_namespaces=vault policies=vault-snapshot ttl=15m

if ! v kv get kv/family-budget/app >/dev/null 2>&1; then
  read -rsp "Anthropic API key (empty = AI hints off): " AKEY; echo
  read -rp "Home city regex (e.g. (?i)mycity|мойгород): " HCITY
  v kv put kv/family-budget/app secret_key="$(openssl rand -hex 32)" anthropic_api_key="$AKEY" home_city_regex="${HCITY:-(?i)hometown}" >/dev/null
fi
if ! v kv get kv/family-budget/backup >/dev/null 2>&1; then
  read -rp "restic repository (e.g. s3:https://storage.yandexcloud.net/bucket/budget; empty = skip backups for now): " REPO
fi
if [ -n "${REPO:-}" ]; then
  read -rp "S3 access key id: " AK
  read -rsp "S3 secret key: " SK; echo
  RP=$(openssl rand -base64 32)
  v kv put kv/family-budget/backup restic_repository="$REPO" restic_password="$RP" \
    aws_access_key_id="$AK" aws_secret_access_key="$SK" >/dev/null
  echo ">>> restic password generated: save it to the password manager too (needed for restore without Vault):"
  echo "    $RP"
fi
echo "done. Consider revoking the root token: vault token revoke <root>"
