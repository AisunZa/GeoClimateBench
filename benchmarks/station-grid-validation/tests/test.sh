#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier

if {
    test -f /app/solve.py &&
    test -f /app/results/station_pairs.csv &&
    test -f /app/results/metrics.json &&
    python /tests/verify.py \
        --daily /tests/data/daily_max.nc \
        --stations /tests/data/stations_synthetic.csv \
        --pairs /app/results/station_pairs.csv \
        --metrics /app/results/metrics.json &&
    python /tests/regression_cases.py \
        --solver /app/solve.py \
        --verifier /tests/verify.py \
        --workers 2
} > /logs/verifier/checks.log 2>&1; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
cat /logs/verifier/checks.log
