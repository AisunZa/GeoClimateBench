# GeoClimateBench Harbor benchmark 03 — station-grid-validation

All input station and gridded temperatures are **synthetic**, not ERA5-Land or DWD observations.

This task matches synthetic station observations to the nearest grid cell by
Haversine great-circle distance, rejects matches beyond 180 km, applies explicit
exclusion precedence, and reports untrimmed model-minus-observation errors.
It is an offline scientific programming benchmark, not a real-data climate
validation study or a forecasting skill estimate.

## Windows Anaconda PowerShell (run from repository root)

```powershell
.\.venv\Scripts\python.exe .\benchmarks\station-grid-validation\build_fixture.py

docker build -t geoclimatebench-station-agent .\benchmarks\station-grid-validation\environment
docker build -t geoclimatebench-station-verifier .\benchmarks\station-grid-validation\tests

harbor run -p .\benchmarks\station-grid-validation -a oracle
harbor run -p .\benchmarks\station-grid-validation -a nop
```

The verifier image contains the public, independent `verify.py` and
`regression_cases.py`, *not* the reference solution. The agent image contains
only the synthetic inputs and preinstalled scientific libraries; the Oracle
solution is supplied separately by Harbor. The verifier receives the listed
artifacts (`solve.py`, paired CSV, metrics JSON) and reconstructs expected
pairs and statistics from independently supplied data. It additionally reruns
submitted code on four unseen conforming fixtures, tests 20 invalid-input
cases and checks six deliberately corrupt outcomes.

Expected controls: Oracle reward 1.0, Nop reward 0.0. These expectations must
be confirmed by running Harbor; no Harbor outcome is asserted here.

Do not commit Harbor-generated `jobs/` folders. The independent verifier is
public, transparent, and not intended to be tamperproof.
