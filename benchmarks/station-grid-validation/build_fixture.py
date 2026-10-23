"""Build portable, deterministic, SYNTHETIC station-grid benchmark inputs.

Writes identical NetCDF and CSV input bytes to the agent and verifier build
contexts; no external datasets or GeoClimateBench production code required.
"""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

ROOT = Path(__file__).resolve().parent
LATITUDES = np.array([47.5, 49.0, 50.5, 52.0, 53.5], dtype=np.float64)
LONGITUDES = np.array([7.5, 9.5, 11.5, 13.5], dtype=np.float64)
STATIONS = (
    ("SYN-BERLIN", 52.1, 13.3, 3, 3, 0.7),
    ("SYN-FRANKFURT", 50.4, 9.4, 2, 1, -0.3),
    ("SYN-MUNICH", 48.9, 11.4, 1, 2, 0.2),
    ("SYN-HAMBURG", 53.4, 9.6, 4, 1, -0.4),
    ("SYN-OUTSIDE", 60.0, 17.0, None, None, 0.0),
)


def build():
    dates = pd.date_range("2022-07-01", "2022-07-31", freq="D")
    day = np.arange(len(dates), dtype=np.float64)[:, None, None]
    lat = LATITUDES[None, :, None]
    lon = LONGITUDES[None, None, :]
    # Analytic temperatures, not observations and not ERA5 output.
    values = (26.0 + 3.4 * np.sin(2 * np.pi * day / 15.0)
              + 0.6 * (50.5 - lat) + 0.14 * (lon - 10.5)).astype(np.float32)
    values[9, 4, 1] = np.nan  # missing model temperature for SYN-HAMBURG July 10
    values[15, 3, 3] = np.nan  # missing model temperature for SYN-BERLIN July 16
    ds = xr.Dataset(
        {"tmax_c": (("time", "latitude", "longitude"), values,
                    {"units": "degC"})},
        coords={"time": dates, "latitude": LATITUDES, "longitude": LONGITUDES},
        attrs={"time_standard": "UTC", "source_type": "SYNTHETIC ONLY; NOT ERA5-Land or DWD"},
    )
    rows = []
    for sid, slat, slon, ilat, ilon, bias in STATIONS:
        for index, timestamp in enumerate(dates):
            date_text = timestamp.strftime("%Y-%m-%d")
            reference = (float(values[index, ilat, ilon]) if ilat is not None else 25.0)
            if not np.isfinite(reference):
                reference = 26.0  # keep a valid observation when model is missing
            observed = round(reference + bias + 0.65 * np.sin((index + 2) * 0.9), 3)
            if sid == "SYN-MUNICH" and index == 11:
                observed = -999.0
            if sid == "SYN-FRANKFURT" and index == 14:
                observed = "nan"
            if sid == "SYN-BERLIN" and index == 23:
                observed = round(float(observed) + 6.0, 3)  # valid high-error outlier
            rows.append((sid, date_text, slat, slon, observed))
    # Additional unavailable-grid-date record, without station-coordinate changes.
    rows.append(("SYN-FRANKFURT", "2022-08-01", 50.4, 9.4, 27.0))
    rows.sort(key=lambda row: (row[0], row[1]))

    paths = []
    for folder in (ROOT / "environment" / "data", ROOT / "tests" / "data"):
        folder.mkdir(parents=True, exist_ok=True)
        nc_path = folder / "daily_max.nc"
        csv_path = folder / "stations_synthetic.csv"
        ds.to_netcdf(nc_path, engine="scipy")
        with csv_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(["station_id", "date", "latitude", "longitude", "txk_c"])
            writer.writerows(rows)
        paths.append((nc_path, csv_path))
    for i in (0, 1):
        checksums = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths[i]]
        print(f"{'Agent' if i == 0 else 'Verifier'} input checksums: {checksums}")
    assert all(paths[0][j].read_bytes() == paths[1][j].read_bytes() for j in (0, 1))
    print(f"PASS: identical agent/verifier inputs; {len(rows)} synthetic station rows, {len(dates)} grid dates")


if __name__ == "__main__":
    build()
