"""Command-line entry points for the reproducible local benchmark."""
import argparse
from pathlib import Path
import json
import platform
import hashlib

import numpy as np
import pandas as pd
import xarray as xr

from . import __version__
from .dwd import parse_dwd_daily_zip
from .evaluate import grade
from .era5 import normalize_era5_netcdf
from .fixtures import generate_fixtures
from .plots import create_plots
from .science import daily_max_from_hourly, compute_extremes
from .validation import compare_stations, save_station_outputs


def run_pipeline(hourly_path: Path, stations_path: Path, output: Path, target_year: int = 2022, target_month: int = 7, plots: bool = True) -> None:
    output.mkdir(parents=True, exist_ok=True)
    with xr.open_dataset(hourly_path) as hourly:
        daily = daily_max_from_hourly(hourly)
    daily.to_netcdf(output / "daily_max.nc", engine="scipy")
    extreme = compute_extremes(daily, target_year=target_year, target_month=target_month)
    extreme.to_netcdf(output / "heatwaves.nc", engine="scipy")
    observations = pd.read_csv(stations_path, dtype={"station_id": str})
    pairs, metrics = compare_stations(daily, observations)
    save_station_outputs(pairs, metrics, output)
    if plots:
        create_plots(daily, extreme, output)
    def checksum(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as fp:
            for chunk in iter(lambda: fp.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    provenance = {
        "tool": f"GeoClimateBench v{__version__}",
        "environment": {
            "python": platform.python_version(), "numpy": np.__version__,
            "pandas": pd.__version__, "xarray": xr.__version__,
        },
        "input_sha256": {
            "hourly": checksum(hourly_path), "stations": checksum(stations_path),
        },
        "hourly_input": str(hourly_path),
        "stations_input": str(stations_path),
        "input_type": daily.attrs.get("source_type", "Unknown"),
        "target_year": target_year,
        "target_month": target_month,
        "note": "Outputs describe the supplied inputs; synthetic fixtures cannot validate climate conclusions.",
    }
    (output / "run_metadata.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    print(f"Saved scientific outputs to {output.resolve()}")
    print(f"Station validation: n_pairs={metrics['overall']['n_pairs']}; RMSE={metrics['overall']['rmse_c']} °C")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="geoclimatebench", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Generate synthetic data, run oracle, grade and plot (no network)")
    demo.add_argument("--data-dir", type=Path, default=Path("data"))
    demo.add_argument("--output", type=Path, default=Path("results"))

    run = commands.add_parser("run", help="Run oracle pipeline on user-supplied normalized data")
    run.add_argument("--hourly", required=True, type=Path)
    run.add_argument("--stations", required=True, type=Path)
    run.add_argument("--output", type=Path, default=Path("results"))
    run.add_argument("--target-year", type=int, default=2022)
    run.add_argument("--target-month", type=int, default=7)
    run.add_argument("--no-plots", action="store_true")

    grading = commands.add_parser("grade", help="Independently re-check outputs against SYNTHETIC fixture")
    grading.add_argument("--data-dir", type=Path, default=Path("data"))
    grading.add_argument("--output", type=Path, default=Path("results"))

    oracle = commands.add_parser("solve-task", help="Run the reference solution for one task")
    oracle.add_argument("--task", type=int, choices=[1, 2, 3], required=True)
    oracle.add_argument("--data-dir", type=Path, default=Path("data"))
    oracle.add_argument("--output", type=Path, default=Path("results"))

    taskgrade = commands.add_parser("grade-task", help="Check one task's output independently")
    taskgrade.add_argument("--task", type=int, choices=[1, 2, 3], required=True)
    taskgrade.add_argument("--data-dir", type=Path, default=Path("data"))
    taskgrade.add_argument("--output", type=Path, default=Path("results"))

    convert = commands.add_parser("dwd-import", help="Convert one official DWD CDC daily KL ZIP to station CSV")
    convert.add_argument("--archive", required=True, type=Path)
    convert.add_argument("--latitude", required=True, type=float)
    convert.add_argument("--longitude", required=True, type=float)
    convert.add_argument("--start", default="2022-07-01")
    convert.add_argument("--end", default="2022-07-31")
    convert.add_argument("--output", required=True, type=Path)

    norm = commands.add_parser("era5-normalize", help="Normalize local ERA5-Land NetCDF exports")
    norm.add_argument("--input", nargs="+", required=True, type=Path)
    norm.add_argument("--output", required=True, type=Path)

    args = parser.parse_args(argv)
    if args.command == "demo":
        generate_fixtures(args.data_dir)
        run_pipeline(args.data_dir / "hourly_synthetic.nc", args.data_dir / "stations_synthetic.csv", args.output)
        result = grade(args.output, args.data_dir)
        print(json.dumps(result, indent=2))
    elif args.command == "run":
        run_pipeline(args.hourly, args.stations, args.output, args.target_year, args.target_month, plots=not args.no_plots)
    elif args.command == "grade":
        print(json.dumps(grade(args.output, args.data_dir), indent=2))
    elif args.command == "solve-task":
        args.output.mkdir(parents=True, exist_ok=True)
        if args.task == 1:
            with xr.open_dataset(args.data_dir / "hourly_synthetic.nc") as source:
                daily = daily_max_from_hourly(source)
            daily.to_netcdf(args.output / "daily_max.nc", engine="scipy")
        elif args.task == 2:
            with xr.open_dataset(args.output / "daily_max.nc") as input_daily:
                heatwaves = compute_extremes(input_daily)
            heatwaves.to_netcdf(args.output / "heatwaves.nc", engine="scipy")
        else:
            with xr.open_dataset(args.output / "daily_max.nc") as input_daily:
                observations = pd.read_csv(args.data_dir / "stations_synthetic.csv", dtype={"station_id": str})
                pairs, metrics = compare_stations(input_daily, observations)
            save_station_outputs(pairs, metrics, args.output)
        print(f"Reference solution for task {args.task} saved in {args.output}")
    elif args.command == "grade-task":
        print(json.dumps(grade(args.output, args.data_dir, task=args.task), indent=2))
    elif args.command == "era5-normalize":
        normalize_era5_netcdf(args.input, args.output)
        print(f"Wrote normalized hourly data to {args.output}")
    elif args.command == "dwd-import":
        df = parse_dwd_daily_zip(args.archive, station_lat=args.latitude, station_lon=args.longitude, start=args.start, end=args.end)
        args.output.parent.mkdir(exist_ok=True, parents=True)
        df.to_csv(args.output, index=False)
        print(f"Wrote {len(df)} records to {args.output}")


if __name__ == "__main__":
    main()
