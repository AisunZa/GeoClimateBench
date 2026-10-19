"""Independent station-to-grid pairing and transparent error statistics (task 3)."""
from pathlib import Path
import json

import numpy as np
import pandas as pd
import xarray as xr

from .science import _grid_check

PAIRS_COLUMNS = [
    "station_id", "date", "station_lat", "station_lon", "grid_lat", "grid_lon",
    "distance_km", "observed_tmax_c", "modeled_tmax_c", "error_c",
]


def _haversine_km(lat1, lon1, lat2, lon2):
    """Vectorized great-circle distance; spherical approximation with 6371.0088 km Earth radius."""
    la1, la2 = np.radians(lat1), np.radians(lat2)
    dlat = la2 - la1
    dlon = np.radians(lon2) - np.radians(lon1)
    a = np.sin(dlat / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin(dlon / 2) ** 2
    return 2 * 6371.0088 * np.arcsin(np.minimum(1.0, np.sqrt(a)))


def find_closest_grid_cell(latitudes, longitudes, lat, lon) -> tuple[int, int, float]:
    """Nearest by haversine distance, not independent nearest latitude/longitude."""
    lat_grid, lon_grid = np.meshgrid(latitudes, longitudes, indexing="ij")
    distance = _haversine_km(float(lat), float(lon), lat_grid, lon_grid)
    a, b = np.unravel_index(np.argmin(distance), distance.shape)
    return int(a), int(b), float(distance[a, b])


def _metrics(values: np.ndarray) -> dict:
    values = np.asarray(values, dtype="float64")
    if not len(values):
        return {"n_pairs": 0, "bias_c": None, "mae_c": None, "rmse_c": None, "max_abs_error_c": None}
    return {
        "n_pairs": int(len(values)),
        "bias_c": float(np.mean(values)),
        "mae_c": float(np.mean(np.abs(values))),
        "rmse_c": float(np.sqrt(np.mean(values ** 2))),
        "max_abs_error_c": float(np.max(np.abs(values))),
    }


def compare_stations(daily: xr.Dataset, stations: pd.DataFrame, max_distance_km: float = 180.0):
    """Compare daily maximum from hourly UTC grid with TXK-like input.

    No outlier trimming, no gap filling, no correction for mismatch in observation
    periods, elevation, station exposure, gridding or temporal representativity.
    """
    _grid_check(daily, "tmax_c")
    if max_distance_km <= 0:
        raise ValueError("max_distance_km must be positive")
    required = {"station_id", "date", "latitude", "longitude", "txk_c"}
    if not required.issubset(stations.columns):
        raise ValueError(f"Station CSV must contain {sorted(required)}")
    data = stations.copy()
    if data[["station_id", "date"]].duplicated().any():
        raise ValueError("Duplicate station_id/date observations are not allowed")
    data["date"] = pd.to_datetime(data["date"], errors="raise").dt.normalize()
    if data[["station_id", "date"]].duplicated().any():
        raise ValueError("Duplicate station_id/date after date parsing")
    for col in ("latitude", "longitude", "txk_c"):
        data[col] = pd.to_numeric(data[col], errors="raise")
    if data[["latitude", "longitude"]].isna().any().any():
        raise ValueError("Station coordinates cannot be missing")
    if ((data.latitude.abs() > 90) | (data.longitude.abs() > 180)).any():
        raise ValueError("Station coordinates exceed geographic bounds")
    if (data.groupby("station_id")[["latitude", "longitude"]].nunique() > 1).any().any():
        raise ValueError("Coordinates must remain constant per station")
    data = data.sort_values(["station_id", "date"]).reset_index(drop=True)
    grid_dates = pd.DatetimeIndex(daily.time.values)
    index_of_day = {pd.Timestamp(date): i for i, date in enumerate(grid_dates)}
    station_cells = {}
    for sid, group in data.groupby("station_id", sort=True):
        first = group.iloc[0]
        station_cells[sid] = find_closest_grid_cell(
            daily.latitude.values, daily.longitude.values,
            first.latitude, first.longitude,
        )
    excluded = {"missing_observation": 0, "outside_grid": 0, "unavailable_date": 0, "missing_grid": 0}
    rows = []
    for r in data.itertuples(index=False):
        observed = float(r.txk_c)
        if not np.isfinite(observed) or observed <= -999 or observed < -80 or observed > 65:
            excluded["missing_observation"] += 1
            continue
        i_lat, i_lon, distance = station_cells[r.station_id]
        if distance > max_distance_km:
            excluded["outside_grid"] += 1
            continue
        idx = index_of_day.get(r.date)
        if idx is None:
            excluded["unavailable_date"] += 1
            continue
        model = float(daily.tmax_c.values[idx, i_lat, i_lon])
        if not np.isfinite(model):
            excluded["missing_grid"] += 1
            continue
        rows.append((
            str(r.station_id), r.date.strftime("%Y-%m-%d"), float(r.latitude), float(r.longitude),
            float(daily.latitude.values[i_lat]), float(daily.longitude.values[i_lon]),
            round(distance, 6), observed, model, model - observed,
        ))
    pairs = pd.DataFrame(rows, columns=PAIRS_COLUMNS).sort_values(["station_id", "date"]).reset_index(drop=True)
    by_station = {str(sid): _metrics(g.error_c.values) for sid, g in pairs.groupby("station_id")}
    metrics = {
        "comparison": "modeled_tmax_c - observed_tmax_c",
        "grid_matching": "nearest great-circle (haversine) cell; no interpolation",
        "max_distance_km": max_distance_km,
        "all_stations": sorted(map(str, data.station_id.unique())),
        "n_input_rows": int(len(data)),
        "n_excluded": excluded,
        "overall": _metrics(pairs.error_c.values),
        "by_station": by_station,
        "limitations": [
            "Hourly UTC maximum is not guaranteed to match the DWD TXK measurement-day definition.",
            "Grid-cell temperature and point measurements differ in height, terrain and exposure.",
            "Uncorrected nearest-neighbor matching can create representativeness error.",
            "Synthetic demo observations are not independent real-world validation.",
        ],
    }
    return pairs, metrics


def save_station_outputs(pairs: pd.DataFrame, metrics: dict, folder: str | Path) -> None:
    out = Path(folder)
    out.mkdir(parents=True, exist_ok=True)
    pairs.to_csv(out / "station_pairs.csv", index=False, float_format="%.6f")
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
