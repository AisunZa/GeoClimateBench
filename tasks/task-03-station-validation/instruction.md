# Task 03 — Station–grid comparison, exclusions and uncertainty metrics

## Scenario

Evaluate gridded temperature predictions against daily station-like maximum temperature records. Produce auditable station matchups and metrics without deleting inconvenient high-error observations.

**Inputs:** `results/daily_max.nc` from Task 01; `data/stations_synthetic.csv` containing `station_id,date,latitude,longitude,txk_c` (synthetic, not DWD observations).

**Required outputs:** `results/station_pairs.csv`, `results/metrics.json`.

## Scientific requirements

1. Reject duplicate `(station_id,date)` pairs and stations with inconsistent positions. Verify valid geographic coordinates.
2. Match station to the nearest cell using haversine great-circle distance (mean Earth radius 6371.0088 km), excluding distances **greater than 180 km**. Preserve the actual distance, model grid coordinates and station coordinates.
3. Exclude clearly identified invalid/missing observations (`-999`, NaN, below −80°C, above 65°C), absent model dates and missing model values. Report exclusion counts for each reason.
4. Compute error as `modelled − observed` in °C, with **bias**, **MAE**, **RMSE**, **maximum absolute error** and `n_pairs` globally and per station. Never remove outliers merely because the resulting statistics are worse.
5. Store pairs in deterministic `(station_id,date)` sort order and full summary metadata with explicit scientific limits. All 5 original synthetic station IDs should be reported, even when a station has no valid matchup.

## Scientific caution

Max sampled hourly UTC reanalysis temperatures and observed station TXK are not necessarily defined over the same clock window and are not directly identical physical representational quantities. Neither synthetic data nor unadjusted nearest-neighbor RMSE is evidence of real ERA5-Land forecast skill.

## Local demonstration

```bash
python -m geoclimatebench solve-task --task 3 --data-dir data --output results
python -m geoclimatebench grade-task --task 3 --data-dir data --output results
```

Task 01 output must exist first. For true external-agent evaluation, keep the verifier independent of the agent runtime; this repository's local verifier is transparent, not hidden.
