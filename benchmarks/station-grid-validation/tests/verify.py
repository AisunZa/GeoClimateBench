"""Independent numerical verifier for GeoClimateBench station-grid validation.

This verifier does not import geoclimatebench or an agent solution.
"""
import argparse
import csv
import json
import math
import re
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

PAIR_COLUMNS = [
    "station_id", "date", "station_lat", "station_lon", "grid_lat",
    "grid_lon", "distance_km", "observed_tmax_c", "modeled_tmax_c", "error_c",
]
EXCLUSION_NAMES = (
    "missing_observation", "outside_grid", "unavailable_date", "missing_grid",
)
STAT_NAMES = ("bias_c", "mae_c", "rmse_c", "max_abs_error_c")
TOL = 1e-4


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def distance_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    a = math.sin((lat2 - lat1) / 2) ** 2
    a += math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0088 * math.asin(min(1.0, math.sqrt(a)))


def statistics(errors):
    n = len(errors)
    if not n:
        return {"n_pairs": 0, **{name: None for name in STAT_NAMES}}
    return {
        "n_pairs": n,
        "bias_c": math.fsum(errors) / n,
        "mae_c": math.fsum(abs(x) for x in errors) / n,
        "rmse_c": math.sqrt(math.fsum(x * x for x in errors) / n),
        "max_abs_error_c": max(abs(x) for x in errors),
    }


def check_stats(actual, expected, label):
    check(isinstance(actual, dict), f"{label}: expected an object")
    check(actual.get("n_pairs") == expected["n_pairs"], f"{label}: n_pairs mismatch")
    for name in STAT_NAMES:
        value = actual.get(name)
        target = expected[name]
        if target is None:
            check(value is None, f"{label}.{name}: expected null")
        else:
            check(isinstance(value, (int, float)) and not isinstance(value, bool)
                  and math.isfinite(value) and abs(value - target) <= TOL,
                  f"{label}.{name}: expected {target!r}, got {value!r}")


def check_input_and_reconstruct(daily_path, station_path):
    with xr.open_dataset(daily_path) as ds:
        check("tmax_c" in ds and ds.tmax_c.dims == ("time", "latitude", "longitude"),
              "daily NetCDF: variable or dimension-order mismatch")
        check(ds.tmax_c.attrs.get("units") == "degC", "daily NetCDF: temperature units")
        check(ds.attrs.get("time_standard") == "UTC", "daily NetCDF: missing UTC declaration")
        dates = pd.DatetimeIndex(ds.time.values)
        check(len(dates) > 0 and not dates.has_duplicates and dates.is_monotonic_increasing,
              "daily NetCDF: invalid dates")
        check(all(d == d.normalize() for d in dates), "daily NetCDF: non-midnight time")
        days = {d.strftime("%Y-%m-%d"): i for i, d in enumerate(dates)}
        lats = np.asarray(ds.latitude.values, dtype=float)
        lons = np.asarray(ds.longitude.values, dtype=float)
        check(lats.ndim == lons.ndim == 1 and len(lats) and len(lons),
              "daily NetCDF: invalid coordinate shapes")
        check(np.all(np.isfinite(lats)) and np.all(np.isfinite(lons)),
              "daily NetCDF: nonfinite coordinates")
        check(np.all(np.diff(lats) > 0) and np.all(np.diff(lons) > 0),
              "daily NetCDF: unordered coordinates")
        check(np.all(np.abs(lats) <= 90) and np.all(np.abs(lons) <= 180),
              "daily NetCDF: invalid geographical bounds")
        temperatures = np.asarray(ds.tmax_c.values, dtype=float)

    with station_path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        check(reader.fieldnames == ["station_id", "date", "latitude", "longitude", "txk_c"],
              "station CSV: incorrect header")
        source_rows = list(reader)
    check(len(source_rows) > 0, "station CSV: empty input")

    positions, seen, stations = {}, set(), []
    for index, row in enumerate(source_rows, 1):
        sid = row["station_id"]
        day = row["date"]
        check(bool(sid and sid.strip()), f"station row {index}: empty identifier")
        check(bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", day or "")),
              f"station row {index}: invalid date")
        date.fromisoformat(day)
        lat, lon = float(row["latitude"]), float(row["longitude"])
        check(math.isfinite(lat) and math.isfinite(lon) and abs(lat) <= 90 and abs(lon) <= 180,
              f"station row {index}: invalid coordinates")
        check((sid, day) not in seen, f"station row {index}: duplicate station/date")
        seen.add((sid, day))
        check(sid not in positions or positions[sid] == (lat, lon),
              f"station row {index}: inconsistent station position")
        positions[sid] = (lat, lon)
        stations.append((sid, day, lat, lon, row["txk_c"]))

    nearest = {}
    for sid, (lat, lon) in positions.items():
        nearest[sid] = min(
            (distance_km(lat, lon, float(glat), float(glon)), i, j)
            for i, glat in enumerate(lats)
            for j, glon in enumerate(lons)
        )

    expected, excluded = [], {name: 0 for name in EXCLUSION_NAMES}
    for sid, day, lat, lon, observed_text in stations:
        observed = float(observed_text) if observed_text and observed_text.strip() else math.nan
        if not math.isfinite(observed) or observed <= -999 or observed < -80 or observed > 65:
            excluded["missing_observation"] += 1
            continue
        dist, i, j = nearest[sid]
        if dist > 180.0:
            excluded["outside_grid"] += 1
            continue
        if day not in days:
            excluded["unavailable_date"] += 1
            continue
        modeled = float(temperatures[days[day], i, j])
        if not math.isfinite(modeled):
            excluded["missing_grid"] += 1
            continue
        expected.append({
            "station_id": sid, "date": day, "station_lat": lat, "station_lon": lon,
            "grid_lat": float(lats[i]), "grid_lon": float(lons[j]),
            "distance_km": dist, "observed_tmax_c": observed,
            "modeled_tmax_c": modeled, "error_c": modeled - observed,
        })
    return sorted(expected, key=lambda r: (r["station_id"], r["date"])), excluded, positions, len(stations)


