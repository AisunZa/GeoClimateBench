from io import BytesIO
from zipfile import ZipFile

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from geoclimatebench.dwd import parse_dwd_daily_zip
from geoclimatebench.validation import compare_stations, find_closest_grid_cell


def tiny_daily():
    return xr.Dataset({"tmax_c": (("time", "latitude", "longitude"), np.array([[[20.0]], [[30.0]]]))},
                      coords={"time": pd.date_range("2022-07-01", periods=2), "latitude": [50.0], "longitude": [10.0]})


def tiny_stations():
    return pd.DataFrame({"station_id": ["X", "X", "Y", "Z"],
                         "date": ["2022-07-01", "2022-07-02", "2022-07-01", "2022-07-01"],
                         "latitude": [50., 50., 50., 60.], "longitude": [10., 10., 10., 20.],
                         "txk_c": [18., 32., -999., 18.]})


def test_exact_matching_rmse_and_exclusions():
    pairs, metrics = compare_stations(tiny_daily(), tiny_stations())
    assert len(pairs) == 2
    assert np.allclose(pairs.error_c.values, [2, -2])
    assert metrics["overall"]["bias_c"] == pytest.approx(0)
    assert metrics["overall"]["rmse_c"] == pytest.approx(2)
    assert metrics["overall"]["mae_c"] == pytest.approx(2)
    assert metrics["n_excluded"]["missing_observation"] == 1
    assert metrics["n_excluded"]["outside_grid"] == 1
    assert sum(metrics["n_excluded"].values()) + len(pairs) == metrics["n_input_rows"]


def test_closest_grid_point_is_geodesic():
    i, j, distance = find_closest_grid_cell([49., 50.], [10., 11.], 49., 10.)
    assert (i, j) == (0, 0)
    assert distance == pytest.approx(0)


def test_reject_duplicate_station_dates():
    st = pd.concat([tiny_stations(), tiny_stations().iloc[:1]], ignore_index=True)
    with pytest.raises(ValueError, match="Duplicate"):
        compare_stations(tiny_daily(), st)


def test_dwd_zip_parse_preserves_missing_as_nan(tmp_path):
    zpath = tmp_path / "one.zip"
    with ZipFile(zpath, "w") as archive:
        archive.writestr("produkt_klima_tag_20220101_20221231_00433.txt", "STATIONS_ID;MESS_DATUM;TXK;eor\n433;20220701;33.2;eor\n433;20220702;-999;eor\n433;20220601;25.0;eor\n")
    got = parse_dwd_daily_zip(zpath, station_lat=52.2, station_lon=13.1)
    assert len(got) == 2
    assert got.station_id.iloc[0] == "00433"
    assert got.txk_c.iloc[0] == pytest.approx(33.2)
    assert np.isnan(got.txk_c.iloc[1])
