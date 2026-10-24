#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier
if python /tests/verify.py > /logs/verifier/checks.log 2>&1; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
cat /logs/verifier/checks.log
