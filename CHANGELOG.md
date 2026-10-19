# Changelog

## Task 04 add-on — October 2026

- Added optional real ERA5-Land / DWD July 2022 task with transparent, numerically independent local verifier.
- Added automated adversarial regression tests for corrupted daily values, residuals, statistics, QC flags, provenance hashes and observation-day assumptions.
- No real observation files included: data acquisition, license acceptance and source authenticity remain user responsibilities.


## 0.1.0 — 2026-10-19

- First fully offline executable synthetic test bench with three connected scientific coding tasks.
- Implemented reference Kelvin temperature preprocessing with UTC and QC requirements.
- Added calendar-aware percentile threshold detection and five-day exceedance episodes.
- Added station-grid haversine matchups, exclusions, uncertainty summary and DWD daily KL ZIP parsing.
- Added basic user-downloaded ERA5-Land NetCDF normalization.
- Added local task-level verifier with numerical comparisons, multiple analytic unit tests and intentional-output-corruption test.
- Added two illustrative figures, Dockerfile, GitHub Actions, and provenance/limitations documentation.

All bundled example results are synthetic; real observational evaluation and secure separated verifiers are not included in this release.
