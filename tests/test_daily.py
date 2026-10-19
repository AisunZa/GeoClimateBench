import numpy as np
import pandas as pd
import pytest
import xarray as xr

from geoclimatebench.science import daily_max_from_hourly


def hourly_one_day():
    dates = pd.date_range("2022-07-01", periods=24, freq="h")
    values = np.full((24, 1, 1), 293.15)
    values[12, 0, 0] = 305.15
    values[5, 0, 0] = 999  # exclude an impossible outlier
    return xr.Dataset(
        {"t2m": (("time", "latitude", "longitude"), values, {"units": "K"})},
        coords={"time": dates, "latitude": [50.0], "longitude": [10.0]},
        attrs={"time_standard": "UTC"},
    )


def test_known_hourly_max_and_outlier_rejection():
    result = daily_max_from_hourly(hourly_one_day())
    assert result.tmax_c.item() == pytest.approx(32.0, abs=1e-5)
    assert result.hours_valid.item() == 23
    assert result.tmax_c.attrs["units"] == "degC"


def test_reject_invalid_units():
    ds = hourly_one_day()
    ds.t2m.attrs["units"] = "degC"
    with pytest.raises(ValueError, match="units"):
        daily_max_from_hourly(ds)


def test_reject_ambiguous_time_zone():
    ds = hourly_one_day()
    del ds.attrs["time_standard"]
    with pytest.raises(ValueError, match="UTC"):
        daily_max_from_hourly(ds)


def test_reject_duplicate_hours():
    ds = hourly_one_day()
    ds = ds.assign_coords(time=[ds.time.values[0], *ds.time.values[:-1]])
    with pytest.raises(ValueError, match="unique"):
        daily_max_from_hourly(ds)


def test_minimum_coverage_masks_day():
    ds = hourly_one_day()
    ds.t2m.values[:8, 0, 0] = np.nan  # 16 valid hours remain (the invalid hour is among those masked)
    result = daily_max_from_hourly(ds)
    assert np.isnan(result.tmax_c.item())
    assert result.hours_valid.item() == 16


def test_multiple_nonadjacent_dates_no_phantom_days():
    ds = hourly_one_day()
    next_week = ds.assign_coords(time=ds.time.values + np.timedelta64(7, "D"))
    combined = xr.concat([ds, next_week], dim="time")
    result = daily_max_from_hourly(combined)
    assert result.sizes["time"] == 2
