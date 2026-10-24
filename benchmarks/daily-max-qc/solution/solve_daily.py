"""Reference implementation for the Harbor Oracle agent, NOT the verifier."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr


def solve(data: xr.Dataset) -> xr.Dataset:
    if "t2m" not in data or data.t2m.dims != ("time", "latitude", "longitude"):
        raise ValueError("Expected t2m(time, latitude, longitude)")
    if any(k not in data.coords for k in ("time", "latitude", "longitude")):
        raise ValueError("Missing required coordinates")
    if data.t2m.attrs.get("units") not in ("K", "kelvin", "Kelvin"):
        raise ValueError("Temperature input must declare Kelvin")
    if data.attrs.get("time_standard") != "UTC":
        raise ValueError("Expected explicit UTC time_standard")

    times = pd.DatetimeIndex(data.time.values)
    if len(times) == 0 or times.has_duplicates or not times.is_monotonic_increasing:
        raise ValueError("Time must be unique, ordered, and nonempty")
    if not np.all((times.minute == 0) & (times.second == 0) & (times.microsecond == 0) & (times.nanosecond == 0)):
        raise ValueError("Time samples must fall on exact UTC hours")
    time_ns = times.to_numpy(dtype="datetime64[ns]").astype("int64")
    if np.any(np.diff(time_ns) < 3_600_000_000_000):
        raise ValueError("Subhourly samples are not allowed")

    for name, low, high in (("latitude", -90.0, 90.0), ("longitude", -180.0, 180.0)):
        coords = np.asarray(data[name].values)
        if coords.ndim != 1 or not len(coords) or not np.all(np.isfinite(coords)):
            raise ValueError(f"Invalid {name} coordinates")
        if not np.all((coords >= low) & (coords <= high)) or np.any(np.diff(coords) <= 0):
            raise ValueError(f"Out-of-range, duplicate, or decreasing {name} coordinates")

    valid = data.t2m.where(np.isfinite(data.t2m) & (data.t2m >= 180) & (data.t2m <= 340))
    grouped = valid.assign_coords(day=("time", times.floor("D").to_numpy()))
    counts = grouped.groupby("day").count(dim="time").astype("int16")
    counts.attrs = {"units": "1", "description": "Count of valid hourly samples"}
    sampled_max = grouped.groupby("day").max(dim="time", skipna=True)
    tmax = (sampled_max - 273.15).where(counts >= 18).astype("float32")
    tmax.attrs = {"units": "degC"}

    return xr.Dataset(
        {"tmax_c": tmax.rename(day="time"), "hours_valid": counts.rename(day="time")},
        attrs={"time_standard": "UTC", "method": "Valid hourly-sampled UTC daily maximum"},
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    with xr.open_dataset(args.input) as ds:
        result = solve(ds)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_netcdf(output, engine="scipy")


if __name__ == "__main__":
    main()
