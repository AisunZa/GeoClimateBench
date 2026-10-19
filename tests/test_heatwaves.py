import numpy as np
import pandas as pd
import pytest
import xarray as xr

from geoclimatebench.science import compute_extremes, _mark_events, _noleap_day_of_year


def small_daily():
    baseline1 = pd.date_range("1991-07-01", periods=31, freq="D")
    baseline2 = pd.date_range("1992-07-01", periods=31, freq="D")
    target = pd.date_range("2022-07-01", periods=31, freq="D")
    times = baseline1.append([baseline2, target])
    vals = np.concatenate([np.zeros(31), np.full(31, 10.0), np.full(31, 8.0)])
    vals[-31 + 11:-31 + 16] = 12.0  # 2022 Jul 12-16 inclusive
    vals[-31 + 7] = 9.0  # equals threshold, must NOT count
    return xr.Dataset(
        {"tmax_c": (("time", "latitude", "longitude"), vals[:, None, None])},
        coords={"time": times, "latitude": [50.0], "longitude": [10.0]},
    )


def test_known_quantile_tie_and_full_five_day_event():
    data = compute_extremes(
        small_daily(), baseline_start=1991, baseline_end=1992,
        window_days=0, min_baseline_samples=2, min_baseline_years=2,
    )
    assert np.allclose(data.threshold_c.values, 9.0)
    assert np.all(data.baseline_samples.values == 2)
    assert np.all(data.baseline_years.values == 2)
    assert data.exceedance_day.values[7, 0, 0] == 0
    assert data.heatwave_day.values[11:16, 0, 0].tolist() == [1] * 5
    assert data.event_count.item() == 1
    assert data.heatwave_days.item() == 5
    assert data.max_event_length.item() == 5


def test_break_event_with_missing_day():
    daily = small_daily()
    daily.tmax_c.values[-31 + 13, 0, 0] = np.nan
    out = compute_extremes(daily, baseline_start=1991, baseline_end=1992, window_days=0, min_baseline_samples=2, min_baseline_years=2)
    assert out.event_count.item() == 0
    assert out.heatwave_days.item() == 0


def test_low_baseline_coverage_returns_nan_threshold():
    out = compute_extremes(small_daily(), baseline_start=1991, baseline_end=1992, window_days=0, min_baseline_samples=3, min_baseline_years=2)
    assert np.isnan(out.threshold_c.values).all()
    assert not out.exceedance_day.values.any()


def test_calendar_day_leap_mapping():
    assert _noleap_day_of_year(pd.Timestamp("1992-07-01")) == _noleap_day_of_year(pd.Timestamp("1991-07-01"))
    with pytest.raises(ValueError, match="Feb 29"):
        _noleap_day_of_year(pd.Timestamp("2000-02-29"))


def test_date_gaps_split_runs():
    dates = pd.DatetimeIndex([*pd.date_range("2022-07-01", periods=3), *pd.date_range("2022-07-06", periods=3)])
    flags, n, longest = _mark_events(np.ones(6, dtype=bool), dates, min_days=3)
    assert n == 2 and longest == 3
    assert flags.tolist() == [True] * 6


def test_reject_missing_target_dates():
    ds = small_daily().sel(time=small_daily().time != np.datetime64("2022-07-05"))
    with pytest.raises(ValueError, match="all daily timestamps"):
        compute_extremes(ds, baseline_start=1991, baseline_end=1992, window_days=0, min_baseline_samples=2, min_baseline_years=2)
