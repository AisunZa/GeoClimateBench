# GeoClimateBench Harbor benchmark 02 — heatwave-p90

**All data are synthetic.** Independent, offline scientific coding benchmark for
1991–2020 ±7-day calendar-window 90th percentile thresholds, per-cell baseline
coverage, strict exceedance, and >=5-consecutive-day heatwave events.

## Run from the repository root (Windows Anaconda PowerShell)

```powershell
docker build -t geoclimatebench-heatwave-agent .\benchmarks\heatwave-p90\environment
docker build -t geoclimatebench-heatwave-verifier .\benchmarks\heatwave-p90\tests
harbor run -p .\benchmarks\heatwave-p90 -a oracle
harbor run -p .\benchmarks\heatwave-p90 -a nop
.\.venv\Scripts\python.exe .\benchmarks\heatwave-p90\fault_injection.py
```

Verified locally on October 21, 2026: Oracle reward **1.0** (1/1 trials, zero errors); Nop reward **0.0** (zero exceptions). The Heatwave fault-injection suite passed **12/12** controls. Scientific verifier calculates its own thresholds
and events without importing reference solution code. The submitted code is
rerun against unseen synthetic fixtures and invalid-input tests. This is a public
portfolio repository and not a tamperproof or confidential hidden-test service.

The task matches the core method in `geoclimatebench/science.py`, without reading
that code in the benchmark agent or verifier image. Generate fixtures again with
`python benchmarks/heatwave-p90/build_fixture.py` (requires NumPy/pandas/xarray/SciPy).
