"""Scientific reference algorithms for task 1 and task 2.

Explicit conventions, no spatial interpolation, no hidden climatological assumptions.
"""
import calendar
from datetime import date

import numpy as np
import pandas as pd
import xarray as xr


def _grid_check(ds: xr.Dataset, var: str) -> None:
    if var not in ds:
        raise ValueError(f"Required variable {var!r} is missing")
    for dim in ("time", "latitude", "longitude"):
        if dim not in ds[var].dims or dim not in ds.coords:
            raise ValueError(f"{var} requires dimension and coordinate {dim!r}")
    if ds[var].dims != ("time", "latitude", "longitude"):
        raise ValueError(f"Expected time/latitude/longitude dimension order for {var}")
    index = pd.DatetimeIndex(ds.time.values)
    if len(index) == 0 or index.has_duplicates or not index.is_monotonic_increasing:
        raise ValueError("Time coordinate must be nonempty, unique, and increasing")
    if np.any(~np.isfinite(ds.latitude.values)) or np.any(~np.isfinite(ds.longitude.values)):
        raise ValueError("Latitude/longitude coordinates must be finite")
    if np.any(np.diff(ds.latitude.values) <= 0) or np.any(np.diff(ds.longitude.values) <= 0):
        raise ValueError("Latitude/longitude must be strictly increasing")
    if np.any(np.abs(ds.latitude.values) > 90) or np.any(np.abs(ds.longitude.values) > 180):
        raise ValueError("Coordinates must be within geographic latitude/longitude ranges")


def daily_max_from_hourly(ds: xr.Dataset, min_valid_hours: int = 18) -> xr.Dataset:
    """Compute maximum available hourly samples, not an instantaneous continuous-day max.

    Every input time is interpreted as UTC. Invalid values (<180 or >340 K) are
    marked missing before aggregation; days with fewer than min_valid_hours are NaN.
    No implicit interpolation or unit guessing is permitted.
    """
    if not 1 <= min_valid_hours <= 24:
        raise ValueError("min_valid_hours must be in [1,24]")
    _grid_check(ds, "t2m")
    if ds.t2m.attrs.get("units") not in ("K", "kelvin", "Kelvin"):
        raise ValueError("Expected t2m units 'K'; do not silently guess units")
    if ds.attrs.get("time_standard") != "UTC":
        raise ValueError("Input must explicitly declare time_standard='UTC'")
    time = pd.DatetimeIndex(ds.time.values)
    if not np.all((time.minute == 0) & (time.second == 0)):
        raise ValueError("Only exact UTC hourly timestamps are supported")
    if len(np.unique(time.floor("D"))) == 0:
        raise ValueError("No complete dates found")
    # Duplicate and non-hourly within a day inputs are rejected; gaps are okay.
    if np.any(np.diff(time.to_numpy(dtype="datetime64[ns]").astype("int64")) < 3_600_000_000_000):
        raise ValueError("Hourly samples must be at least 1 hour apart")
    clean = ds.t2m.where(np.isfinite(ds.t2m) & (ds.t2m >= 180) & (ds.t2m <= 340))
    temp = clean.assign_coords(day=("time", time.floor("D").to_numpy()))
    counts = temp.groupby("day").count(dim="time").astype("int16")
    counts.attrs = {"units": "hours", "description": "Count of QC-accepted hourly samples"}
    maximum = temp.groupby("day").max(dim="time", skipna=True)
    tmax = (maximum - 273.15).where(counts >= min_valid_hours)
    return xr.Dataset(
        {
            "tmax_c": tmax.rename(day="time").astype("float32"),
            "hours_valid": counts.rename(day="time"),
        },
        attrs={
            "method": "Daily max of valid hourly ERA5-like 2m temperature samples",
            "time_standard": "UTC",
            "minimum_valid_hours": min_valid_hours,
            "source_type": ds.attrs.get("dataset_type", "Unverified user-supplied input"),
            "limits": "Hourly sampling differs from continuous observations and DWD daily max.",
        },
    ).assign(tmax_c=lambda x: x.tmax_c.assign_attrs(units="degC"))


def _noleap_day_of_year(timestamp: pd.Timestamp) -> int:
    """Map month/day onto a fixed nonleap 2001 calendar, never silently use leap DOY."""
    if timestamp.month == 2 and timestamp.day == 29:
        raise ValueError("Feb 29 is not supported by this no-leap moving-window method")
    return date(2001, timestamp.month, timestamp.day).timetuple().tm_yday


def _circular_distance(a: np.ndarray, b: int) -> np.ndarray:
    diff = np.abs(a - b)
    return np.minimum(diff, 365 - diff)


def _mark_events(exceeds: np.ndarray, dates: pd.DatetimeIndex, min_days: int) -> tuple[np.ndarray, int, int]:
    """Return full-run mask, number of episodes, longest length; break on date gaps."""
    flagged = np.zeros(len(exceeds), dtype=bool)
    event_count, longest = 0, 0
    start = None
    # Explicit nanosecond precision avoids NumPy generic-timedelta warnings.
    date_ns = dates.to_numpy(dtype="datetime64[ns]").astype("int64")
    for i in range(len(exceeds) + 1):
        in_run = i < len(exceeds) and bool(exceeds[i])
        continuous = i > 0 and i < len(exceeds) and (date_ns[i] - date_ns[i - 1] == 86_400_000_000_000)
        if start is not None and (not in_run or not continuous):
            end = i
            run_len = end - start
            if run_len >= min_days:
                flagged[start:end] = True
                event_count += 1
                longest = max(longest, run_len)
            start = None
        if in_run and start is None:
            start = i
    return flagged, event_count, longest


