# Task 04 — Real ERA5-Land / DWD station validation, July 2022

## Scenario for a scientific coding agent

You are given a *user-supplied* ERA5-Land hourly 2-m temperature NetCDF, a DWD
Berlin-Tempelhof station observation CSV, and the **original DWD daily climate
archive ZIP**, all for July 2022. Create a reproducible, scientifically
qualified station-versus-grid comparison. This is a data-processing and
scientific-accuracy benchmark, **not** a weather-forecast benchmark or a climate
trend analysis.

This is an **optional real-data task**. It is intentionally not part of the
three self-contained synthetic offline benchmark tasks: it requires separately
licensed datasets to be obtained by the user.

## Inputs (relative to repo root)

- `data/era5_berlin_2022_07_normalized.nc`: `t2m` (K), dimension order
  `(time, latitude, longitude)`, UTC timestamps, hourly July 2022 grid.
- `data/dwd_berlin_2022_07.csv`: `station_id,date,latitude,longitude,txk_c`.
- `downloads/tageswerte_KL_00433_*_hist.zip`: original DWD archive, including
  station TXK parameter metadata and report-level quality flag `QN_4`.

Input retrieval and normalization occur **before** this task. Never label
synthetic data as ERA5-Land/DWD. Retain source hashes and the original archive.

## Required outputs in `results/real_berlin_2022_07/`

1. `daily_max.nc`: `tmax_c` and `hours_valid`, with UTC daily timestamps and
   original grid coordinates; `tmax_c` units `degC`.
2. `station_pairs.csv`: columns `station_id,date,station_lat,station_lon,grid_lat,grid_lon,distance_km,observed_tmax_c,modeled_tmax_c,error_c`,
   sorted by station ID/date.
3. `metrics.json`: per-station/global counts, **bias, MAE, RMSE and maximum
   absolute error**, exclusion counts and scientifically specific limitations.
4. `real_run_metadata.json`: SHA-256 of all 3 source inputs, QC flag counts,
   documented station observation-day convention, grid-day convention, run
   software versions, and limitations.
5. `station_temperature_comparison.png`: descriptive comparison graphic (not
   numerically scored by the local verifier).

## Exact scientific requirements

- Inputs: hourly 2-m air temperature in K, UTC (do **not** silently infer the
  unit). Only finite 180–340 K samples are valid.
- Output: maximum of **24 hourly sampled values**, converted to °C by
  subtracting 273.15; reject incomplete days rather than fill missing hours.
  This is *not* the maximum of continuous air temperature in each day.
- Cover exactly **2022-07-01 00:00 through 2022-07-31 23:00 UTC**; no duplicate
  times or skipped dates. Days are defined as 00:00–24:00 UTC.
- Verify the station is `00433`, values and dates match original DWD TXK in the
  ZIP; preserve the original archive's `QN_4` quality-control distribution.
- Read **2022-applicable** `TXK` metadata: Berlin-Tempelhof's documented
  observation-day convention is `00:00 - 24:00 UTC gemessen`.
- Match 52.4675 N, 13.4021 E to **one nearest grid cell via haversine great-circle
  distance**, Earth radius 6371.0088 km; reject matches farther than 20 km.
  Do not bilinearly interpolate or make an elevation correction.
- Error = modeled °C **minus** DWD observed °C. Report all 31 dates, with no
  outlier removal; calculate bias = mean(error), MAE = mean(|error|),
  RMSE = sqrt(mean(error²)), max absolute error = max(|error|).
- Explicitly discuss hourly-versus-instrument maxima; station/grid
  representativeness; original `QN_4`; and the one-station/one-month limitation.
  Do **not** claim that different calendar-day windows explain bias for this
  particular station/month: its source metadata confirms a nominal UTC day.

## Local solution and transparent verifier

From the project root, after independently obtaining and processing the data:

```powershell
.\.venv\Scripts\python.exe scripts\compare_real_july2022.py
.\.venv\Scripts\python.exe scripts\grade_real_july2022.py
```

The verifier independently computes daily maxima, nearest grid cell,
station-day pairs, and metrics **from original inputs**, rather than simply
running the solution code. It also verifies metadata/hash consistency. It
compares numeric results at absolute tolerance `1e-4`, `rtol=0`. Its code is
public and runs in the same local environment, so it is **not a secure hidden
benchmark**, isolated grading infrastructure, or proof of agent difficulty.

Typical user-observed preliminary values for the supplied July 2022 case are
bias −1.438°C, MAE 1.525°C, and RMSE 1.728°C. These example numbers are not
hard-coded as the grader's oracle: the source files are recomputed each time.

## Evaluation limitations

A PASS certifies specified *reproducibility and numerical consistency with the
provided sources*. It does not certify dataset authenticity beyond matching
the supplied DWD archive, weather-model accuracy, statistical significance,
or correctness of broad climate conclusions. Running a real baseline-based
heatwave climatology still requires historical data (e.g., 1991–2020).
