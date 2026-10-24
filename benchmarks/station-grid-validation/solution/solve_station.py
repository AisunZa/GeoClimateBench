"""Reference solution for the standalone GeoClimateBench station-grid benchmark.

Synthetic-fixture algorithm verification; not real station validation.
The benchmark's verifier must independently reconstruct expected results.
"""

import argparse
import csv
import json
import math
import re
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

EARTH_RADIUS_KM = 6371.0088
MAX_MATCH_DISTANCE_KM = 180.0
STATION_FIELDS = ["station_id", "date", "latitude", "longitude", "txk_c"]
PAIR_FIELDS = [
    "station_id", "date", "station_lat", "station_lon", "grid_lat",
    "grid_lon", "distance_km", "observed_tmax_c", "modeled_tmax_c", "error_c",
]
EXCLUSION_REASONS = (
    "missing_observation", "outside_grid", "unavailable_date", "missing_grid",
)


def load_daily(path):
    """Validate the daily-maximum NetCDF and return plain in-memory arrays."""
    with xr.open_dataset(path) as ds:
        if "tmax_c" not in ds or ds["tmax_c"].dims != ("time", "latitude", "longitude"):
            raise ValueError("tmax_c must have (time, latitude, longitude) dimensions")
        if ds["tmax_c"].attrs.get("units") != "degC":
            raise ValueError("tmax_c must declare units='degC'")
        if ds.attrs.get("time_standard") != "UTC":
            raise ValueError("the input must declare time_standard='UTC'")
        for name in ("time", "latitude", "longitude"):
            if name not in ds.coords or ds[name].dims != (name,):
                raise ValueError(f"{name} must be a one-dimensional coordinate")

        try:
            dates = pd.DatetimeIndex(ds["time"].values)
        except (TypeError, ValueError) as exc:
            raise ValueError("time must be a valid daily datetime coordinate") from exc
        if (
            not len(dates)
            or dates.hasnans
            or dates.has_duplicates
            or not dates.is_monotonic_increasing
            or not np.all(dates == dates.normalize())
        ):
            raise ValueError("time must have unique, increasing UTC-midnight days")

        lats = np.asarray(ds["latitude"].values, dtype="float64")
        lons = np.asarray(ds["longitude"].values, dtype="float64")
        for name, coords, bound in (("latitude", lats, 90), ("longitude", lons, 180)):
            if (
                not len(coords)
                or not np.all(np.isfinite(coords))
                or not np.all(np.abs(coords) <= bound)
                or not np.all(np.diff(coords) > 0)
            ):
                raise ValueError(f"invalid {name} coordinates")

        temperatures = np.asarray(ds["tmax_c"].values, dtype="float64")
        days = {day.strftime("%Y-%m-%d"): i for i, day in enumerate(dates)}
    return days, lats, lons, temperatures


def load_stations(path):
    """Reject bad records before any exclusions; keep original station rows."""
    records = []
    positions = {}
    seen = set()
    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames != STATION_FIELDS:
            raise ValueError("station CSV header must match the required five columns")
        for row_number, row in enumerate(reader, 2):
            if None in row or any(row[key] is None for key in STATION_FIELDS):
                raise ValueError(f"malformed station CSV row {row_number}")
            station = row["station_id"]
            day = row["date"]
            if not station or not station.strip():
                raise ValueError(f"empty station_id in row {row_number}")
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day or ""):
                raise ValueError(f"invalid date format in row {row_number}")
            try:
                date.fromisoformat(day)
            except ValueError as exc:
                raise ValueError(f"invalid calendar date in row {row_number}") from exc
            try:
                lat = float(row["latitude"])
                lon = float(row["longitude"])
                observed = float(row["txk_c"]) if row["txk_c"].strip() else math.nan
            except ValueError as exc:
                raise ValueError(f"invalid numerical field in row {row_number}") from exc
            if not (math.isfinite(lat) and math.isfinite(lon) and abs(lat) <= 90 and abs(lon) <= 180):
                raise ValueError(f"invalid geographic coordinates in row {row_number}")
            key = (station, day)
            if key in seen:
                raise ValueError(f"duplicate station/date in row {row_number}")
            seen.add(key)
            position = (lat, lon)
            if station in positions and positions[station] != position:
                raise ValueError(f"inconsistent coordinates for station {station!r}")
            positions[station] = position
            records.append((station, day, lat, lon, observed))
    if not records:
        raise ValueError("station CSV must contain at least one record")
    return records, positions


