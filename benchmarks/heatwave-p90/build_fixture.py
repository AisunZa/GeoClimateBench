"""Rebuild deterministic synthetic heatwave task input. Not copied into agent image."""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
import xarray as xr

ROOT = Path(__file__).resolve().parent


def build(seed: int = 104) -> xr.Dataset:
    blocks = [pd.date_range(f"{year}-06-24", f"{year}-08-07", freq="D")
              for year in range(1991, 2021)]
    blocks.append(pd.date_range("2022-07-01", "2022-07-31", freq="D"))
    time = blocks[0].append(blocks[1:])
    rng = np.random.default_rng(seed)
    year = time.year.to_numpy()
    idx = time.dayofyear.to_numpy()
    seasonal = 1.3 * np.sin(2 * np.pi * (idx - 201) / 46)
    space = np.array([[0.0, 0.7], [-0.8, 0.3]])
    shift = np.where(year == 2022, -1.1, 0.035 * (year - 1991))
    values = 27.2 + seasonal[:, None, None] + shift[:, None, None] + space
    values = values + rng.normal(0, 0.25, size=values.shape)
    target = year == 2022
    day = time.day.to_numpy()
    values[target & (day >= 19) & (day <= 24), 0, 0] += 9.0  # 6-day event
    values[target & (day >= 8) & (day <= 12), 0, 1] += 9.0   # exactly 5 days
    values[target & (day >= 13) & (day <= 16), 1, 1] += 9.0  # 4 days: no event
    values[target & (day >= 21) & (day <= 28), 1, 1] += 9.0  # broken by NaN
    values[target & (day == 24), 1, 1] = np.nan
    # 20 complete baseline years: exactly 300 samples (window=15 days).
    values[(year >= 1991) & (year <= 2000), 0, 1] = np.nan
    # Only 15 baseline years: threshold ineligible for this grid cell.
    values[(year >= 1991) & (year <= 2005), 1, 0] = np.nan
    # Single missing baseline sample, exercising date-specific sample counts.
    missing = np.asarray(time == pd.Timestamp("1999-07-04"))
    values[missing, 1, 1] = np.nan
    return xr.Dataset(
        {"tmax_c": (("time", "latitude", "longitude"), values.astype(np.float32),
                    {"units": "degC", "long_name": "Synthetic sampled daily maximum temperature"})},
        coords={"time": time.to_numpy(dtype="datetime64[ns]"),
                "latitude": [45., 52.], "longitude": [7., 13.]},
        attrs={"time_standard": "UTC", "dataset_type": "SYNTHETIC — not observational",
               "description": "Deterministic algorithm test, no climatic inference"},
    )


if __name__ == "__main__":
    ds = build()
    for folder in (ROOT / "environment" / "data", ROOT / "tests" / "data"):
        folder.mkdir(parents=True, exist_ok=True)
        ds.to_netcdf(folder / "daily_synthetic.nc", engine="scipy")
    print("Wrote identical synthetic NetCDF inputs for agent and isolated verifier")
