# Task 04 — Independent local grading architecture

Task 04 uses `geoclimatebench/realdata_grader.py` and
`scripts/grade_real_july2022.py` to verify the output of
`scripts/compare_real_july2022.py`. The numerical grader **does not call** the
solution's `daily_max_from_hourly` or `compare_stations` functions.

It checks:

- 744 exact input UTC timestamps, Kelvin units, spatial coordinate order
- independently aggregated 31×grid sampled maxima and quality coverage
- original DWD archive TXK, July dates, `QN_4` distribution and 2022 UTC day
- haversine station/grid match and 31 signed station-day residuals
- independent MAE, bias, RMSE, maximum absolute error and exclusions
- correct missing-data/measurement limitations and SHA-256 provenance hashes

The grader is **source-derived**, not a fixed comparison against the
user-reported bias/MAE/RMSE. Its 1e-4 tolerance is explicit. The `tests/` suite
adds corrupted-output regression tests: changing an error, a metric, a
scientific convention, or a source hash must produce FAIL.

### Execute on Windows Anaconda PowerShell

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\compare_real_july2022.py
.\.venv\Scripts\python.exe scripts\grade_real_july2022.py
```

The third command exits with code **0** and prints JSON `status: PASS` on
success, or exits with code **1** with `status: FAIL` on a detected problem.

Optional real DWD/ERA5 input data are **not** distributed with this patch ZIP.
The original three-task offline synthetic demo and its CI pipeline remain
independent of these optional sources.

### Threat model

This is a public, local verifier; it is not protected against deliberately
malicious code with access to the verifier or source files. For actual AI-agent
training/evaluation, isolate an agent workspace and run a trusted verifier in a
separate container/process with its own uncontaminated data. Neither score
statistics nor external-agent pass rates have yet been measured.
