"""Normalize local ERA5-Land NetCDF exports into the strict GeoClimateBench schema.

CDS access/download is not part of the offline demo. Downloads must be done by
users who have accepted applicable Copernicus licence and CDS terms.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr


def normalize_era5_netcdf(files: list[Path], output: Path) -> None:
    """Normalize CDS 2m temperatures using xarray, without regridding or unit guesses.

    This supports simple (valid_time|time, latitude, longitude) NetCDF exports.
    More complex CDS archives/GRIB/forecast-step formats need separate inspection.
    """
    if not files:
        raise ValueError("At least one NetCDF input file is required")
    parts = []
    for file in files:
        with xr.open_dataset(file) as original:
            ds = original.copy().load()
        if "valid_time" in ds.dims and "time" not in ds.dims:
            ds = ds.rename({"valid_time": "time"})
        if "lat" in ds.dims and "latitude" not in ds.dims:
            ds = ds.rename({"lat": "latitude"})
        if "lon" in ds.dims and "longitude" not in ds.dims:
            ds = ds.rename({"lon": "longitude"})
        if "t2m" not in ds:
            if "2m_temperature" in ds:
                ds = ds.rename({"2m_temperature": "t2m"})
            else:
                raise ValueError(f"{file} must contain t2m or 2m_temperature")
        if ds.t2m.attrs.get("units") not in ("K", "kelvin", "Kelvin"):
            raise ValueError(f"{file} must identify 2m temperature in Kelvin")
        if set(ds.t2m.dims) != {"time", "latitude", "longitude"}:
            raise ValueError(f"{file} contains unexpected dimensions: {ds.t2m.dims}")
        ds = ds[["t2m"]].transpose("time", "latitude", "longitude")
        ds = ds.sortby("latitude").sortby("longitude").sortby("time")
        parts.append(ds)
    first_lat = parts[0].latitude.values
    first_lon = parts[0].longitude.values
    for part in parts[1:]:
        if not np.array_equal(part.latitude.values, first_lat) or not np.array_equal(part.longitude.values, first_lon):
            raise ValueError("All input files must have identical grid coordinates; no implicit regridding")
    assembled = xr.concat(parts, dim="time").sortby("time")
    index = pd.DatetimeIndex(assembled.time.values)
    if index.has_duplicates or not index.is_monotonic_increasing:
        raise ValueError("Time stamps overlap or are not ordered across input files")
    assembled.attrs = {
        "time_standard": "UTC",
        "dataset_type": "User-provided ERA5-Land-like NetCDF (provenance not independently verified)",
        "processing": "Combined and sorted, without regridding, gap-filling, or interpolation.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    assembled.to_netcdf(output, engine="scipy")
