# GeoClimateBench: Station-grid validation

## Objective

Implement a reusable Python program to compare synthetic
station daily maximum temperatures with gridded daily
maximum temperatures.

The data are synthetic, not ERA5-Land or DWD observations.

Create `/app/solve.py` with this CLI:

    python /app/solve.py --daily INPUT.nc --stations INPUT.csv --output-dir OUTPUT_DIRECTORY

Run the program on:

- `/app/data/daily_max.nc`
- `/app/data/stations_synthetic.csv`

Write:

- `/app/results/station_pairs.csv`
- `/app/results/metrics.json`

The program must also process previously unseen conforming inputs.
Do not hardcode supplied fixture results.

## NetCDF input

Require:

- `tmax_c(time, latitude, longitude)` in exactly this order.
- Temperature variable attribute `units="degC"`.
- Dataset attribute `time_standard="UTC"`.
- Nonempty, unique, strictly increasing UTC midnight dates.
- One-dimensional latitude and longitude coordinates.
- Finite, strictly increasing, unique geographic coordinates.
- Latitude within [-90, 90].
- Longitude within [-180, 180].

Missing days are permitted. Do not interpolate missing dates.
Nonfinite model temperatures are missing.

## Station CSV input

Required columns, in this order:

    station_id,date,latitude,longitude,txk_c

Require:

- At least one station record.
- Nonempty station identifiers.
- Dates in YYYY-MM-DD format.
- Finite geographic coordinates within valid bounds.
- Constant coordinates for each station identifier.
- No duplicate (station_id, date) records.

Reject invalid station identifiers, dates, coordinates,
duplicate station/date records, and inconsistent positions.

Missing or nonfinite txk_c values are observation exclusions,
not reasons to reject the entire CSV.

## Spatial matching

For each station, select the geographically nearest grid cell
using Haversine great-circle distance.

Use spherical Earth radius 6371.0088 km.

Search all grid cells, not independent nearest coordinates.
For equal distances, choose the first cell in latitude-major,
then longitude-major index order.

No interpolation, elevation correction, or gap filling.

Exclude matches with distance strictly greater than 180 km.
Exactly 180 km is allowed.

If the nearest cell has missing model data, exclude that
record rather than selecting another cell.

## Exclusion precedence

Validate the complete input structure before processing rows.

For each station observation, apply these checks in order.
Assign exactly one exclusion reason:

1. missing_observation:
   txk_c is missing, nonfinite, <= -999, < -80, or > 65.

2. outside_grid:
   nearest great-circle distance is greater than 180 km.

3. unavailable_date:
   the observation date is absent from the NetCDF time axis.

4. missing_grid:
   the selected model temperature is nonfinite.

All remaining records become valid station-grid pairs.

Do not remove valid high-error observations as outliers.

## Pair output

Write `station_pairs.csv` with exactly these columns:

    station_id
    date
    station_lat
    station_lon
    grid_lat
    grid_lon
    distance_km
    observed_tmax_c
    modeled_tmax_c
    error_c

The CSV header must use these names and this order.

Use YYYY-MM-DD dates and ascending (station_id, date)
ordering, independent of input row ordering.

Error is always modeled_tmax_c minus observed_tmax_c.

Preserve numerical values with sufficient precision
for absolute tolerance 1e-4 and relative tolerance 0.

Write a header-only CSV when there are no valid pairs.

## Metrics JSON

Write `metrics.json` containing:

- comparison
- grid_matching
- max_distance_km
- all_stations
- n_input_rows
- n_excluded
- overall
- by_station
- limitations

Required metadata:

comparison = "modeled_tmax_c - observed_tmax_c"

grid_matching =
"nearest great-circle (haversine) cell; no interpolation"

max_distance_km = 180.0

all_stations must contain every input station identifier,
sorted alphabetically, including zero-match stations.

n_input_rows is the number of station CSV data rows.

n_excluded must contain integer counts for:

- missing_observation
- outside_grid
- unavailable_date
- missing_grid

Require:

    n_input_rows = n_valid_pairs + sum(n_excluded.values())

Both overall and every by_station entry must contain:

- n_pairs
- bias_c
- mae_c
- rmse_c
- max_abs_error_c

Let e = modeled temperature minus observed temperature.

bias_c = mean(e)
mae_c = mean(abs(e))
rmse_c = sqrt(mean(e ** 2))
max_abs_error_c = max(abs(e))

Use all valid pairs, without outlier filtering.

Every input station must have a by_station entry.

For a station with zero valid pairs, set n_pairs=0
and all four numerical statistics to JSON null.

Apply the same null convention to overall statistics
when no valid pairs exist.

The limitations field must be a nonempty list of strings
explaining scientific interpretation limitations.

## Invalid input handling

Reject malformed or scientifically invalid input structures
with a nonzero process exit status.

Do not silently repair duplicate records, invalid geographic
coordinates, inconsistent station positions, or malformed dates.

## Scientific interpretation

Hourly-sampled UTC daily maxima and station daily TXK
may use different observation and reporting windows.

Grid-cell and point-station temperatures may also differ
because of elevation, exposure, and spatial representativeness.

Synthetic input statistics are tests of algorithmic behavior,
not evidence of real observational accuracy or forecast skill.

## Independent verification

The verifier independently reconstructs expected results
from input data without importing the submitted program.

It checks the supplied output, unseen conforming fixtures,
scientific edge cases, and invalid-input rejection.

The verifier is public and separate from the agent environment,
not a secure secret-test system.
