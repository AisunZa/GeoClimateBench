#!/usr/bin/env bash
set -euo pipefail
cp /solution/solve_daily.py /app/solve.py
python /app/solve.py --input /app/data/hourly_synthetic.nc --output /app/results/daily_max.nc
