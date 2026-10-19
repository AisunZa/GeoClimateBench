# Limitations and honest interpretation

This is a **v0.1 prototype**, not a validated climate science publication or a production-ready AI agent benchmark.

1. **Synthetic proof of behavior:** All bundled sample data and figures are invented fixtures with seeded randomness, *not* authentic ERA5-Land or DWD observations. Demonstrated station skill metrics measure synthetic consistency, not climate-model accuracy.
2. **No independent agent scores:** The public verifier compares against the included reference implementation. No external agent was tested; there is no verified task success rate, difficulty ranking or hidden-test isolation.
3. **Not official Harbor format:** The task prompts are terminal-based contracts but not yet three fully standalone, separate-verifier tasks matching an external framework's exact schema.
4. **Temporal definition:** The maximum of hourly reanalysis temperatures is not the continuous maximum; DWD TXK may use different observation periods or network instrumentation.
5. **Partial baseline:** Synthetic data covers only June 24–August 7 in each baseline year. The current general method supports July use but February 29 is deliberately rejected. Partial-month target data is rejected.
6. **Events at boundaries:** July heatwaves starting in June or continuing into August are left-censored or right-censored and should not be interpreted as fully characterized events.
7. **No formal trend inference:** Percentiles are a fixed historical reference; no physical attribution, bias correction, detrending, adjusted probability model or trend significance is performed.
8. **Missing data policy:** Implausibly extreme readings are masked; no gap-filling. A fixed 18-hour daily acceptance threshold and ≥300 baseline observations are explicit design choices, not universal climatological standards.
9. **Spatial validation:** Haversine nearest-cell matching ignores land mask, orography, elevation, station exposure and coastlines. A 180-km cutoff is generous and may be unacceptable for real validation.
10. **DWD QC:** DWD quality flags and evolving station metadata are not evaluated. Parser uses TXK and its missing sentinel only.
11. **ERA5 input formats:** Only simple hourly NetCDF input with known units and dimensions is supported. Additional formats (GRIB, forecast-step coordinates, Zarr) are not automatically normalized.
12. **Resource requirements:** Full-resolution real Germany-wide 30-year hourly ERA5-Land inputs can be large. Spatial/temporal subsetting and chunked xarray/Dask computation would be needed for scale.
13. **Software environment:** Python tests and the demo were run locally; package dependency ranges are not a fully pinned environment lockfile. The run metadata records core library versions and file checksums; Docker build and all GitHub CI runtime variants must be confirmed after checkout in those environments.
14. **Licence:** MIT covers original repository code only. ERA5/DWD data require compliance with the original providers' licences and attribution.

## Interpretation of the grader result

A status of `PASS` means submitted *synthetic* output satisfies the local scientific contract and canonical tolerances under tested scenarios. It does not guarantee correctness on arbitrarily malformed input, reproduce independent data, or establish skill in real meteorology.