def verify(daily_path, station_path, pairs_path, metrics_path):
    expected, excluded, positions, n_input = check_input_and_reconstruct(daily_path, station_path)
    with pairs_path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        check(reader.fieldnames == PAIR_COLUMNS, "pairs: incorrect columns or column order")
        actual = list(reader)
    check(len(actual) == len(expected), f"pairs: expected {len(expected)}, got {len(actual)}")
    for index, (row, reference) in enumerate(zip(actual, expected), 1):
        for field in PAIR_COLUMNS:
            if field in ("station_id", "date"):
                check(row[field] == reference[field], f"pairs row {index}: {field} mismatch")
            else:
                try:
                    number = float(row[field])
                except (ValueError, TypeError) as exc:
                    raise AssertionError(f"pairs row {index}: invalid {field}") from exc
                check(math.isfinite(number) and abs(number - reference[field]) <= TOL,
                      f"pairs row {index}: {field} mismatch")

    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    check(metrics.get("comparison") == "modeled_tmax_c - observed_tmax_c",
          "metrics: error sign metadata mismatch")
    check(metrics.get("grid_matching") == "nearest great-circle (haversine) cell; no interpolation",
          "metrics: matching metadata mismatch")
    check(metrics.get("max_distance_km") == 180.0, "metrics: distance threshold mismatch")
    check(metrics.get("n_input_rows") == n_input, "metrics: input count mismatch")
    check(metrics.get("all_stations") == sorted(positions), "metrics: station list mismatch")
    check(metrics.get("n_excluded") == excluded, "metrics: exclusion categories or counts mismatch")
    check(isinstance(metrics.get("limitations"), list) and metrics["limitations"]
          and all(isinstance(s, str) and s.strip() for s in metrics["limitations"]),
          "metrics: missing scientific limitations")
    check_stats(metrics.get("overall"), statistics([r["error_c"] for r in expected]), "overall")
    by_station = metrics.get("by_station")
    check(isinstance(by_station, dict), "metrics: by_station must be an object")
    missing = sorted(set(positions) - set(by_station))
    extra = sorted(set(by_station) - set(positions))
    check(not missing and not extra,
          f"by_station station coverage mismatch: missing={missing}, extra={extra}")
    for sid in sorted(positions):
        check_stats(by_station[sid], statistics([r["error_c"] for r in expected
                                                 if r["station_id"] == sid]), f"by_station.{sid}")
    print(f"PASS: independently reconstructed {len(expected)} pairs and {sum(excluded.values())} exclusions")
    print("PASS: all-station metrics, zero-pair stations, and scientific metadata")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--daily", type=Path, required=True)
    parser.add_argument("--stations", type=Path, required=True)
    parser.add_argument("--pairs", type=Path, required=True)
    parser.add_argument("--metrics", type=Path, required=True)
    args = parser.parse_args()
    try:
        verify(args.daily, args.stations, args.pairs, args.metrics)
    except (AssertionError, ValueError, KeyError, OSError) as exc:
        print(f"FAIL: {exc}", file=__import__("sys").stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