def distance_km(station_lat, station_lon, grid_lat, grid_lon):
    """Haversine great-circle distance on a sphere of radius 6371.0088 km."""
    a, b, c, d = map(math.radians, (station_lat, station_lon, grid_lat, grid_lon))
    hav = math.sin((c - a) / 2) ** 2
    hav += math.cos(a) * math.cos(c) * math.sin((d - b) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(hav)))


def error_stats(errors):
    n = len(errors)
    if n == 0:
        return {
            "n_pairs": 0,
            "bias_c": None,
            "mae_c": None,
            "rmse_c": None,
            "max_abs_error_c": None,
        }
    return {
        "n_pairs": n,
        "bias_c": math.fsum(errors) / n,
        "mae_c": math.fsum(abs(x) for x in errors) / n,
        "rmse_c": math.sqrt(math.fsum(x * x for x in errors) / n),
        "max_abs_error_c": max(abs(x) for x in errors),
    }


def compare(days, lats, lons, temperatures, records, positions):
    nearest = {}
    for station, (lat, lon) in positions.items():
        # Tuple ordering gives deterministic latitude-major, longitude-major ties.
        nearest[station] = min(
            (distance_km(lat, lon, float(grid_lat), float(grid_lon)), i, j)
            for i, grid_lat in enumerate(lats)
            for j, grid_lon in enumerate(lons)
        )

    pairs = []
    excluded = {name: 0 for name in EXCLUSION_REASONS}
    for station, day, lat, lon, observed in records:
        # The order below defines the single reason for multi-fault records.
        if not math.isfinite(observed) or observed <= -999 or observed < -80 or observed > 65:
            excluded["missing_observation"] += 1
            continue
        distance, i, j = nearest[station]
        if distance > MAX_MATCH_DISTANCE_KM:
            excluded["outside_grid"] += 1
            continue
        if day not in days:
            excluded["unavailable_date"] += 1
            continue
        modeled = float(temperatures[days[day], i, j])
        if not math.isfinite(modeled):
            excluded["missing_grid"] += 1
            continue
        pairs.append({
            "station_id": station,
            "date": day,
            "station_lat": lat,
            "station_lon": lon,
            "grid_lat": float(lats[i]),
            "grid_lon": float(lons[j]),
            "distance_km": distance,
            "observed_tmax_c": observed,
            "modeled_tmax_c": modeled,
            "error_c": modeled - observed,
        })
    pairs.sort(key=lambda row: (row["station_id"], row["date"]))
    all_stations = sorted(positions)
    metrics = {
        "comparison": "modeled_tmax_c - observed_tmax_c",
        "grid_matching": "nearest great-circle (haversine) cell; no interpolation",
        "max_distance_km": MAX_MATCH_DISTANCE_KM,
        "all_stations": all_stations,
        "n_input_rows": len(records),
        "n_excluded": excluded,
        "overall": error_stats([row["error_c"] for row in pairs]),
        "by_station": {
            station: error_stats([row["error_c"] for row in pairs if row["station_id"] == station])
            for station in all_stations
        },
        "limitations": [
            "Hourly-sampled UTC maxima and station TXK may use different reporting windows.",
            "Grid-cell and point-station temperatures differ in elevation, exposure and representativeness.",
            "Synthetic inputs test algorithms, not real observational accuracy or forecast skill.",
        ],
    }
    return pairs, metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--daily", type=Path, required=True)
    parser.add_argument("--stations", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        days, lats, lons, temperatures = load_daily(args.daily)
        records, positions = load_stations(args.stations)
        pairs, metrics = compare(days, lats, lons, temperatures, records, positions)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        with (args.output_dir / "station_pairs.csv").open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=PAIR_FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(pairs)
        (args.output_dir / "metrics.json").write_text(
            json.dumps(metrics, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        print(f"Reference solution wrote {len(pairs)} pairs and {sum(metrics['n_excluded'].values())} exclusions")
    except (ValueError, TypeError, KeyError, OSError, OverflowError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
