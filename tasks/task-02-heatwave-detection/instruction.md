# Task 02 — Baseline percentile climatology and heatwave runs

## Scenario

You receive gridded UTC daily sampled maximum temperature data and must detect extreme-heat events relative to a reproducible 1991–2020 reference climatology. The expected 2022 July result must be robust to calendar-year alignment, missing data, percentile ties and incomplete reference coverage.

**Input:** `results/daily_max.nc` from Task 01.

**Required output:** `results/heatwaves.nc` with:

- 3D `(time, latitude, longitude)`: `threshold_c`, `baseline_samples`, `baseline_years`, `exceedance_day`, `heatwave_day`.
- 2D `(latitude, longitude)`: `event_count`, `heatwave_days`, `max_event_length`.

## Scientific requirements

1. Use **1991–2020 inclusive** as baseline and **July 2022** as target.
2. For each target month/day, pool baseline daily Tmax values across years within ±7 calendar days, inclusive; ignore leap-day offset when comparing July dates. Treat Feb 29 as unsupported rather than silently mishandling it.
3. Require **at least 300 valid baseline samples** and **at least 20 represented baseline years**, for each grid cell and target date. Insufficient coverage gives NaN threshold.
4. Use the 90th percentile (`numpy.nanpercentile`, linear method), independently per day and grid cell. An exceedance requires `Tmax > threshold`, not `>=`.
5. An episode requires **five or more consecutive exceedance days**. Mark all days within each qualifying episode; shorter episodes do not qualify.
6. Export heatwave episode count, number of qualifying days, and longest episode per grid cell. Reject an incomplete target month. Do not interpolate missing dates.

## Edge cases

Leap years, ties at the percentile threshold, missing baseline cells, and breaks in exceedance runs must be correct. The evaluation month truncates episodes at month boundaries; this limitation must be acknowledged.

## Local demonstration

```bash
python -m geoclimatebench solve-task --task 2 --data-dir data --output results
python -m geoclimatebench grade-task --task 2 --data-dir data --output results
```

Task 01 output must exist first; the reference implementation is public and separate from the prompts.