def compute_extremes(
    daily: xr.Dataset,
    *,
    target_year: int = 2022,
    target_month: int = 7,
    baseline_start: int = 1991,
    baseline_end: int = 2020,
    window_days: int = 7,
    percentile: float = 90,
    min_baseline_samples: int = 300,
    min_baseline_years: int = 20,
    min_run_days: int = 5,
) -> xr.Dataset:
    """Daily threshold with calendar ±window and percentile, plus run-length detection.

    Baseline excludes target, thresholds are independently computed per grid cell.
    No interpolation, no spatial smoothing; strictly greater than is an exceedance.
    """
    _grid_check(daily, "tmax_c")
    if not (baseline_start <= baseline_end < target_year):
        raise ValueError("Baseline range must precede target year")
    if target_month not in range(1, 13):
        raise ValueError("Invalid target month")
    if not (0 < percentile < 100) or not (0 <= window_days <= 30):
        raise ValueError("Bad percentile or window_days")
    if min_run_days < 1 or min_baseline_years < 1 or min_baseline_samples < 1:
        raise ValueError("Required positive minimum coverage and event length")
    dates = pd.DatetimeIndex(daily.time.values)
    mask_baseline = (dates.year >= baseline_start) & (dates.year <= baseline_end)
    mask_target = (dates.year == target_year) & (dates.month == target_month)
    target_dates = dates[mask_target]
    if len(target_dates) == 0:
        raise ValueError("No target dates in daily data")
    required = pd.date_range(f"{target_year}-{target_month:02d}-01", periods=calendar.monthrange(target_year, target_month)[1], freq="D")
    if not target_dates.equals(required):
        raise ValueError("The target month must have all daily timestamps; partial months are not evaluated")
    baseline_dates = dates[mask_baseline]
    baseline = daily.tmax_c.values[mask_baseline, :, :]
    if len(baseline_dates) == 0:
        raise ValueError("No reference baseline dates")
    bday = np.array([_noleap_day_of_year(d) for d in baseline_dates])
    tday = np.array([_noleap_day_of_year(d) for d in target_dates])
    byear = np.asarray(baseline_dates.year)
    target = daily.tmax_c.values[mask_target, :, :]
    nt, nlat, nlon = target.shape
    threshold = np.full((nt, nlat, nlon), np.nan, dtype="float64")
    nsample = np.zeros((nt, nlat, nlon), dtype="int16")
    nyears = np.zeros((nt, nlat, nlon), dtype="int16")
    for i, d in enumerate(tday):
        match = _circular_distance(bday, d) <= window_days
        values = baseline[match]
        finite = np.isfinite(values)
        nsample[i] = finite.sum(axis=0)
        years = byear[match]
        for year in np.unique(years):
            nyears[i] += np.any(finite[years == year], axis=0)
        eligible = (nsample[i] >= min_baseline_samples) & (nyears[i] >= min_baseline_years)
        if np.any(eligible):
            # Avoid RuntimeWarning for all-NaN grid cells.
            vals2 = values.reshape(len(values), -1)
            eligible_flat = eligible.ravel()
            threshold[i].ravel()[eligible_flat] = np.nanpercentile(
                vals2[:, eligible_flat], percentile, axis=0, method="linear"
            )
    exceeds = np.isfinite(target) & np.isfinite(threshold) & (target > threshold)
    flagged = np.zeros_like(exceeds, dtype="bool")
    event_count = np.zeros((nlat, nlon), dtype="int16")
    max_length = np.zeros((nlat, nlon), dtype="int16")
    for j in range(nlat):
        for k in range(nlon):
            flagged[:, j, k], event_count[j, k], max_length[j, k] = _mark_events(
                exceeds[:, j, k], target_dates, min_run_days
            )
    return xr.Dataset(
        {
            "threshold_c": (("time", "latitude", "longitude"), threshold.astype("float32")),
            "baseline_samples": (("time", "latitude", "longitude"), nsample),
            "baseline_years": (("time", "latitude", "longitude"), nyears),
            "exceedance_day": (("time", "latitude", "longitude"), exceeds.astype("int8")),
            "heatwave_day": (("time", "latitude", "longitude"), flagged.astype("int8")),
            "event_count": (("latitude", "longitude"), event_count),
            "heatwave_days": (("latitude", "longitude"), flagged.sum(axis=0).astype("int16")),
            "max_event_length": (("latitude", "longitude"), max_length),
        },
        coords={"time": target_dates.to_numpy(), "latitude": daily.latitude.values, "longitude": daily.longitude.values},
        attrs={
            "baseline_period": f"{baseline_start}-{baseline_end}",
            "target_period": f"{target_year}-{target_month:02d}",
            "percentile": percentile,
            "window_days_each_side": window_days,
            "minimum_baseline_samples": min_baseline_samples,
            "minimum_baseline_years": min_baseline_years,
            "min_consecutive_exceedance_days": min_run_days,
            "comparison": "strict_gt",
            "calendar": "365-day month/day indexing; Feb 29 excluded",
            "source_type": daily.attrs.get("source_type", "Unverified input"),
        },
    ).assign(threshold_c=lambda x: x.threshold_c.assign_attrs(units="degC"))
