#!/usr/bin/env bash
# Vault starts sealed after a pod/node restart. Unseal with 3 of 5 keys from the password manager.
set -euo pipefail
for i in 1 2 3; do
  read -rsp "unseal key $i: " K; echo
  kubectl -n vault exec -i vault-0 -- env VAULT_ADDR=http://127.0.0.1:8200 vault operator unseal "$K" | grep -E '^Sealed'
done
