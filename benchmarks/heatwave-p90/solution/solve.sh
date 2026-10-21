#!/usr/bin/env bash
set -euo pipefail
cp /solution/solve_heatwaves.py /app/solve.py
python /app/solve.py --input /app/data/daily_synthetic.nc --output /app/results/heatwaves.nc
