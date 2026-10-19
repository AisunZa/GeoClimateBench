"""Independent tests for DWD archive-level QC and TXK time-window checks."""
import io
from zipfile import ZipFile

import pandas as pd
import pytest

from geoclimatebench.realdata_qc import verified_berlin_july2022


def make_inputs(tmp_path, window="00:00 - 24:00 UTC gemessen", change_value=False):
    days = pd.date_range("2022-07-01", periods=31, freq="D")
    original = pd.DataFrame({
        "STATIONS_ID": ["433"] * 31,
        "MESS_DATUM": [d.strftime("%Y%m%d") for d in days],
        "TXK": [20.0 + 0.1 * i for i in range(31)],
        "QN_4": [9] * 31,
    })
    imported = pd.DataFrame({
        "station_id": ["00433"] * 31,
        "date": [d.strftime("%Y-%m-%d") for d in days],
        "txk_c": [20.0 + 0.1 * i for i in range(31)],
    })
    if change_value:
        imported.loc[0, "txk_c"] = 99.0
    csv = tmp_path / "dwd.csv"
    imported.to_csv(csv, index=False)
    zipfile = tmp_path / "dwd.zip"
    with ZipFile(zipfile, "w") as archive:
        archive.writestr("produkt_klima_tag_00433.txt", original.to_csv(index=False, sep=";"))
        archive.writestr(
            "Metadaten_Parameter_klima_tag_00433.txt",
            "433;20010401;20260418;Berlin-Tempelhof;TXK;Daily 2m max;°C;source;" + window + ";;;eor;\n"
        )
    return zipfile, csv


def test_utc_metadata_qn_and_source_integrity(tmp_path):
    zipfile, csv = make_inputs(tmp_path)
    result = verified_berlin_july2022(zipfile, csv)
    assert result["n_station_days"] == 31
    assert result["txk_measurement_window_utc_aligned"] is True
    assert result["qn_4_counts"] == {"9": 31}
    assert result["source_txk_matches_imported_csv"] is True


def test_wrong_day_window_fails_closed(tmp_path):
    zipfile, csv = make_inputs(tmp_path, window="21:30 to 21:30 CET")
    with pytest.raises(ValueError, match="Unexpected 2022 DWD TXK measurement window"):
        verified_berlin_july2022(zipfile, csv)


def test_changed_imported_temperature_is_detected(tmp_path):
    zipfile, csv = make_inputs(tmp_path, change_value=True)
    with pytest.raises(ValueError, match="do not match"):
        verified_berlin_july2022(zipfile, csv)
