#!/usr/bin/env bash
# Release gate: identical commands are run by GitHub Actions and Jenkins.
# Any non-zero exit blocks the build, image creation and deployment.
set -u
FAIL=0
echo "=== GATE 1: unit + integration + regression tests, coverage >= 90% ==="
python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=90 -q || { echo "GATE 1 FAILED"; FAIL=1; }
echo "=== GATE 2: static security scan (bandit, medium+ severity) ==="
bandit -q -r app -ll || { echo "GATE 2 FAILED"; FAIL=1; }
echo "=== GATE 3: no secrets committed ==="
if git ls-files | grep -E '(^|/)\.env$' ; then echo "GATE 3 FAILED: .env tracked"; FAIL=1; fi
if git grep -nIE '(AKIA[0-9A-Z]{16}|BEGIN (RSA|EC) PRIVATE KEY|password\s*=\s*["'"'"'][^"'"'"']+["'"'"'])' -- . ':!scripts/gate.sh' ; then
  echo "GATE 3 FAILED: secret-like string found"; FAIL=1; fi
if [ "$FAIL" -ne 0 ]; then echo ">>> RELEASE BLOCKED"; exit 1; fi
echo ">>> ALL GATES PASSED - release may proceed to build"
