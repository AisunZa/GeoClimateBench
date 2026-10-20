import numpy as np
import pandas as pd
import xarray as xr

from geoclimatebench.science import daily_max_from_hourly


def test_valid_hour_counts_survive_netcdf_roundtrip(tmp_path):
    hourly = xr.Dataset(
        {
            "t2m": (
                ("time", "latitude", "longitude"),
                np.full((24, 1, 1), 293.15),
                {"units": "K"},
            )
        },
        coords={
            "time": pd.date_range("2022-07-01", periods=24, freq="h"),
            "latitude": [52.5],
            "longitude": [13.4],
        },
        attrs={"time_standard": "UTC"},
    )

    daily = daily_max_from_hourly(hourly)
    path = tmp_path / "daily_max.nc"
    daily.to_netcdf(path, engine="scipy")

    with xr.open_dataset(path, engine="scipy") as result:
        assert result.hours_valid.dtype.kind in "iu"
        assert result.hours_valid.attrs["units"] == "1"
        assert result.hours_valid.item() == 24
