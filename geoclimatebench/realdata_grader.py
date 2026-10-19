"""Numerically independent local grader for optional real-data Berlin task 04.

Unlike scripts/compare_real_july2022.py, the oracle does *not* invoke the
application's daily_max_from_hourly or compare_stations reference algorithms.
It independently recomputes day-wise maxima, great-circle matching and error
metrics from original inputs. The provenance parser is shared intentionally.

This is a transparent local portfolio verifier, not a secured agent sandbox.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from .realdata_qc import verified_berlin_july2022


class RealDataGradingError(ValueError):
    """A scientific result or required provenance check failed."""


def _require(condition: bool, msg: str) -> None:
    if not condition:
        raise RealDataGradingError(msg)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _read_json(path: Path) -> dict:
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        _require(isinstance(result, dict), f"{path.name}: expected JSON object")
        return result
    except (OSError, ValueError) as ex:
        raise RealDataGradingError(f"Cannot read {path.name}: {ex}") from ex


def _is_close(got: float, ref: float, label: str, tolerance: float) -> None:
    try:
        actual = float(got)
    except (TypeError, ValueError) as ex:
        raise RealDataGradingError(f"{label}: non-numeric result") from ex
    _require(np.isfinite(actual) and np.isclose(actual, ref, rtol=0, atol=tolerance),
             f"{label}: expected {ref:.8f}, found {actual:.8f}")


def _oracle(hourly: Path, station_csv: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, pd.DataFrame, dict]:
    """Compute source-derived answers directly with NumPy, not application code."""
    with xr.open_dataset(hourly) as ds:
        _require(set(ds.dims) == {"time", "latitude", "longitude"},
                 "Input ERA5: unsupported dimension set")
        _require(ds["t2m"].dims == ("time", "latitude", "longitude"),
                 "Input ERA5: expected time/latitude/longitude temperature order")
        _require(ds.attrs.get("time_standard") == "UTC" and ds.t2m.attrs.get("units") == "K",
                 "Input ERA5: UTC and Kelvin must be explicit")
        times = pd.DatetimeIndex(ds.time.values)
        expected = pd.date_range("2022-07-01 00:00:00", periods=744, freq="h")
        _require(times.equals(expected), "Input ERA5: requires exactly 744 UTC hourly values")
        lat = np.asarray(ds.latitude.values, dtype="float64")
        lon = np.asarray(ds.longitude.values, dtype="float64")
        _require(lat.ndim == 1 and lon.ndim == 1 and len(lat) and len(lon),
                 "Input ERA5: invalid spatial axes")
        _require(np.all(np.diff(lat) > 0) and np.all(np.diff(lon) > 0),
                 "Input ERA5: spatial axes must increase")
        temperatures = np.asarray(ds.t2m.values, dtype="float64")

    valid = np.isfinite(temperatures) & (temperatures >= 180) & (temperatures <= 340)
    sample_counts = valid.reshape(31, 24, len(lat), len(lon)).sum(axis=1).astype("int16")
    clean = np.where(valid, temperatures, np.nan).reshape(31, 24, len(lat), len(lon))
    # Explicit no-warning all-NaN handling, independent of xarray aggregation.
    safe = np.where(np.isfinite(clean), clean, -np.inf)
    maximum_k = safe.max(axis=1)
    maximum_k[~np.isfinite(maximum_k)] = np.nan
    daily_c = (maximum_k - 273.15).astype("float32")
    daily_c[sample_counts < 24] = np.nan

    obs = pd.read_csv(station_csv, dtype={"station_id": str})
    expected_cols = {"station_id", "date", "latitude", "longitude", "txk_c"}
    _require(expected_cols.issubset(obs.columns), "Station CSV: missing required columns")
    _require(len(obs) == 31 and obs.station_id.eq("00433").all(),
             "Station CSV: exactly 31 records for station 00433 required")
    obs = obs.copy()
    obs["date"] = pd.to_datetime(obs["date"], errors="raise")
    obs = obs.sort_values("date").reset_index(drop=True)
    _require(pd.DatetimeIndex(obs["date"]).equals(
        pd.date_range("2022-07-01", periods=31, freq="D")),
        "Station CSV: 31 unique and consecutive July dates required")
    for field in ("latitude", "longitude", "txk_c"):
        obs[field] = pd.to_numeric(obs[field], errors="raise")
    _require(obs[["latitude", "longitude", "txk_c"]].notna().all().all(),
             "Station CSV: missing required values")
    _require(obs.latitude.nunique() == obs.longitude.nunique() == 1,
             "Station CSV: station coordinates cannot change")
    _require(obs.txk_c.between(-80, 65).all(), "Station CSV: invalid TXK value")

    # Haversine matching implemented here independently of app validation.py.
    station_lat, station_lon = float(obs.latitude.iloc[0]), float(obs.longitude.iloc[0])
    grid_lat, grid_lon = np.meshgrid(lat, lon, indexing="ij")
    lat_delta = np.radians(grid_lat - station_lat)
    lon_delta = np.radians(grid_lon - station_lon)
    term = (np.sin(lat_delta / 2) ** 2
            + np.cos(np.radians(station_lat)) * np.cos(np.radians(grid_lat))
            * np.sin(lon_delta / 2) ** 2)
    distances = 6371.0088 * 2 * np.arcsin(np.sqrt(np.clip(term, 0, 1)))
    i, j = np.unravel_index(int(np.argmin(distances)), distances.shape)
    distance = float(distances[i, j])
    _require(distance <= 20.0, "Station is farther than the 20 km matching limit")
    model = daily_c[:, i, j].astype("float64")
    _require(np.isfinite(model).all(), "Not all 31 grid-cell days have 24 valid hours")
    errors = model - obs.txk_c.to_numpy(dtype="float64")
    rows = pd.DataFrame({
        "station_id": ["00433"] * 31,
        "date": obs.date.dt.strftime("%Y-%m-%d"),
        "station_lat": [station_lat] * 31,
        "station_lon": [station_lon] * 31,
        "grid_lat": [float(lat[i])] * 31,
        "grid_lon": [float(lon[j])] * 31,
        "distance_km": [round(distance, 6)] * 31,
        "observed_tmax_c": obs.txk_c.to_numpy(dtype="float64"),
        "modeled_tmax_c": model,
        "error_c": errors,
    })
    summary = {
        "n_pairs": 31,
        "bias_c": float(np.mean(errors)),
        "mae_c": float(np.mean(np.abs(errors))),
        "rmse_c": float(np.sqrt(np.mean(errors * errors))),
        "max_abs_error_c": float(np.max(np.abs(errors))),
    }
    return lat, lon, daily_c, sample_counts, rows, summary


def grade_real_berlin(
    *,
    hourly: str | Path = "data/era5_berlin_2022_07_normalized.nc",
    stations: str | Path = "data/dwd_berlin_2022_07.csv",
    archive: str | Path,
    output: str | Path = "results/real_berlin_2022_07",
    tolerance: float = 1e-4,
) -> dict:
    """Grade task 04 from immutable-ish source files and submitted artifact files.

    Tolerance is absolute and in scientific output units (°C/km). No silent
    acceptance of NaN/inf. Not a secure grader against malicious candidate code.
    """
    hourly, stations, archive, output = map(Path, (hourly, stations, archive, output))
    _require(np.isfinite(tolerance) and 0 < tolerance <= 1e-3,
             "Tolerance must be finite, positive and <= 1e-3")
    for path in (hourly, stations, archive):
        _require(path.is_file(), f"Missing source file: {path}")
    for name in ("daily_max.nc", "station_pairs.csv", "metrics.json", "real_run_metadata.json"):
        _require((output / name).is_file(), f"Missing submitted output: {output / name}")
    # Validate source DWD archive and TXK measurement-day convention with the
    # existing independent-of-solution archive-level QC parser.
    source_qc = verified_berlin_july2022(archive, stations)
    lat, lon, daily_c, valid_hours, expected_pairs, expected_summary = _oracle(hourly, stations)
    checks: list[str] = []
    with xr.open_dataset(output / "daily_max.nc") as actual:
        _require("tmax_c" in actual and "hours_valid" in actual,
                 "daily_max.nc: missing outputs")
        _require(actual.tmax_c.dims == ("time", "latitude", "longitude"),
                 "daily_max.nc: unexpected tmax dimensions")
        _require(actual.tmax_c.attrs.get("units") == "degC",
                 "daily_max.nc: temperature output must be degC")
        _require(np.array_equal(actual.latitude.values, lat)
                 and np.array_equal(actual.longitude.values, lon),
                 "daily_max.nc: grid coordinate mismatch")
        _require(pd.DatetimeIndex(actual.time.values).equals(
            pd.date_range("2022-07-01", periods=31, freq="D")),
            "daily_max.nc: incorrect daily UTC timestamps")
        candidate = np.asarray(actual.tmax_c.values, dtype="float64")
        _require(candidate.shape == daily_c.shape, "daily_max.nc: incorrect temperature shape")
        _require(np.allclose(candidate, daily_c, atol=tolerance, rtol=0, equal_nan=True),
                 "daily_max.nc: incorrect sampled daily maxima")
        _require(actual.hours_valid.dims == ("time", "latitude", "longitude"),
                 "daily_max.nc: invalid valid-hours dimensions")
        _require(np.array_equal(actual.hours_valid.values, valid_hours),
                 "daily_max.nc: incorrect valid-hour counts")
    checks.append("31 daily UTC maxima, Kelvin conversion, grid and 24-hour counts")

    pairs = pd.read_csv(output / "station_pairs.csv", dtype={"station_id": str})
    _require(list(pairs.columns) == list(expected_pairs.columns),
             "station_pairs.csv: incorrect column order or schema")
    _require(len(pairs) == 31, "station_pairs.csv: expected 31 records")
    for key in ("date", "station_id"):
        _require(pairs[key].astype(str).tolist() == expected_pairs[key].astype(str).tolist(),
                 f"station_pairs.csv: incorrect {key} values/order")
    for key in expected_pairs.columns.difference(["date", "station_id"]):
        vals = pd.to_numeric(pairs[key], errors="coerce").to_numpy(dtype="float64")
        _require(np.isfinite(vals).all(), f"station_pairs.csv: invalid numeric values in {key}")
        _require(np.allclose(vals, expected_pairs[key].values, rtol=0, atol=tolerance),
                 f"station_pairs.csv: incorrect {key}")
    checks.append("31 independent haversine station/grid pairings and signed residuals")

    metrics = _read_json(output / "metrics.json")
    _require(metrics.get("comparison") == "modeled_tmax_c - observed_tmax_c",
             "metrics.json: error sign convention invalid")
    _require(metrics.get("n_input_rows") == 31 and metrics.get("all_stations") == ["00433"],
             "metrics.json: missing station or input count")
    _require(metrics.get("max_distance_km") == 20.0,
             "metrics.json: wrong spatial match limit")
    excluded = metrics.get("n_excluded", {})
    _require(isinstance(excluded, dict) and
             set(excluded) == {"missing_grid", "missing_observation", "outside_grid", "unavailable_date"}
             and all(excluded[k] == 0 for k in excluded),
             "metrics.json: incorrect exclusion counts")
    for where in ("overall", "by_station"):
        block = metrics.get(where, {})
        if where == "by_station":
            _require(set(block) == {"00433"}, "metrics.json: incorrect per-station keys")
            block = block["00433"]
        _require(isinstance(block, dict), f"metrics.json: invalid {where} block")
        for name, value in expected_summary.items():
            if name == "n_pairs":
                _require(block.get(name) == value, f"metrics.json: incorrect {where}.{name}")
            else:
                _is_close(block.get(name), value, f"metrics.json:{where}.{name}", tolerance)
    limitations = metrics.get("limitations")
    _require(isinstance(limitations, list) and len(limitations) >= 4,
             "metrics.json: missing scientific limitations")
    note = " ".join(map(str, limitations)).lower()
    _require("hourly" in note and "grid" in note and "qn_4" in note,
             "metrics.json: must document hourly sampling, grid vs. station, and QN_4")
    _require("not guaranteed to match the dwd" not in note
             and "synthetic demo observations" not in note,
             "metrics.json: contains outdated scientific limitation")
    checks.append("bias, MAE, RMSE, maximum error, exclusions and interpretive limits")

    meta = _read_json(output / "real_run_metadata.json")
    source = meta.get("datasets") or {}
    for name, path in (("hourly_sha256", hourly), ("stations_sha256", stations),
                       ("original_dwd_archive_sha256", archive)):
        _require(source.get(name) == _sha256(path),
                 f"real_run_metadata.json: incorrect {name}")
    observed_qc = meta.get("dwd_source_checks") or {}
    _require(observed_qc.get("qn_4_counts") == source_qc["qn_4_counts"],
             "real_run_metadata.json: QN_4 counts mismatch")
    _require(observed_qc.get("txk_measurement_window") == source_qc["txk_measurement_window"]
             and observed_qc.get("txk_measurement_window_utc_aligned") is True,
             "real_run_metadata.json: DWD observation-day mismatch")
    _require(meta.get("n_paired_station_days") == 31,
             "real_run_metadata.json: wrong paired-day count")
    _require(meta.get("minimum_valid_hours_per_cell_day") == int(valid_hours.min()),
             "real_run_metadata.json: erroneous coverage statistic")
    checks.append("original archive TXK/QN_4 checks, UTC convention, provenance hashes")
    return {
        "status": "PASS", "task_id": 4,
        "checks_passed": len(checks), "checks": checks,
        "n_station_days": 31, "tolerance": tolerance,
        "data_type": "User-supplied inputs: DWD archive consistency verified, external authenticity not established",
    }
