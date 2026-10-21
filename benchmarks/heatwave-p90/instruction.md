# GeoClimateBench: Calendar-window p90 heatwave detection

The file `/app/data/daily_synthetic.nc` is **synthetic** daily maximum air temperature data; it is NOT ERA5-Land or station observations. Implement a new, reusable Python CLI at `/app/solve.py`:

```
python /app/solve.py --input INPUT.nc --output OUTPUT.nc
```

Run it once on the supplied dataset to write `/app/results/heatwaves.nc`. Your solution must work on other conforming datasets, not only the supplied fixture. Use scientific input validation and do not hardcode outputs. You may use Python, NumPy, pandas, SciPy, and xarray preinstalled in the container.

## Input contract

- A NetCDF `tmax_c(time, latitude, longitude)` variable, in that dimension order, with `units="degC"` and global `time_standard="UTC"`.
- Time coordinates are nonempty, strictly increasing, unique **UTC midnight** daily timestamps. Baseline data may omit days and years; do not silently interpolate or fabricate dates. Target month must contain **all 31 dates of July 2022**.
- Geographic coordinates are finite, unique, strictly increasing, and within latitude `[-90, 90]` and longitude `[-180, 180]`.
- Any nonfinite temperature is missing. Valid finite input temperature values are already in Celsius; do not convert Kelvin here.
- The evaluated period is **July 2022**. The baseline period is **1991–2020** (inclusive), and the target year is not part of the baseline.
- Feb 29 in the baseline or target is **unsupported**: reject it rather than mix leap-year and no-leap calendar indices.

## Scientific method

For **each July 2022 date and grid cell independently**:

1. Map calendar month/day to day-of-year in a fixed **365-day** calendar. Select baseline observations from **1991–2020** whose circular calendar distance is at most **7 days** from that target calendar date. This window wraps across Dec 31 / Jan 1 if necessary.
2. Count finite observations in that window as `baseline_samples`, and the number of **distinct baseline years** containing at least one finite observation in that window as `baseline_years`.
3. If `baseline_samples < 300` **or** `baseline_years < 20`, the threshold is missing (NaN). Otherwise compute `threshold_c` as the **90th percentile**, using NumPy's **linear** interpolation convention (`np.percentile(..., 90, method="linear")`).
4. An `exceedance_day` is 1 **only** when both target temperature and threshold are finite and `target_temp > threshold_c` (strictly greater, never `>=`). Otherwise it is 0.
5. A heatwave is a run of **at least 5 consecutive calendar days** with `exceedance_day=1`, separately for each grid cell. Mark **all days** of qualifying runs in `heatwave_day`, including the first day. A date gap would break the run (though the required July target is complete).

## Output contract

Write `/app/results/heatwaves.nc`, a NetCDF containing:

- `threshold_c(time, latitude, longitude)` (float; `units="degC"`)
- `baseline_samples(time, latitude, longitude)` (integer)
- `baseline_years(time, latitude, longitude)` (integer)
- `exceedance_day(time, latitude, longitude)` (0 or 1, integer)
- `heatwave_day(time, latitude, longitude)` (0 or 1, integer)
- `event_count(latitude, longitude)` (integer: number of qualifying runs)
- `heatwave_days(latitude, longitude)` (integer: number of days in qualifying runs)
- `max_event_length(latitude, longitude)` (integer: longest qualifying run, 0 if none)

The output `time` coordinate must contain exactly 2022-07-01 through 2022-07-31 at UTC midnight, and preserve input latitude/longitude exactly. Include global metadata:

- `baseline_period="1991-2020"`
- `target_period="2022-07"`
- `percentile=90`
- `window_days_each_side=7`
- `minimum_baseline_samples=300`
- `minimum_baseline_years=20`
- `min_consecutive_exceedance_days=5`
- `comparison="strict_gt"`

Numerical tolerance: absolute `1e-4`, relative `0`. A separate verifier checks the supplied output and **reruns your submitted source** on previously unseen test inputs. The agent container does not include a solution or verifier implementation.
