import json
import numpy as np
import pandas as pd
import pytest
import xarray as xr

from geoclimatebench.cli import run_pipeline
from geoclimatebench.era5 import normalize_era5_netcdf
from geoclimatebench.evaluate import grade, GradingError
from geoclimatebench.fixtures import generate_fixtures, make_synthetic_dataset, make_synthetic_stations


@pytest.fixture(scope="module")
def populated(tmp_path_factory):
    root = tmp_path_factory.mktemp("full")
    generate_fixtures(root / "data")
    run_pipeline(root / "data/hourly_synthetic.nc", root / "data/stations_synthetic.csv", root / "out", plots=False)
    return root


def test_full_oracle_grades_pass(populated):
    assert grade(populated / "out", populated / "data")["passed"] == 3


def test_changing_event_count_detected(populated):
    output = populated / "out/heatwaves.nc"
    with xr.open_dataset(output) as infile:
        ds = infile.load()
    backup = output.read_bytes()
    try:
        ds.event_count.values[0, 0] += 1
        ds.to_netcdf(output, engine="scipy")
        with pytest.raises(GradingError, match="event_count"):
            grade(populated / "out", populated / "data")
    finally:
        output.write_bytes(backup)


def test_synthetic_dataset_is_deterministic():
    first = make_synthetic_dataset(seed=2026).t2m.values
    second = make_synthetic_dataset(seed=2026).t2m.values
    assert np.array_equal(first, second, equal_nan=True)


def test_reference_includes_injected_heatwave(populated):
    with xr.open_dataset(populated / "out/heatwaves.nc") as ds:
        assert ds.heatwave_days.sel(latitude=52.0, longitude=13.5).item() >= 9


def test_era5_normalization_from_valid_time(tmp_path):
    time = pd.date_range("2022-07-01", periods=3, freq="h")
    raw = xr.Dataset({"t2m": (("valid_time", "latitude", "longitude"), np.full((3, 2, 1), 299.0), {"units": "K"})},
                     coords={"valid_time": time, "latitude": [51.0, 50.0], "longitude": [10.0]})
    source = tmp_path / "source.nc"
    raw.to_netcdf(source, engine="scipy")
    target = tmp_path / "normalized.nc"
    normalize_era5_netcdf([source], target)
    with xr.open_dataset(target) as done:
        assert list(done.latitude.values) == [50.0, 51.0]
        assert "time" in done.dims
        assert done.attrs["time_standard"] == "UTC"
