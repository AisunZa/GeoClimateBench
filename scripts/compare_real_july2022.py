r"""Berlin-Tempelhof July 2022 ERA5-Land vs DWD scientific comparison.

Execute at the project root:
    .\.venv\Scripts\python.exe scripts\compare_real_july2022.py

The DWD original ZIP is required for verification of 2022 reporting-day
metadata, QN_4 quality flags, and the integrity of imported TXK observations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr

from geoclimatebench.realdata_qc import verified_berlin_july2022
from geoclimatebench.science import daily_max_from_hourly
from geoclimatebench.validation import compare_stations, save_station_outputs


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hourly", type=Path, default=Path("data/era5_berlin_2022_07_normalized.nc"))
    ap.add_argument("--stations", type=Path, default=Path("data/dwd_berlin_2022_07.csv"))
    ap.add_argument("--dwd-archive", type=Path, default=None,
                    help="Original historical DWD ZIP; auto-detected in downloads/ otherwise")
    ap.add_argument("--output", type=Path, default=Path("results/real_berlin_2022_07"))
    ap.add_argument("--max-distance-km", type=float, default=20.0)
    args = ap.parse_args()

    if args.dwd_archive is None:
        matches = list(Path("downloads").glob("tageswerte_KL_00433_*_hist.zip"))
        if len(matches) != 1:
            ap.error("Expected exactly one Berlin-Tempelhof historical DWD ZIP in downloads/. "
                     "Set --dwd-archive to override.")
        args.dwd_archive = matches[0]

    for source in (args.hourly, args.stations, args.dwd_archive):
        if not source.is_file():
            ap.error(f"Missing input file: {source}. Run from the project root.")

    dwd_provenance = verified_berlin_july2022(args.dwd_archive, args.stations)
    expected = pd.date_range("2022-07-01 00:00:00", "2022-07-31 23:00:00", freq="h")
    with xr.open_dataset(args.hourly) as ds:
        observed_times = pd.DatetimeIndex(ds.time.values)
        if not observed_times.equals(expected):
            raise ValueError("ERA5-Land input must contain exactly 744 consecutive UTC hourly "
                             "timestamps from July 1 00:00 through July 31 23:00, 2022")
        if ds.attrs.get("time_standard") != "UTC":
            raise ValueError("Normalized NetCDF must declare time_standard='UTC'")
        if ds.t2m.attrs.get("units") != "K":
            raise ValueError("ERA5-Land t2m units must be K")
        missing_hourly = int(ds.t2m.isnull().sum().item())
        daily = daily_max_from_hourly(ds, min_valid_hours=24)

    station_data = pd.read_csv(args.stations, dtype={"station_id": str})
    pairs, metrics = compare_stations(daily, station_data, max_distance_km=args.max_distance_km)
    if metrics["overall"]["n_pairs"] != 31:
        raise ValueError("Expected 31 valid station/grid comparisons; inspect excluded records")
    metrics["limitations"] = [
        "The DWD TXK measurement-day convention is UTC 00:00–24:00 for station "
        "00433 in July 2022, according to metadata supplied in the DWD ZIP.",
        "ERA5-Land daily max here uses hourly sampled temperatures; DWD TXK may "
        "include within-hour maxima or differently sampled observations.",
        "ERA5-Land is a 2-m grid-cell estimate; the station is a point with distinct "
        "elevation, urban setting, instrumentation and exposure.",
        "Nearest-cell matching uses no topographic, temporal, or instrument correction.",
        "DWD QN_4 quality-control level is 9 for this source dataset; retain "
        "the report-level flag, which does not itself prove TXK is wrong.",
        "One station and one month do not establish general model accuracy or climate trends.",
    ]
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    daily.to_netcdf(output / "daily_max.nc", engine="scipy")
    save_station_outputs(pairs, metrics, output)

    fig, ax = plt.subplots(figsize=(10, 4.5), constrained_layout=True)
    dates = pd.to_datetime(pairs["date"])
    ax.plot(dates, pairs["observed_tmax_c"], "o-", label="DWD station TXK", markersize=3)
    ax.plot(dates, pairs["modeled_tmax_c"], "s-",
            label="ERA5-Land hourly-sampled daily maximum", markersize=3)
    ax.set(title="Berlin-Tempelhof | July 2022 | Exploratory temperature comparison",
           xlabel="UTC date", ylabel="Daily maximum temperature (°C)")
    ax.legend(loc="best", frameon=False)
    ax.grid(alpha=0.25)
    fig.autofmt_xdate()
    fig.text(0.5, 0.01,
             "Same nominal UTC reporting day; hourly sampling and station/grid representation differ.",
             fontsize=8, ha="center")
    fig.savefig(output / "station_temperature_comparison.png", dpi=170, bbox_inches="tight")
    plt.close(fig)

    provenance = {
        "purpose": "Exploratory, nominal-UTC-day-aligned station-to-grid temperature comparison",
        "datasets": {
            "hourly_path": str(args.hourly), "stations_path": str(args.stations),
            "original_dwd_archive_path": str(args.dwd_archive),
            "hourly_sha256": sha256(args.hourly),
            "stations_sha256": sha256(args.stations),
            "original_dwd_archive_sha256": sha256(args.dwd_archive),
        },
        "time_period": "2022-07-01 through 2022-07-31",
        "grid_day": "UTC 00:00–23:00 timestamps, max of 24 hourly samples",
        "dwd_source_checks": dwd_provenance,
        "hourly_missing_samples": missing_hourly,
        "minimum_valid_hours_per_cell_day": int(daily.hours_valid.min().item()),
        "n_paired_station_days": int(metrics["overall"]["n_pairs"]),
        "station_grid_matching": "nearest cell by great-circle distance, no interpolation",
        "python": platform.python_version(), "numpy": np.__version__,
        "pandas": pd.__version__, "xarray": xr.__version__,
        "interpretation_limitations": metrics["limitations"],
    }
    (output / "real_run_metadata.json").write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print("PASS: DWD TXK July 2022 observation window: 00:00–24:00 UTC")
    print(f"PASS: DWD archive CSV values match; QN_4 distribution: {dwd_provenance['qn_4_counts']}")
    print("PASS: 744 UTC hourly timestamps; 31 calendar days")
    print(f"Missing hourly grid samples: {missing_hourly}")
    print(f"Paired station-days: {metrics['overall']['n_pairs']}")
    print(f"Excluded station-days: {metrics['n_excluded']}")
    first = pairs.iloc[0]
    print(f"Matched grid cell: {first.grid_lat:.4f} N, {first.grid_lon:.4f} E, "
          f"distance={first.distance_km:.2f} km")
    for name in ("bias_c", "mae_c", "rmse_c"):
        print(f"{name}: {metrics['overall'][name]:.3f} °C")
    print(f"Updated real-data results saved to: {output.resolve()}")
    print("CAUTION: Nominal UTC day aligned; within-hour extrema and spatial differences remain.")


if __name__ == "__main__":
    main()
