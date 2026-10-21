# 🌍 GeoClimateBench

**A reproducible Earth Sciences coding benchmark for climate extremes, numerical validation, and agent evaluation.**

[![Scientific validation](https://github.com/AisunZa/GeoClimateBench/actions/workflows/ci.yml/badge.svg)](https://github.com/AisunZa/GeoClimateBench/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)
[![Mode](https://img.shields.io/badge/demo-synthetic%20data-orange)](docs/DATA_SOURCES.md)

## Why this project exists

GeoClimateBench is a GitHub portfolio prototype featuring **three offline scientific programming tasks and a fourth optional real-data validation task**. Each task has a precise contract, an executable reference solution and a local verifier. The aim is to evaluate whether an AI coding agent can handle climate-data units, spatial/temporal integrity, numerical methods, and scientific reporting — **not merely whether it produces a plausible-looking chart**.

This is **not** an official Terminal-Bench/Harbor submission, a secure hidden-test system, or a published climate study. The offline demo is **100% synthetic (NOT ERA5-Land and NOT real DWD observations)**. The code has input adapters for user-obtained real ERA5-Land-style NetCDF and DWD daily observation files; an optional, separately sourced Berlin July 2022 real-data case study and numerical grader are also available (Task 04).

## Harbor Benchmarks — GeoClimateBench v2

GeoClimateBench includes two reproducible scientific coding benchmarks
implemented with Harbor 0.24.0, Docker, and independent numerical verifiers.

| Benchmark | Oracle | Nop | Fault-injection controls |
|---|---:|---:|---:|
| [Daily Temperature QC](benchmarks/daily-max-qc/) | 1.0 | 0.0 | 5/5 passed |
| [Heatwave P90](benchmarks/heatwave-p90/) | 1.0 | 0.0 | 12/12 passed |

### Reproduce the evaluations

From the repository root in Windows Anaconda PowerShell:

```powershell
harbor run -p ".\benchmarks\daily-max-qc" -a oracle
harbor run -p ".\benchmarks\daily-max-qc" -a nop
harbor run -p ".\benchmarks\heatwave-p90" -a oracle
harbor run -p ".\benchmarks\heatwave-p90" -a nop

.\.venv\Scripts\python.exe .\benchmarks\daily-max-qc\fault_injection.py
.\.venv\Scripts\python.exe .\benchmarks\heatwave-p90\fault_injection.py
```

The fault-injection scripts require their corresponding local Docker
verifier images.

### Interpretation and limitations

- All Harbor benchmark datasets are synthetic.
- Verifiers are isolated from agent environments, but their source is public.
- Oracle and Nop runs are controls, not independent AI-agent evaluations.
- Fault injection checks selected scientific errors, not exhaustive correctness.
- No independent AI coding-agent performance results are available yet.

Results verified locally on October 21, 2026.

## Scientific tasks

| Task | Scientific challenge | Key output | Independent verifier |
|---|---|---|---|
| [01 — QC & daily temperature](tasks/task-01-daily-max/instruction.md) | Convert hourly 2m temperature K to sampled daily max °C with QC and minimum completeness | `daily_max.nc` | Units, timestamps, completeness, grids, numerical error |
| [02 — heatwave identification](tasks/task-02-heatwave-detection/instruction.md) | Compute 1991–2020 day-specific p90 using ±7-day calendar windows; detect ≥5 consecutive exceedance days | `heatwaves.nc` | Baseline coverage, percentiles, strict comparisons, runs |
| [03 — station verification](tasks/task-03-station-validation/instruction.md) | Match station TXK-like records to nearest grid cell, apply exclusions, calculate MAE/bias/RMSE | `station_pairs.csv`, `metrics.json` | Geodesic distances, exclusions, statistics, output schema |
| [04 — real-data validation](tasks/task-04-real-berlin-validation/instruction.md) | Compare ERA5-Land and DWD Berlin-Tempelhof temperatures with source QC | Daily maxima, station errors, provenance | Independent numerical and metadata grader |

**Key scientific distinction:** the maximum of 24 hourly instantaneous values is an *hourly-sampled UTC daily maximum*, not necessarily the true daily maximum measured by a station. The comparison is explicitly subject to sampling, exposure, land-surface, and station reporting-period differences.

## Quick start — works OFFLINE after installing dependencies

Requires Python 3.10+ with `pip` (tested here in a Linux-based Python environment). From the repository directory:

```bash
python -m venv .venv
source .venv/bin/activate       # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e '.[dev]'
python -m pytest -q
python -m geoclimatebench demo --data-dir data --output results
```

`demo` automatically creates a reproducible synthetic input dataset, executes all reference solutions, generates two PNG visualizations, and runs numerical verification. It **does not require a CDS API key or internet access**.

Afterward, inspect:

```text
results/
├── daily_max.nc
├── heatwaves.nc
├── station_pairs.csv
├── metrics.json
├── run_metadata.json
├── heatwave_days.png
└── heatwave_timeseries.png
```

Run the stages individually (useful for learning and agent evaluation):

```bash
python -m geoclimatebench solve-task --task 1 --data-dir data --output results
python -m geoclimatebench grade-task --task 1 --data-dir data --output results
python -m geoclimatebench solve-task --task 2 --data-dir data --output results
python -m geoclimatebench grade-task --task 2 --data-dir data --output results
python -m geoclimatebench solve-task --task 3 --data-dir data --output results
python -m geoclimatebench grade-task --task 3 --data-dir data --output results
python -m geoclimatebench grade --data-dir data --output results
```

Alternative: `make demo`, `make test`, `bash scripts/check_all.sh`.

### Run in Docker

```bash
docker build -t geoclimatebench:0.1 .
docker run --rm geoclimatebench:0.1
```

The container runs the tests and offline demo. Its files remain inside the container unless mounted. To save artifacts locally:

```bash
mkdir -p data results
docker run --rm -v "$(pwd)/data:/workspace/data" -v "$(pwd)/results:/workspace/results" geoclimatebench:0.1
```

Docker build/runtime is supplied but may require verification on your own Docker host. The included GitHub Actions workflow runs tests and the demo on multiple Python versions when pushed to GitHub.

## Real ERA5-Land and DWD data (optional / not needed for the demo)

The **data workflow is not a climate study until real datasets and their observational timing differences are checked**. Our demo generator deliberately labels all arrays as synthetic. For real-world inputs:

1. For many NetCDF-4 CDS exports, also install the optional reader first: `python -m pip install -e ".[real]"`. Download **ERA5-Land hourly 2m temperature** (`2m_temperature`, K) from the [Copernicus Climate Data Store](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land), covering a sufficiently populated baseline (1991–2020) and your target month (e.g. July 2022). The baseline threshold for July needs at least June 24–August 7 across baseline years. Download a **small spatial subset** to avoid unexpectedly large files. Account, licence acknowledgement, and data acquisition are your responsibility.
2. Convert simple downloaded NetCDF files to the project schema (variable `t2m`, ascending `latitude`/`longitude`, UTC `time`, Kelvin):

   ```bash
   python -m geoclimatebench era5-normalize --input downloads/year1.nc downloads/year2.nc --output data/era5_hourly_normalized.nc
   ```

3. Download one or more historical **daily KL ZIP archives** from [DWD CDC open data](https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/daily/kl/historical/). Confirm the station's **actual coordinates** from DWD station metadata. Convert each ZIP:

   ```bash
   python -m geoclimatebench dwd-import --archive downloads/station.zip --latitude 52.0 --longitude 13.0 --start 2022-07-01 --end 2022-07-31 --output data/station_one.csv
   ```

   **These lat/lon values are syntax examples only, not real station metadata.** Merge resulting station CSVs, preserving schema and unique station/date pairs.
4. Run the pipeline against correctly normalized, overlapping data:

   ```bash
   python -m geoclimatebench run --hourly data/era5_hourly_normalized.nc --stations data/real_dwd_stations.csv --output real_results --target-year 2022 --target-month 7
   ```

**Important:** the original `grade`/`grade-task` commands use the **synthetic official fixture**; use `scripts/grade_real_july2022.py` for the separate real-input Task 04. Do not use their PASS output as evidence of real-world accuracy. The ERA5 normalizer supports basic NetCDF exports only, not all CDS GRIB/forecast-step variants. DWD reporting-day conventions can differ across station/instrument periods. See [sources and limitations](docs/DATA_SOURCES.md).

## Optional Task 04: independently graded real-data station comparison

After acquiring, normalizing, and validating your July 2022 Berlin ERA5-Land
and DWD input data, you can run a fourth, **optional real-data benchmark task**:

```powershell
.\.venv\Scripts\python.exe scripts\compare_real_july2022.py
.\.venv\Scripts\python.exe scripts\grade_real_july2022.py
```

The real-data verifier recomputes sampled daily maximum temperatures,
station/grid geodesic matching, and error statistics directly from inputs;
it also checks the DWD archive quality flags, observation-day metadata,
and SHA-256 provenance hashes. This is a **transparent local verifier**, not
secure grading of an external AI agent. It is not included in the offline demo
or CI tests because it needs separately acquired ERA5-Land and DWD data.

See [Task 04 instructions](tasks/task-04-real-berlin-validation/instruction.md)
and [grading architecture](docs/TASK04_VALIDATION.md). The included Task 04
unit tests use synthetic mini-fixtures and do not distribute real source data.

## Benchmark layout

```text
GeoClimateBench_v1/
├── geoclimatebench/
│   ├── cli.py              # CLI / reference pipeline
│   ├── fixtures.py         # seeded synthetic scenario
│   ├── science.py          # QC, percentile, heatwave reference methods
│   ├── validation.py       # station pairing, uncertainty metrics
│   ├── dwd.py              # DWD daily KL ZIP parser
│   ├── era5.py             # standard NetCDF normalization
│   ├── evaluate.py         # local numerical grader
│   └── plots.py            # example visualization
├── tasks/                  # four task specifications
├── tests/                  # independent small numerical examples and integration tests
├── docs/                   # methods, provenance, limitations, interview preparation
├── example_results/        # verified precomputed SYNTHETIC example outputs
├── .github/workflows/ci.yml
├── Dockerfile
└── pyproject.toml
```

## Design decisions that make scientific evaluation meaningful

- Explicit Kelvin → Celsius conversion (`−273.15`), never guessed temperature units.
- Missing/invalid values are **masked**, never converted into extreme temperatures.
- UTC timestamps, unique hourly samples, minimum of 18 QC-valid samples per day.
- Climatology from 1991–2020, ±7-day calendar window, strict percentile > comparator.
- At least 300 finite reference observations and 20 different baseline years **per grid cell/day**.
- Heatwave event requires **five consecutive daily threshold exceedances**; all days in a qualifying event are marked.
- Haversine station-grid pairing with maximum 180 km distance, not mislabeled as bilinear interpolation.
- Numerical verifier uses explicit `atol=1e-4`, `rtol=0` and tests scientifically meaningful invariants.
- Regression tests introduce faulty data and confirm wrong answers are rejected.
- Provenance is explicit: no fake observations, no inferred station coordinates, no unpublished claim of performance.

See [scientific methodology](docs/METHODOLOGY.md), [source details](docs/DATA_SOURCES.md), and [limitations](docs/LIMITATIONS.md).

## Reproducibility and contribution integrity

The project is a **portfolio/learning prototype**, built with AI assistance and intended for human scientific review. Before presenting it as personal professional work, run it yourself, review the algorithms and edge cases, commit your own understanding and any improvements, and be prepared to explain methods, assumptions, and test failures. A successful synthetic test is evidence of **software behavior under controlled conditions**, not of meteorological accuracy or independent AI-agent benchmark difficulty.

The MIT licence applies to **original code in this repository**. It does not change the licence of downloaded ERA5-Land or DWD data; check and comply with those data-source terms independently.

## Roadmap and future extensions

- Extend the single-station real ERA5-Land/DWD exploratory case to more locations/months; audit additional station metadata and quality flags.
- Fully isolated agent/verifier container tasks compliant with the chosen benchmark runner's exact format.
- External-agent trials and empirical pass/fail rates to quantify task difficulty.
- Expanded high-coverage dates and event-boundary handling beyond the July prototype.

**Status:** v0.1 prototype plus optional real-data Task 04 (source-derived local grader, real-data provenance/QC). The 3-task synthetic demo remains fully offline; external-agent trials and longer-term real climate-extremes validation are not yet implemented.
