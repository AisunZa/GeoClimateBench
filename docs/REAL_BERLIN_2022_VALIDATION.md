# Berlin-Tempelhof, July 2022: real-data validation

This case study compares an hourly-sampled ERA5-Land 2-m temperature **grid-cell** daily maximum with a DWD **station** daily maximum `TXK`.

## Prerequisites

Run from the GeoClimateBench project root, with the following files present:

- `data/era5_berlin_2022_07_normalized.nc` (744 UTC hourly timestamps; Kelvin)
- `data/dwd_berlin_2022_07.csv` (imported DWD daily observations)
- `downloads/tageswerte_KL_00433_*_hist.zip` (the original DWD station archive, including metadata)

Command (Windows Anaconda PowerShell):

```powershell
.\.venv\Scripts\python.exe scripts\compare_real_july2022.py
.\.venv\Scripts\python.exe -m pytest -q
```

The script checks that the imported DWD TXK values exactly match the archived DWD measurements, that 31 expected dates are present, and that the `TXK` observation-day metadata for July 2022 is `00:00 - 24:00 UTC gemessen`. It records the DWD `QN_4` quality-code distribution and SHA-256 checksums. It fails if these assumptions do not hold.

## Important scientific interpretation

For station **00433** during **July 2022**, the supplied DWD archive's parameter metadata specifies **00:00–24:00 UTC** for `TXK` (since 2001-04-01). The *intended calendar day* therefore aligns with the ERA5-Land UTC-day aggregation. However, ERA5-Land's computed maximum is the maximum **of the 24 hourly sample values**; the DWD `TXK` maximum can capture different within-hour extrema and observational methods. Station-versus-grid cell representativeness, elevation, and urban-exposure differences remain.

DWD `QN_4 = 9` means *not all parameters corrected* under the DWD report-level quality convention; it is not direct evidence that each TXK observation is inaccurate. Preserve the flags rather than silently discarding them.

The previous experiment found 31 station-day pairs, bias = -1.438°C, MAE = 1.525°C, and RMSE = 1.728°C. These numbers are **user-reported exploratory results from the supplied files**, not independently reproduced results in this upgrade bundle. One station and one month cannot establish general ERA5-Land model performance, and no climate-extremes baseline has yet been applied to this real-data period.

## Files generated

In `results/real_berlin_2022_07/`:

- `daily_max.nc`, `station_pairs.csv`, `metrics.json`
- `station_temperature_comparison.png`
- `real_run_metadata.json` including DWD source QC, validated station observation-day, and input SHA-256 hashes

## References

- DWD daily climate archive: https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/daily/kl/historical/
- DWD quality-control levels: https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/monthly/kl/DESCRIPTION_obsgermany-climate-monthly-kl_en.pdf

We recommend a future independent sensitivity analysis using neighboring grid cells, station altitude, and time sampling before generalizing findings.
