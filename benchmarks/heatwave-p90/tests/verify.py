"""Independent Harbor verifier: no import of reference solution or fixture generator.

The independent reference uses explicit month/day window loops and a separate
run detector, not the Oracle's vectorized procedure. Verifies outputs and
reruns the submitted source against unseen input datasets.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

SCRIPT = Path(os.environ.get("GC_SUBMISSION_SCRIPT", "/app/solve.py"))
OUTPUT = Path(os.environ.get("GC_SUBMITTED_OUTPUT", "/app/results/heatwaves.nc"))
PUBLIC_INPUT = Path(os.environ.get("GC_PUBLIC_INPUT", "/tests/data/daily_synthetic.nc"))
THREE_D = ("time", "latitude", "longitude")
TWO_D = ("latitude", "longitude")
FIELDS3 = ("threshold_c", "baseline_samples", "baseline_years", "exceedance_day", "heatwave_day")
FIELDS2 = ("event_count", "heatwave_days", "max_event_length")


def require(ok, msg):
    if not ok:
        raise AssertionError(msg)


def noleap(t):
    if t.month == 2 and t.day == 29:
        raise ValueError("Feb 29 not supported")
    return date(2001, t.month, t.day).timetuple().tm_yday


def truth(input_ds):
    """Independent scalar reference, deliberately using explicit per-cell loops."""
    timestamps = pd.DatetimeIndex(input_ds.time.values)
    baseline_indices = [i for i, d in enumerate(timestamps) if 1991 <= d.year <= 2020]
    target_indices = [i for i, d in enumerate(timestamps) if d.year == 2022 and d.month == 7]
    target_days = timestamps[target_indices]
    shape = (len(target_days), len(input_ds.latitude), len(input_ds.longitude))
    raw = np.asarray(input_ds.tmax_c.values, dtype=np.float64)
    basetime = [timestamps[i] for i in baseline_indices]
    target = raw[target_indices]
    threshold = np.full(shape, np.nan, dtype=np.float64)
    samples = np.zeros(shape, dtype=np.int16)
    unique_years = np.zeros(shape, dtype=np.int16)
    exceeding = np.zeros(shape, dtype=np.int8)
    flagged = np.zeros(shape, dtype=np.int8)
    count_events = np.zeros(shape[1:], dtype=np.int16)
    total_days = np.zeros(shape[1:], dtype=np.int16)
    longest_run = np.zeros(shape[1:], dtype=np.int16)

    for j in range(shape[1]):
        for k in range(shape[2]):
            for q, day in enumerate(target_days):
                target_ordinal = noleap(day)
                gathered = []
                distinct_years = set()
                for baseline_position, baseline_day in zip(baseline_indices, basetime):
                    ordinal = noleap(baseline_day)
                    delta = abs(ordinal - target_ordinal)
                    if min(delta, 365 - delta) <= 7:
                        value = raw[baseline_position, j, k]
                        if np.isfinite(value):
                            gathered.append(value)
                            distinct_years.add(baseline_day.year)
                samples[q, j, k] = len(gathered)
                unique_years[q, j, k] = len(distinct_years)
                if len(gathered) >= 300 and len(distinct_years) >= 20:
                    threshold[q, j, k] = np.percentile(gathered, 90, method="linear")
                if np.isfinite(target[q, j, k]) and np.isfinite(threshold[q, j, k]):
                    exceeding[q, j, k] = int(target[q, j, k] > threshold[q, j, k])

            # Independent event detector: enumerate contiguous true positions.
            run = []
            for q in range(len(target_days) + 1):
                active = q < len(target_days) and exceeding[q, j, k] == 1
                calendar_continuous = (q == 0 or
                    (q < len(target_days) and target_days[q] - target_days[q - 1] == pd.Timedelta(days=1)))
                if active and calendar_continuous:
                    run.append(q)
                else:
                    if len(run) >= 5:
                        flagged[run, j, k] = 1
                        count_events[j, k] += 1
                        total_days[j, k] += len(run)
                        longest_run[j, k] = max(longest_run[j, k], len(run))
                    run = [q] if active else []
    return {
        "threshold_c": threshold,
        "baseline_samples": samples,
        "baseline_years": unique_years,
        "exceedance_day": exceeding,
        "heatwave_day": flagged,
        "event_count": count_events,
        "heatwave_days": total_days,
        "max_event_length": longest_run,
    }


def inspect(input_path, output_path, label):
    require(output_path.is_file(), f"{label}: missing NetCDF result")
    with xr.open_dataset(input_path) as src, xr.open_dataset(output_path) as out:
        require(set(out.data_vars) >= set(FIELDS3 + FIELDS2), f"{label}: missing output variables")
        require(out.threshold_c.attrs.get("units") == "degC", f"{label}: threshold units")
        for key in FIELDS3:
            require(out[key].dims == THREE_D, f"{label}: {key} dimensions")
        for key in FIELDS2:
            require(out[key].dims == TWO_D, f"{label}: {key} dimensions")
        for key in FIELDS3[1:] + FIELDS2:
            require(out[key].dtype.kind in "iu", f"{label}: {key} must be integer")
        metadata = {
            "baseline_period": "1991-2020", "target_period": "2022-07", "percentile": 90,
            "window_days_each_side": 7, "minimum_baseline_samples": 300,
            "minimum_baseline_years": 20, "min_consecutive_exceedance_days": 5,
            "comparison": "strict_gt",
        }
        for k, v in metadata.items():
            require(out.attrs.get(k) == v, f"{label}: metadata {k}")
        dates = pd.date_range("2022-07-01", "2022-07-31", freq="D").to_numpy(dtype="datetime64[ns]")
        require(np.array_equal(out.time.values.astype("datetime64[ns]"), dates), f"{label}: target days")
        for key in ("latitude", "longitude"):
            require(np.array_equal(src[key].values, out[key].values), f"{label}: {key} coordinates")
        expected = truth(src)
        for key, arr in expected.items():
            got = out[key].values
            require(got.shape == arr.shape, f"{label}: {key} shape")
            if key == "threshold_c":
                require(np.allclose(got, arr, atol=1e-4, rtol=0, equal_nan=True),
                        f"{label}: moving-window p90 threshold mismatch")
            else:
                require(np.array_equal(got, arr), f"{label}: {key} differs")


def unseen_input(path, variant=0, invalid=None):
    rng = np.random.default_rng(700 + variant)
    years = [pd.date_range(f"{y}-06-24", f"{y}-08-07", freq="D") for y in range(1991, 2021)]
    years.append(pd.date_range("2022-07-01", "2022-07-31", freq="D"))
    times = years[0].append(years[1:])
    data = np.zeros((len(times), 2, 2), dtype=np.float32)
    for i, t in enumerate(times):
        # A different parameterization from build_fixture.py.
        data[i] = 23.0 + (t.month - 6) * .45 + (t.day % 8) * .11 + \
            (t.year - 1991) * (.01 if t.year < 2022 else 0) + \
            np.array([[1., 2.], [-.5, .4]]) + rng.normal(0, .14, (2, 2))
        if t.year == 2022:
            data[i] -= 2.5
            if variant == 0:
                if 1 <= t.day <= 5:
                    data[i, 0, 0] += 9
                if 10 <= t.day <= 13:
                    data[i, 0, 1] += 9  # 4-day episode
                if 22 <= t.day <= 27:
                    data[i, 1, 1] += 9
                if t.day == 24:
                    data[i, 1, 1] = np.nan  # split 6-day run
            else:
                if 27 <= t.day <= 31:
                    data[i, 0, 0] += 9  # 5 at month end
                if 11 <= t.day <= 17:
                    data[i, 1, 0] += 9  # 7 days
                if 5 <= t.day <= 11:
                    data[i, 0, 1] += 9
        if 1991 <= t.year <= 2000:
            data[i, 0, 1] = np.nan  # exactly 20 valid years
        if variant == 1 and 1991 <= t.year <= 2008:
            data[i, 1, 1] = np.nan  # below minimum baseline years
    # Exact equality case: constant baseline p90=24.0 for cell [1,1].
    # A target at exactly 24.0 must NOT exceed the threshold.
    if variant == 0:
        for i, t in enumerate(times):
            if 1991 <= t.year <= 2020:
                data[i, 1, 1] = 24.0
            elif t.year == 2022 and t.month == 7 and t.day == 7:
                data[i, 1, 1] = 24.0
    if invalid == "duplicate":
        times = pd.DatetimeIndex([times[0], *times[:-1]])
    elif invalid == "missing_target":
        mask = np.asarray(times != pd.Timestamp("2022-07-12"))
        times = times[mask]
        data = data[mask]
    elif invalid == "nonmidnight":
        times = times + pd.Timedelta(hours=12)
    elif invalid == "feb29":
        leap = pd.Timestamp("2000-02-29")
        pos = times.searchsorted(leap)
        times = times[:pos].append(pd.DatetimeIndex([leap])).append(times[pos:])
        data = np.insert(data, pos, data[pos - 1], axis=0)
    lat = [39., 41.] if invalid != "reversed_lat" else [41., 39.]
    ds = xr.Dataset(
        {"tmax_c": (THREE_D, data, {"units": "degC"})},
        coords={"time": times, "latitude": lat, "longitude": [-8., 5.]},
        attrs={"time_standard": "UTC", "dataset_type": "synthetic"},
    )
    if invalid == "wrong_units":
        ds.tmax_c.attrs["units"] = "K"
    if invalid == "missing_utc":
        del ds.attrs["time_standard"]
    ds.to_netcdf(path, engine="scipy")


def execute(input_file, output_file, should_accept):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--input", str(input_file), "--output", str(output_file)],
        cwd=str(SCRIPT.parent), capture_output=True, text=True, timeout=240,
    )
    if should_accept:
        require(result.returncode == 0,
                f"Solver failed on valid unseen fixture: {result.stderr[-1500:]}")
        inspect(input_file, output_file, "unseen fixture")
    else:
        require(result.returncode != 0, "Invalid input not rejected")


def main():
    require(SCRIPT.is_file(), "Missing submitted /app/solve.py")
    inspect(PUBLIC_INPUT, OUTPUT, "supplied fixture")
    print("PASS: provided synthetic fixture independently verified")
    with tempfile.TemporaryDirectory(prefix="geoclimatebench-heatwaves-") as td:
        root = Path(td)
        for variant in (0, 1):
            input_file = root / f"case{variant}.nc"
            output_file = root / f"case{variant}_out.nc"
            unseen_input(input_file, variant)
            execute(input_file, output_file, True)
        print("PASS: two independent unseen scientific fixtures")
        for i, invalid in enumerate(("duplicate", "missing_target", "nonmidnight", "feb29",
                                     "reversed_lat", "wrong_units", "missing_utc")):
            input_file, output_file = root / f"invalid{i}.nc", root / f"invalid{i}_out.nc"
            unseen_input(input_file, 0, invalid)
            execute(input_file, output_file, False)
        print("PASS: seven invalid-input cases rejected")
    print("ALL HEATWAVE P90 CHECKS PASSED")


if __name__ == "__main__":
    main()
