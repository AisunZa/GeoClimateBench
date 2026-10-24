#!/usr/bin/env bash
set -euo pipefail
cp /solution/solve_station.py /app/solve.py
python /app/solve.py \
    --daily /app/data/daily_max.nc \
    --stations /app/data/stations_synthetic.csv \
    --output-dir /app/results
