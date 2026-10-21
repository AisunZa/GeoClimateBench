"""Reference solution for Harbor Oracle; not included in the agent image."""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr


def day365(t: pd.Timestamp) -> int:
    if t.month == 2 and t.day == 29:
        raise ValueError("February 29 is unsupported in the 365-day climatology")
    return date(2001, t.month, t.day).timetuple().tm_yday


def run(ds: xr.Dataset) -> xr.Dataset:
    if "tmax_c" not in ds or ds.tmax_c.dims != ("time", "latitude", "longitude"):
        raise ValueError("Expected tmax_c(time, latitude, longitude)")
    if any(c not in ds.coords for c in ("time", "latitude", "longitude")):
        raise ValueError("Missing time or spatial coordinates")
    if ds.tmax_c.attrs.get("units") != "degC" or ds.attrs.get("time_standard") != "UTC":
        raise ValueError("Must declare Celsius temperatures and UTC time")
    dates = pd.DatetimeIndex(ds.time.values)
    if dates.empty or dates.has_duplicates or not dates.is_monotonic_increasing:
        raise ValueError("Dates must be strictly increasing, unique, and nonempty")
    if np.any((dates.hour != 0) | (dates.minute != 0) | (dates.second != 0) |
              (dates.microsecond != 0) | (dates.nanosecond != 0)):
        raise ValueError("Daily timestamps must be UTC midnight")
    if np.any(np.diff(dates.to_numpy(dtype="datetime64[ns]").astype(np.int64)) < 86_400_000_000_000):
        raise ValueError("Less-than-daily spacing in timestamps")
    for name, lower, upper in (("latitude", -90, 90), ("longitude", -180, 180)):
        values = np.asarray(ds[name].values, dtype=float)
        if (values.ndim != 1 or values.size == 0 or not np.all(np.isfinite(values)) or
            np.any(values < lower) or np.any(values > upper) or np.any(np.diff(values) <= 0)):
            raise ValueError(f"Invalid {name} coordinates")
    baseline_mask = (dates.year >= 1991) & (dates.year <= 2020)
    target_mask = (dates.year == 2022) & (dates.month == 7)
    expected_target = pd.date_range("2022-07-01", "2022-07-31", freq="D")
    targets = dates[target_mask]
    if not targets.equals(expected_target) or not baseline_mask.any():
        raise ValueError("Missing required July 2022 or reference baseline dates")
    bdates = dates[baseline_mask]
    bday = np.array([day365(t) for t in bdates], dtype=np.int16)
    tday = np.array([day365(t) for t in targets], dtype=np.int16)
    years = bdates.year.to_numpy()
    baseline = ds.tmax_c.values[baseline_mask].astype(np.float64)
    target = ds.tmax_c.values[target_mask].astype(np.float64)
    ntime, nlat, nlon = target.shape

    threshold = np.full(target.shape, np.nan, dtype=np.float64)
    samples = np.zeros(target.shape, dtype=np.int16)
    coverage_years = np.zeros(target.shape, dtype=np.int16)
    for i, ordinal in enumerate(tday):
        distance = np.abs(bday - ordinal)
        in_window = np.minimum(distance, 365 - distance) <= 7
        reference = baseline[in_window]
        available = np.isfinite(reference)
        samples[i] = available.sum(axis=0)
        window_years = years[in_window]
        for y in np.unique(window_years):
            coverage_years[i] += np.any(available[window_years == y], axis=0)
        eligible = (samples[i] >= 300) & (coverage_years[i] >= 20)
        for j, k in np.argwhere(eligible):
            threshold[i, j, k] = np.percentile(reference[:, j, k][available[:, j, k]], 90, method="linear")
    exceed = np.isfinite(target) & np.isfinite(threshold) & (target > threshold)
    heatwave = np.zeros(exceed.shape, dtype=np.int8)
    events = np.zeros((nlat, nlon), dtype=np.int16)
    longest = np.zeros((nlat, nlon), dtype=np.int16)
    for j in range(nlat):
        for k in range(nlon):
            start = None
            for i in range(ntime + 1):
                valid = i < ntime and bool(exceed[i, j, k])
                if valid and start is None:
                    start = i
                if not valid and start is not None:
                    length = i - start
                    if length >= 5:
                        heatwave[start:i, j, k] = 1
                        events[j, k] += 1
                        longest[j, k] = max(longest[j, k], length)
                    start = None
    out = xr.Dataset(
        {
            "threshold_c": (("time", "latitude", "longitude"), threshold.astype(np.float32), {"units": "degC"}),
            "baseline_samples": (("time", "latitude", "longitude"), samples),
            "baseline_years": (("time", "latitude", "longitude"), coverage_years),
            "exceedance_day": (("time", "latitude", "longitude"), exceed.astype(np.int8)),
            "heatwave_day": (("time", "latitude", "longitude"), heatwave),
            "event_count": (("latitude", "longitude"), events),
            "heatwave_days": (("latitude", "longitude"), heatwave.sum(axis=0).astype(np.int16)),
            "max_event_length": (("latitude", "longitude"), longest),
        },
        coords={"time": targets.to_numpy(dtype="datetime64[ns]"),
                "latitude": ds.latitude.values, "longitude": ds.longitude.values},
        attrs={"baseline_period": "1991-2020", "target_period": "2022-07", "percentile": 90,
               "window_days_each_side": 7, "minimum_baseline_samples": 300,
               "minimum_baseline_years": 20, "min_consecutive_exceedance_days": 5,
               "comparison": "strict_gt", "source_type": "synthetic"},
    )
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    with xr.open_dataset(args.input) as ds:
        result = run(ds)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_netcdf(output, engine="scipy")


if __name__ == "__main__":
    main()
