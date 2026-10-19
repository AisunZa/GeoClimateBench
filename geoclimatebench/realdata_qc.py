"""Provenance and quality checks for a DWD historical daily KL ZIP.

This module deliberately does not alter source observations or silently treat
all DWD stations as having the same daily measurement-day convention.
"""
from __future__ import annotations

import io
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd

STATION = "00433"
START = pd.Timestamp("2022-07-01")
END = pd.Timestamp("2022-07-31")
EXPECTED_WINDOW = "00:00 - 24:00 UTC gemessen"


def _one_member(archive: ZipFile, prefix: str, suffix: str = ".txt") -> str:
    matches = [name for name in archive.namelist()
               if Path(name).name.lower().startswith(prefix.lower())
               and name.lower().endswith(suffix)]
    if len(matches) != 1:
        raise ValueError(f"Expected one '{prefix}*{suffix}' in DWD ZIP, found {len(matches)}")
    return matches[0]


def verified_berlin_july2022(archive: str | Path, imported_csv: str | Path) -> dict:
    """Check original TXK values, daily timestamps, QN_4 and station-day metadata.

    Designed for the specific Berlin-Tempelhof July 2022 case study, NOT for
    arbitrary stations/years. Fail closed when station-day metadata disagrees.
    """
    with ZipFile(archive) as zf:
        member = _one_member(zf, "produkt_klima_tag_")
        original = pd.read_csv(io.BytesIO(zf.read(member)), sep=";",
                               dtype={"STATIONS_ID": str}, low_memory=False)
        original.columns = original.columns.str.strip()
        required = {"STATIONS_ID", "MESS_DATUM", "TXK", "QN_4"}
        if not required.issubset(original.columns):
            raise ValueError(f"DWD daily data missing required fields: {required - set(original.columns)}")
        original["date"] = pd.to_datetime(original["MESS_DATUM"].astype(str).str.strip(),
                                          format="%Y%m%d", errors="raise")
        original["station_id"] = original["STATIONS_ID"].str.strip().str.zfill(5)
        selected = original.loc[(original["date"] >= START) & (original["date"] <= END)].copy()
        expected_dates = pd.date_range(START, END, freq="D")
        selected = selected.sort_values("date")
        if selected["station_id"].nunique() != 1 or not selected["station_id"].eq(STATION).all():
            raise ValueError("Unexpected station ID in original DWD data")
        if not pd.DatetimeIndex(selected["date"]).equals(expected_dates):
            raise ValueError("Original DWD archive does not contain exactly the 31 July 2022 dates")
        txk = pd.to_numeric(selected["TXK"], errors="coerce")
        if txk.isna().any() or (~txk.between(-80, 65)).any():
            raise ValueError("Invalid or missing DWD TXK measurements")
        qn = pd.to_numeric(selected["QN_4"], errors="coerce")
        if qn.isna().any():
            raise ValueError("DWD QN_4 flags must be present for every observation")
        qn_counts = {str(int(key)): int(val)
                     for key, val in sorted(qn.value_counts().items())}

        meta_member = _one_member(zf, "metadaten_parameter_klima_tag_")
        meta = zf.read(meta_member).decode("latin-1", errors="replace")
        matching = []
        for line in meta.splitlines():
            fields = [value.strip() for value in line.split(";")]
            if len(fields) < 9 or fields[4].upper() != "TXK":
                continue
            try:
                start = pd.to_datetime(fields[1], format="%Y%m%d")
                end = pd.to_datetime(fields[2], format="%Y%m%d")
            except (ValueError, TypeError):
                continue
            if fields[0].zfill(5) == STATION and start <= START and END <= end:
                matching.append(fields)
        if len(matching) != 1:
            raise ValueError("Could not identify exactly one TXK metadata interval covering July 2022")
        window = matching[0][8]
        if window != EXPECTED_WINDOW:
            raise ValueError(f"Unexpected 2022 DWD TXK measurement window: {window!r}")

    imported = pd.read_csv(imported_csv, dtype={"station_id": str})
    if not {"date", "station_id", "txk_c"}.issubset(imported.columns):
        raise ValueError("Imported CSV must contain station_id, date, txk_c")
    imported["date"] = pd.to_datetime(imported["date"], errors="raise")
    imported = imported.sort_values("date")
    if not imported["station_id"].eq(STATION).all():
        raise ValueError("Imported station ID is not 00433")
    if not pd.DatetimeIndex(imported["date"]).equals(expected_dates):
        raise ValueError("Imported DWD CSV does not contain exactly 31 July 2022 dates")
    imported_txk = pd.to_numeric(imported["txk_c"], errors="raise")
    if not np.allclose(imported_txk.to_numpy(), txk.to_numpy(), atol=1e-6, rtol=0):
        raise ValueError("Imported DWD TXK values do not match the source archive")
    return {
        "station_id": STATION,
        "n_station_days": int(len(selected)),
        "source_product_member": member,
        "source_parameter_metadata_member": meta_member,
        "txk_measurement_window": window,
        "txk_measurement_window_utc_aligned": True,
        "qn_4_counts": qn_counts,
        "qn_4_meaning": {
            "9": "Not all parameters corrected (report-level DWD quality flag)",
            "10": "Quality control and all corrections completed",
        },
        "source_txk_matches_imported_csv": True,
    }
