"""Task-04 tests use synthetic unit fixtures, NEVER pretend these are real ERA5/DWD data."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from geoclimatebench.realdata_grader import RealDataGradingError, grade_real_berlin


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    root = tmp_path_factory.mktemp("task04")
    days = pd.date_range("2022-07-01", periods=31, freq="D")
    hours = pd.date_range("2022-07-01", periods=744, freq="h")
    lats = [52.4, 52.5]
    lons = [13.3, 13.4]
    # Deliberately vary within each day and across cells; no missing samples.
    t = np.arange(744, dtype=float)
    values = np.empty((744, 2, 2), dtype="float32")
    for i in range(2):
        for j in range(2):
            values[:, i, j] = (
                292 + 5 * np.sin(2 * np.pi * (t % 24) / 24)
                + .15 * (t // 24) + i * 1.1 + j * .7
            )
    hourly = root / "hourly.nc"
    ds = xr.Dataset({"t2m": (("time", "latitude", "longitude"), values,
                             {"units": "K"})},
                    coords={"time": hours, "latitude": lats, "longitude": lons},
                    attrs={"time_standard": "UTC"})
    ds.to_netcdf(hourly, engine="scipy")

    obs = np.round(values.reshape(31, 24, 2, 2)[:, :, 1, 1].max(axis=1) - 273.15 + 1.2, 1)
    station = pd.DataFrame({
        "station_id": ["00433"] * 31,
        "date": days.strftime("%Y-%m-%d"),
        "latitude": [52.4675] * 31,
        "longitude": [13.4021] * 31,
        "txk_c": obs,
    })
    station_csv = root / "dwd.csv"
    station.to_csv(station_csv, index=False)
    archive = root / "original.zip"
    original = pd.DataFrame({
        "STATIONS_ID": ["433"] * 31,
        "MESS_DATUM": days.strftime("%Y%m%d"),
        "TXK": obs,
        "QN_4": [9] * 31,
    })
    metadata = ("433;20010401;20260418;Berlin-Tempelhof;TXK;Daily 2m max;°C;"
                "source;00:00 - 24:00 UTC gemessen;;;eor;\n")
    with ZipFile(archive, "w") as zf:
        zf.writestr("produkt_klima_tag_00433.txt", original.to_csv(sep=";", index=False))
        zf.writestr("Metadaten_Parameter_klima_tag_00433.txt", metadata)

    output = root / "reference"
    script = Path(__file__).resolve().parents[1] / "scripts" / "compare_real_july2022.py"
    cmd = [sys.executable, str(script), "--hourly", str(hourly), "--stations",
           str(station_csv), "--dwd-archive", str(archive), "--output", str(output)]
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo) + os.pathsep + env.get("PYTHONPATH", "")
    process = subprocess.run(cmd, text=True, capture_output=True, check=False,
                             cwd=repo, env=env)
    assert process.returncode == 0, process.stdout + process.stderr
    return hourly, station_csv, archive, output


def evaluate(inputs, out):
    hourly, stations, archive, _ = inputs
    return grade_real_berlin(hourly=hourly, stations=stations, archive=archive, output=out)


def cloned_output(sample, tmp_path):
    output = tmp_path / "submission"
    shutil.copytree(sample[3], output)
    return output


def test_real_task_grades_correct_source_derived_results(sample):
    report = evaluate(sample, sample[3])
    assert report["status"] == "PASS"
    assert report["checks_passed"] == 4
    assert report["n_station_days"] == 31


def test_bad_pair_residual_is_rejected(sample, tmp_path):
    output = cloned_output(sample, tmp_path)
    csv = output / "station_pairs.csv"
    pairs = pd.read_csv(csv, dtype={"station_id": str})
    pairs.loc[0, "error_c"] += 0.4
    pairs.to_csv(csv, index=False)
    with pytest.raises(RealDataGradingError, match="incorrect error_c"):
        evaluate(sample, output)


def test_inaccurate_rmse_is_rejected(sample, tmp_path):
    output = cloned_output(sample, tmp_path)
    f = output / "metrics.json"
    obj = json.loads(f.read_text())
    obj["overall"]["rmse_c"] += 0.5
    f.write_text(json.dumps(obj), encoding="utf-8")
    with pytest.raises(RealDataGradingError, match="overall.rmse_c"):
        evaluate(sample, output)


def test_untrue_provenance_hash_is_rejected(sample, tmp_path):
    output = cloned_output(sample, tmp_path)
    f = output / "real_run_metadata.json"
    obj = json.loads(f.read_text())
    obj["datasets"]["hourly_sha256"] = "invalid"
    f.write_text(json.dumps(obj), encoding="utf-8")
    with pytest.raises(RealDataGradingError, match="hourly_sha256"):
        evaluate(sample, output)


def test_untrue_quality_flag_is_rejected(sample, tmp_path):
    output = cloned_output(sample, tmp_path)
    f = output / "real_run_metadata.json"
    obj = json.loads(f.read_text())
    obj["dwd_source_checks"]["qn_4_counts"] = {"10": 31}
    f.write_text(json.dumps(obj), encoding="utf-8")
    with pytest.raises(RealDataGradingError, match="QN_4 counts mismatch"):
        evaluate(sample, output)


def test_corrupt_daily_max_is_rejected(sample, tmp_path):
    output = cloned_output(sample, tmp_path)
    f = output / "daily_max.nc"
    with xr.open_dataset(f) as ds:
        modified = ds.load()
    modified["tmax_c"].values[0, 0, 0] += 1.0
    modified.to_netcdf(f, engine="scipy", mode="w")
    with pytest.raises(RealDataGradingError, match="incorrect sampled daily maxima"):
        evaluate(sample, output)


def test_wrong_dwd_measurement_day_fails(sample, tmp_path):
    hourly, csv, zf, output = sample
    altered = tmp_path / "changed.zip"
    with ZipFile(zf) as src, ZipFile(altered, "w") as dest:
        for member in src.namelist():
            body = src.read(member)
            if "metadaten" in member.lower():
                body = body.replace(b"00:00 - 24:00 UTC gemessen", b"21:30 to 21:30 CET")
            dest.writestr(member, body)
    with pytest.raises(ValueError, match="Unexpected 2022 DWD TXK measurement window"):
        grade_real_berlin(hourly=hourly, stations=csv, archive=altered, output=output)
