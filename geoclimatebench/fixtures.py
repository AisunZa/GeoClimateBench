"""Generate reproducible SYNTHETIC (not ERA5 or DWD) climate benchmark fixtures.

Period: Jun 24 to Aug 07 inclusive, each 1991-2020; Jul 2022 evaluation.
Temperature has realistic structure for algorithm testing but no observational validity.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from .science import daily_max_from_hourly

LAT = np.array([47.5, 49.0, 50.5, 52.0, 53.5], dtype=float)
LON = np.array([7.5, 9.5, 11.5, 13.5], dtype=float)


def make_synthetic_dataset(seed: int = 2026) -> xr.Dataset:
    """Deterministic ERA5-*like* hourly temperatures in kelvin, never actual ERA5 data."""
    rng = np.random.default_rng(seed)
    blocks = [
        pd.date_range(f"{year}-06-24", f"{year}-08-07 23:00", freq="h")
        for year in range(1991, 2021)
    ]
    blocks.append(pd.date_range("2022-07-01", "2022-07-31 23:00", freq="h"))
    time = blocks[0].append(blocks[1:])
    nh = len(time)
    lat2d, lon2d = np.meshgrid(LAT, LON, indexing="ij")
    day_of_july = (time.dayofyear.to_numpy() - 182).astype(float)
    # The diurnal cycle peaks near 15:00 UTC. Long-term warmth varies by region.
    daily_phase = 5.5 * np.cos(2 * np.pi * (time.hour.to_numpy() - 15) / 24)
    seasonality = 2.0 * np.sin(2 * np.pi * day_of_july / 45)
    spatial = (50.5 - lat2d) * 0.65 + (lon2d - 10.5) * 0.12
    hour_noise = rng.normal(0, 0.23, size=(nh, len(LAT), len(LON))).astype("float32")
    year_shift = np.asarray([(x.year - 1991) * 0.018 if x.year != 2022 else 1.2 for x in time])
    base_c = (25.0 + daily_phase + seasonality + year_shift)[:, None, None] + spatial[None, :, :]
    t2m = (base_c + hour_noise + 273.15).astype("float32")
    # Inject a sustained, unambiguous heatwave at a particular grid cell.
    target_hot = (time >= "2022-07-14") & (time < "2022-07-23")
    t2m[np.asarray(target_hot), 3, 3] += 10.0
    t2m[np.asarray(target_hot), 2, 2] += 7.0
    # Missing values and scientifically invalid extreme values exercise QC.
    at = np.flatnonzero(np.asarray(time == pd.Timestamp("2022-07-06 01:00")))[0]
    t2m[at, 0, 0] = np.nan
    at = np.flatnonzero(np.asarray(time == pd.Timestamp("2022-07-06 04:00")))[0]
    t2m[at, 0, 0] = 999.0  # must not contaminate daily max
    # A whole target cell/day has only 17 acceptable hours and must be masked.
    mask = (time >= "2022-07-10") & (time < "2022-07-10 07:00")
    t2m[np.asarray(mask), 4, 0] = np.nan
    return xr.Dataset(
        {"t2m": (("time", "latitude", "longitude"), t2m, {"units": "K", "long_name": "Synthetic two-metre air temperature"})},
        coords={"time": time.to_numpy(dtype="datetime64[ns]"), "latitude": LAT, "longitude": LON},
        attrs={
            "dataset_type": "SYNTHETIC FIXTURE — NOT ERA5-Land",
            "seed": seed,
            "time_standard": "UTC",
            "description": "Deterministic teaching/benchmark fixture; not suitable for climate inference.",
        },
    )


def make_synthetic_stations(hourly_ds: xr.Dataset, seed: int = 701) -> pd.DataFrame:
    """Create fake stations independently perturbed from gridded values.

    These are *not DWD observations* and must not be presented as observations.
    """
    rng = np.random.default_rng(seed)
    grid = daily_max_from_hourly(hourly_ds)
    stations = [
        ("SYN-BERLIN", 52.1, 13.3),
        ("SYN-FRANKFURT", 50.4, 9.4),
        ("SYN-MUNICH", 48.9, 11.4),
        ("SYN-HAMBURG", 53.4, 9.6),
        # This location deliberately lies too far outside the grid to match.
        ("SYN-OUTSIDE", 60.0, 17.0),
    ]
    rows = []
    from .validation import find_closest_grid_cell

    for sid, lat, lon in stations:
        ilat, ilon, _ = find_closest_grid_cell(grid.latitude.values, grid.longitude.values, lat, lon)
        for date in pd.date_range("2022-07-01", "2022-07-31", freq="D"):
            reference = float(grid.tmax_c.sel(time=date).isel(latitude=ilat, longitude=ilon))
            offset = 0.75 if sid == "SYN-BERLIN" else -0.3
            observation = reference + offset + rng.normal(0, 0.75)
            if not np.isfinite(reference):
                observation = 26.0  # candidate must handle a missing grid value
            if sid == "SYN-MUNICH" and date.day == 12:
                observation = -999.0  # missing sentinel
            if sid == "SYN-BERLIN" and date.day == 24:
                observation += 6.0  # anomalous but valid; must not be silently removed
            rows.append((sid, date.date().isoformat(), lat, lon, round(observation, 3)))
    return pd.DataFrame(rows, columns=["station_id", "date", "latitude", "longitude", "txk_c"])


def generate_fixtures(folder: str | Path) -> None:
    path = Path(folder)
    path.mkdir(parents=True, exist_ok=True)
    ds = make_synthetic_dataset()
    # NetCDF-3 (SciPy) avoids requiring a native h5netcdf/netCDF4 package.
    ds.to_netcdf(path / "hourly_synthetic.nc", engine="scipy")
    make_synthetic_stations(ds).to_csv(path / "stations_synthetic.csv", index=False)
    (path / "PROVENANCE.txt").write_text(
        "SYNTHETIC FIXTURES (NOT ERA5, NOT DWD).\n"
        "Generated by geoclimatebench.fixtures with fixed PRNG seeds.\n"
        "Use only for algorithm verification, education and offline benchmark tests.\n",
        encoding="utf-8",
    )
