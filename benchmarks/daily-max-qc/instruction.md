# GeoClimateBench: Hourly temperature QC and UTC daily maxima

You are given a **synthetic** hourly gridded 2-m temperature NetCDF file
at `/app/data/hourly_synthetic.nc`. It is **not** real ERA5-Land data.

Develop an original reusable Python program at **`/app/solve.py`**.
It must implement the CLI:

```
python /app/solve.py --input INPUT.nc --output OUTPUT.nc
```

After writing it, execute it to produce `/app/results/daily_max.nc`.
The program must also work on previously unseen NetCDF files that follow the
same input specification. Do **not** hardcode the supplied input's results.

## Scientific contract

1. The input is a NetCDF dataset with `t2m(time, latitude, longitude)`
   in that precise dimension order. Its temperature `units` must be `K`,
   `kelvin`, or `Kelvin`, and its global `time_standard` must be `UTC`.
2. Require time, latitude, and longitude coordinates. Time coordinates must
   be nonempty, strictly increasing, unique, and located exactly on the hour
   (UTC; minute, second, and subsecond zero). Reject duplicate/unsorted or
   subhourly observations. Missing hours and missing whole days are allowed.
3. Latitude/longitude must be finite, within [-90,90]/[-180,180], and
   strictly increasing. Reject reversed or duplicate coordinates.
4. An hourly temperature is valid only when finite and within **180–340 K**
   (inclusive). Exclude other samples from both maxima and counts.
5. Group samples by **UTC calendar day**, separately for each grid cell.
6. `hours_valid` is the integer number of valid samples in that cell/day.
   Its metadata unit must be the dimensionless count `"1"` (not `"hours"`).
7. A cell/day with >= 18 valid samples receives the sampled maximum
   temperature minus **273.15**, in degrees Celsius. With < 18 samples,
   `tmax_c` must be NaN; keep the actual valid-hour count.
8. Produce a NetCDF file with two variables,
   `tmax_c(time, latitude, longitude)` and
   `hours_valid(time, latitude, longitude)`.
   Set `tmax_c` metadata `units="degC"` and the global output
   `time_standard="UTC"`. The `time` coordinate is UTC midnight for
   each **observed** calendar day; do not insert absent dates or interpolate.
   Preserve input spatial coordinates.

For all numeric temperatures, use **absolute tolerance 1e-4**, relative
 tolerance 0. This benchmark's maxima are maxima of hourly samples,
not continuous-time daily station extrema.

The verifier also runs your submitted `/app/solve.py` on independently
created input datasets and checks invalid-input handling. Only the input
and task instructions are in your initial container; reference solutions
and verifier source are not installed in it.
