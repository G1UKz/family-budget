#!/usr/bin/env bash
# Fails if anything that looks like real financial/private data is tracked by git.
set -euo pipefail
bad=0
files=$(git ls-files)
if echo "$files" | grep -E '\.pdf$' | grep -v '^backend/tests/fixtures/vtb_synthetic\.pdf$'; then
  echo "::error::PDF files other than the synthetic fixture are tracked"; bad=1; fi
if echo "$files" | grep -E '(^|/)(journal|rules|overrides|trips)\.csv$|\.dump$|(^|/)\.env$|kubeconfig|vault-init\.json'; then
  echo "::error::private data file is tracked"; bad=1; fi
# 20-digit Russian account numbers and 16-digit card numbers
if git grep -nIE '\b(408|423|302)[0-9]{17}\b|\b[2-6][0-9]{15}\b' -- ':!*.lock' ':!*package-lock.json'; then
  echo "::error::account/card-like number found"; bad=1; fi
exit $bad
