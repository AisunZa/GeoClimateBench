"""Parse a DWD CDC historical daily climate ZIP into the station schema.

No undocumented time-zone adjustment: TXK is a station daily maximum, and the
station-day convention must be checked before quantitative interpretation.
"""
from pathlib import Path
from zipfile import ZipFile
import io

import numpy as np
import pandas as pd


def parse_dwd_daily_zip(
    archive: str | Path,
    *,
    station_lat: float,
    station_lon: float,
    start: str = "2022-07-01",
    end: str = "2022-07-31",
) -> pd.DataFrame:
    """Load 'produkt_klima_tag_*.txt' and parse STATIONS_ID, MESS_DATUM, TXK.

    DWD -999 sentinel denotes missing temperature; we preserve as NaN in CSV.
    Caller supplies real station coordinates from DWD station metadata.
    """
    if not (-90 <= station_lat <= 90 and -180 <= station_lon <= 180):
        raise ValueError("Invalid station latitude/longitude")
    with ZipFile(archive) as zf:
        matches = [n for n in zf.namelist() if Path(n).name.lower().startswith("produkt_klima_tag_") and n.lower().endswith(".txt")]
        if len(matches) != 1:
            raise ValueError("Expected exactly one produkt_klima_tag_*.txt in DWD archive")
        with zf.open(matches[0]) as raw:
            table = pd.read_csv(io.BytesIO(raw.read()), sep=";", dtype={"STATIONS_ID": str}, low_memory=False)
    table.columns = table.columns.str.strip()
    required = {"STATIONS_ID", "MESS_DATUM", "TXK"}
    if not required.issubset(table.columns):
        raise ValueError(f"DWD text missing required fields {required - set(table.columns)}")
    dates = pd.to_datetime(table.MESS_DATUM.astype(str).str.strip(), format="%Y%m%d", errors="raise")
    temperature = pd.to_numeric(table.TXK, errors="coerce")
    temperature = temperature.where((temperature > -999) & (temperature >= -80) & (temperature <= 65), np.nan)
    result = pd.DataFrame({
        "station_id": table.STATIONS_ID.str.strip().str.zfill(5),
        "date": dates.dt.strftime("%Y-%m-%d"),
        "latitude": float(station_lat),
        "longitude": float(station_lon),
        "txk_c": temperature,
    })
    result = result[(dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))].copy()
    return result.sort_values(["station_id", "date"]).reset_index(drop=True)
