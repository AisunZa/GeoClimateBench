"""Independent verifier: derives expected results without importing solution code.

Runs agent-submitted source against a fixed provided case and hidden fixtures.
The grade rewards correctness only; this is not a malicious-code-proof sandbox.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

SCRIPT = Path("/app/solve.py")
SUBMITTED_OUTPUT = Path("/app/results/daily_max.nc")
PUBLIC_INPUT = Path("/tests/data/hourly_synthetic.nc")


def must(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def oracle_array(input_ds: xr.Dataset):
    """Independent NumPy loop, intentionally not using the solution's groupby."""
    t = pd.DatetimeIndex(input_ds.time.values)
    day = t.normalize()
    unique = day.unique()
    raw = np.asarray(input_ds.t2m.values, dtype=np.float64)
    shape = (len(unique), len(input_ds.latitude), len(input_ds.longitude))
    count = np.zeros(shape, dtype=np.int16)
    temp = np.full(shape, np.nan, dtype=np.float64)
    for k, d in enumerate(unique):
        part = raw[np.asarray(day == d)]
        good = np.isfinite(part) & (part >= 180) & (part <= 340)
        count[k] = good.sum(axis=0)
        cleaned = np.where(good, part, -np.inf)
        max_kelvin = cleaned.max(axis=0)
        temp[k] = np.where(count[k] >= 18, max_kelvin - 273.15, np.nan)
    return unique.to_numpy(dtype="datetime64[ns]"), count, temp


def inspect_result(output: Path, source: Path, label: str):
    must(output.is_file(), f"{label}: missing result NetCDF")
    with xr.open_dataset(source) as inp, xr.open_dataset(output) as out:
        must(set(out.data_vars) >= {"tmax_c", "hours_valid"}, f"{label}: missing variables")
        for key in ("tmax_c", "hours_valid"):
            must(out[key].dims == ("time", "latitude", "longitude"), f"{label}: {key} dimension order")
        must(out.attrs.get("time_standard") == "UTC", f"{label}: expected UTC output metadata")
        must(out.tmax_c.attrs.get("units") == "degC", f"{label}: temperature unit metadata")
        must(out.hours_valid.attrs.get("units") == "1", f"{label}: counts must have dimensionless units")
        must(out.hours_valid.dtype.kind in "iu", f"{label}: counts are not integer")
        expected_days, expected_counts, expected_temp = oracle_array(inp)
        must(np.array_equal(out.time.values.astype('datetime64[ns]'), expected_days), f"{label}: day axis")
        for axis in ("latitude", "longitude"):
            must(np.array_equal(out[axis].values, inp[axis].values), f"{label}: {axis} coordinates")
        must(np.array_equal(out.hours_valid.values, expected_counts), f"{label}: valid-hour counts")
        got = np.asarray(out.tmax_c.values, dtype=np.float64)
        must(got.shape == expected_temp.shape, f"{label}: temperature shape")
        must(np.allclose(got, expected_temp, rtol=0, atol=1e-4, equal_nan=True),
             f"{label}: Celsius maxima, coverage, or exclusions incorrect")


def make_input(path: Path, *, invalid: str | None = None, sparse: bool = False):
    days = pd.date_range("2022-07-01", periods=48, freq="h")
    values = np.full((48, 2, 1), 280.0, dtype=np.float64)
    values[8, 0, 0] = 999.0   # excluded; day 1 has 23 hours in cell 0
    values[24:31, 0, 0] = np.nan  # day 2 has 17 hours in cell 0
    values[10, 1, 0] = 300.0
    values[31, 1, 0] = 294.0
    if sparse:
        days = days + pd.Timedelta(days=10)
        # Deliberately remove a whole day between two observed days.
        second = pd.date_range("2022-07-20", periods=24, freq="h")
        days = days[:24].append(second)
    if invalid == "duplicate":
        days = pd.DatetimeIndex([days[0], *days[:-1]])
    if invalid == "non-hour":
        days = days + pd.Timedelta(minutes=1)
    lat = [52.4, 52.5] if invalid != "reversed_lat" else [52.5, 52.4]
    ds = xr.Dataset(
        {"t2m": (("time", "latitude", "longitude"), values, {"units": "K"})},
        coords={"time": days, "latitude": lat, "longitude": [13.4]},
        attrs={"time_standard": "UTC"},
    )
    if invalid == "celsius":
        ds.t2m.attrs["units"] = "degC"
    if invalid == "missing_utc":
        del ds.attrs["time_standard"]
    ds.to_netcdf(path, engine="scipy")


def run_solver(source: Path, output: Path, *, should_pass: bool):
    process = subprocess.run(
        [sys.executable, str(SCRIPT), "--input", str(source), "--output", str(output)],
        cwd=str(SCRIPT.parent), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=180,
    )
    if should_pass:
        must(process.returncode == 0,
             f"solver crashed on a valid fixture ({process.returncode}): {process.stderr[-1000:]}")
        inspect_result(output, source, "hidden fixture")
    else:
        must(process.returncode != 0, "solver did not reject invalid input")


def main() -> None:
    must(SCRIPT.is_file(), "Missing submitted /app/solve.py")
    inspect_result(SUBMITTED_OUTPUT, PUBLIC_INPUT, "provided fixture")
    print("PASS: submitted scientific output verified independently")
    with tempfile.TemporaryDirectory(prefix="geoclimatebench-qc-") as work:
        root = Path(work)
        for i, kwargs in enumerate(({}, {"sparse": True})):
            input_file, output = root / f"valid{i}.nc", root / f"valid{i}_out.nc"
            make_input(input_file, **kwargs)
            run_solver(input_file, output, should_pass=True)
        print("PASS: submitted Python program solves two unseen fixture variants")
        for label in ("duplicate", "non-hour", "celsius", "missing_utc", "reversed_lat"):
            input_file, output = root / f"bad_{label}.nc", root / f"bad_{label}_out.nc"
            make_input(input_file, invalid=label)
            run_solver(input_file, output, should_pass=False)
        print("PASS: invalid scientific input conventions are rejected")
    print("ALL SCIENTIFIC CHECKS PASSED")


if __name__ == "__main__":
    main()
