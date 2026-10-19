"""Local verifier: canonical numerics + invariants + explicit tolerance checks.

A demonstration verifier, not a secure hidden-test service. Reference code ships
in the same public repository; separate verifier containers are future work.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import xarray as xr

from .science import daily_max_from_hourly, compute_extremes
from .validation import compare_stations


class GradingError(AssertionError):
    pass


def _verify_dataset(expected: xr.Dataset, actual: xr.Dataset, name: str, atol: float):
    if not set(expected.data_vars).issubset(actual.data_vars):
        raise GradingError(f"{name}: missing variables {set(expected.data_vars) - set(actual.data_vars)}")
    for dim in expected.sizes:
        if actual.sizes.get(dim) != expected.sizes[dim]:
            raise GradingError(f"{name}: wrong length for {dim}")
        if not np.array_equal(actual[dim].values, expected[dim].values):
            raise GradingError(f"{name}: coordinate {dim} differs")
    for key in expected.data_vars:
        reference = expected[key].values
        result = actual[key].transpose(*expected[key].dims).values
        if np.issubdtype(reference.dtype, np.number):
            if not np.allclose(result, reference, rtol=0.0, atol=atol, equal_nan=True):
                difference = np.abs(result.astype(float) - reference.astype(float))
                finite = difference[np.isfinite(difference)]
                maximum = float(finite.max()) if len(finite) else float("nan")
                raise GradingError(f"{name}.{key}: numerical mismatch (max finite abs diff {maximum})")
        elif not np.array_equal(result, reference):
            raise GradingError(f"{name}.{key} does not match")


def grade(folder: str | Path, data_folder: str | Path, tolerance: float = 1e-4, task: int | None = None) -> dict:
    out = Path(folder)
    data = Path(data_folder)
    if task not in (None, 1, 2, 3):
        raise ValueError("task must be 1, 2, 3, or None")
    checks = []
    with xr.open_dataset(data / "hourly_synthetic.nc", engine="scipy") as hourly:
        expected_daily = daily_max_from_hourly(hourly)
    if task in (None, 1):
        with xr.open_dataset(out / "daily_max.nc", engine="scipy") as actual_daily:
            _verify_dataset(expected_daily, actual_daily, "task-01", tolerance)
        checks.append("task-01 daily_max and hourly completeness")
    if task in (None, 2):
        expected_extremes = compute_extremes(expected_daily)
        with xr.open_dataset(out / "heatwaves.nc", engine="scipy") as actual_extremes:
            _verify_dataset(expected_extremes, actual_extremes, "task-02", tolerance)
            heatwave_flag = actual_extremes.heatwave_day.values.astype(bool)
            exceeds = actual_extremes.exceedance_day.values.astype(bool)
            if np.any(heatwave_flag & ~exceeds):
                raise GradingError("task-02: heatwave day must be an exceedance")
            if not np.array_equal(heatwave_flag.sum(axis=0), actual_extremes.heatwave_days.values):
                raise GradingError("task-02: event-day totals inconsistent")
        checks.append("task-02 percentile baseline and consecutive exceedance events")
    if task in (None, 3):
        station = pd.read_csv(data / "stations_synthetic.csv", dtype={"station_id": str})
        expected_pairs, expected_metrics = compare_stations(expected_daily, station)
        actual_pairs = pd.read_csv(out / "station_pairs.csv", dtype={"station_id": str})
        if list(actual_pairs.columns) != list(expected_pairs.columns) or len(actual_pairs) != len(expected_pairs):
            raise GradingError("task-03: row count or columns differ")
        for column in expected_pairs.columns:
            if column in ("station_id", "date"):
                if not np.array_equal(actual_pairs[column].astype(str).values, expected_pairs[column].astype(str).values):
                    raise GradingError(f"task-03: column {column} differs")
            elif not np.allclose(actual_pairs[column].to_numpy(dtype=float), expected_pairs[column].to_numpy(dtype=float), rtol=0, atol=tolerance):
                raise GradingError(f"task-03: numeric column {column} differs")
        actual_metrics = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
        def recursive_compare(ref, candidate, key="metrics"):
            if isinstance(ref, dict):
                if not isinstance(candidate, dict) or not set(ref).issubset(candidate):
                    raise GradingError(f"{key}: keys differ")
                for subkey in ref:
                    recursive_compare(ref[subkey], candidate[subkey], f"{key}.{subkey}")
            elif isinstance(ref, list):
                if ref != candidate:
                    raise GradingError(f"{key}: list differs")
            elif isinstance(ref, (int, float)) and not isinstance(ref, bool):
                if not isinstance(candidate, (int, float)) or not np.isclose(ref, candidate, atol=tolerance, rtol=0):
                    raise GradingError(f"{key}: value differs")
            elif ref != candidate:
                raise GradingError(f"{key}: value differs")
        recursive_compare(expected_metrics, actual_metrics)
    if task in (None, 3):
        checks.append("task-03 station pairing, exclusions and RMSE / MAE / bias")
    return {"status": "PASS", "passed": len(checks), "checks": checks, "tolerance": tolerance, "fixture": "synthetic"}
