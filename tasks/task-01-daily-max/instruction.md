# Task 01 — Data integrity and gridded daily maximum temperature

## Scenario

A climate dataset's `t2m` is sampled hourly, but a downstream analysis requires accurate **UTC daily sampled maxima**. Produce a machine-readable NetCDF result, without silently coercing invalid data or units.

**Input:** `data/hourly_synthetic.nc` (generated using `geoclimatebench demo`); a `t2m(time, latitude, longitude)` NetCDF with ascending coordinates, UTC hourly timestamps and `t2m.units="K"`.

**Required output:** `results/daily_max.nc` with variables:

- `tmax_c(time, latitude, longitude)`, float, in degrees Celsius.
- `hours_valid(time, latitude, longitude)`, integer sample count.

## Scientific requirements

1. Verify sorted, strictly unique exact hourly UTC timestamps; reject incompatible units/coordinates rather than guessing.
2. Mark temperatures missing if nonfinite or outside 180–340 K inclusive.
3. Group by UTC calendar date, *without inserting nonexistent days in unsampled months*.
4. If at least 18 valid hourly samples exist at a cell/day, compute `max(valid t2m) − 273.15`. Otherwise use NaN.
5. Include original latitude/longitude coordinates unchanged, output day coordinate at UTC midnight, and no implicit gap filling.

## Edge cases you must handle

Synthetic sample includes `999 K` (invalid value) and a cell-day with fewer than 18 valid measurements. Values at those locations must not become implausible heatwave readings.

## Agent success criterion

Your output passes a numerical verifier with `atol=1e-4`, `rtol=0`, retaining missing masks, coordinate values and sample counts.

## Local demonstration

```bash
python -m geoclimatebench solve-task --task 1 --data-dir data --output results
python -m geoclimatebench grade-task --task 1 --data-dir data --output results
```

The first command is a **published reference solution**, not a mystery agent; the second reruns the local verifier. To evaluate an external agent, provide the instruction plus inputs and evaluate its separate output. The public repository does not have hidden-test security boundaries.
