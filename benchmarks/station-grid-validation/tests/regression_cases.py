"""Offline black-box regression controls for GeoClimateBench Station–Grid Validation.

Run the standalone solver and independent verifier against synthetic cases.
No geoclimatebench imports. All generated data are synthetic and temporary.
This is a local pre-Harbor regression suite, NOT a completed Harbor control.
"""

import argparse
import contextlib
import csv
import importlib.util
import io
import json
import math
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

FIELDS = ["station_id", "date", "latitude", "longitude", "txk_c"]
PAIRS = [
    "station_id", "date", "station_lat", "station_lon", "grid_lat",
    "grid_lon", "distance_km", "observed_tmax_c", "modeled_tmax_c", "error_c",
]
STAT_KEYS = ("bias_c", "mae_c", "rmse_c", "max_abs_error_c")


def make_grid(dates, lats, lons, temperatures):
    return xr.Dataset(
        {"tmax_c": (
            ("time", "latitude", "longitude"),
            np.asarray(temperatures, dtype="float64"),
            {"units": "degC"},
        )},
        coords={
            "time": pd.to_datetime(dates),
            "latitude": np.asarray(lats, dtype="float64"),
            "longitude": np.asarray(lons, dtype="float64"),
        },
        attrs={"time_standard": "UTC", "source_type": "SYNTHETIC TEST ONLY"},
    )


def save_input(folder, ds, rows, header=FIELDS):
    folder.mkdir(parents=True, exist_ok=True)
    daily = folder / "daily_max.nc"
    stations = folder / "stations_synthetic.csv"
    ds.to_netcdf(daily, engine="scipy")
    with stations.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(header)
        for record in rows:
            values = dict(zip(FIELDS, record))
            writer.writerow([values[field] for field in header])
    return daily, stations


def execute(script, *args):
    return subprocess.run(
        [sys.executable, str(script), *map(str, args)],
        capture_output=True,
        text=True,
        check=False,
    )


def require_pass(result, label):
    if result.returncode != 0:
        raise AssertionError(
            f"{label} unexpectedly failed (exit {result.returncode}):\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )


def require_rejection(result, label):
    if result.returncode == 0:
        raise AssertionError(f"{label}: invalid input or corrupted output was incorrectly accepted")


def positive_cases():
    # Expected rows are independently specified: (grid_lat, grid_lon, error_C).
    yield (
        "mixed_exclusions_and_temperature_limits",
        make_grid(
            ["2025-08-03", "2025-08-05"], [10, 11], [20, 22],
            [[[20, 25], [35, 40]], [[-2, np.nan], [32, 42]]],
        ),
        [
            ("CENTER", "2025-08-03", 10, 20, -80),
            ("CENTER", "2025-08-05", 10, 20, 65),
            ("NANMODEL", "2025-08-05", 10, 22, 30),
            ("OUT", "2025-08-03", 30, 20, 10),
            ("OUT", "2025-08-05", 30, 20, -999),
            ("MISSING", "2025-08-04", 11, 20, 20),
            ("EDGE", "2025-08-03", 11, 22, 41),
            ("BADOBS", "2025-08-05", 11, 22, 66),
            ("EMPTY", "2025-08-03", 11, 20, "nan"),
            ("LOW", "2025-08-03", 10, 20, -81),
            ("BOGUS", "2025-08-05", 10, 20, ""),
            ("SIDE", "2025-08-05", 11, 20, 31),
        ],
        {
            ("CENTER", "2025-08-03"): (10, 20, 100),
            ("CENTER", "2025-08-05"): (10, 20, -67),
            ("EDGE", "2025-08-03"): (11, 22, -1),
            ("SIDE", "2025-08-05"): (11, 20, 1),
        },
        {"missing_observation": 5, "outside_grid": 1, "unavailable_date": 1, "missing_grid": 1},
    )
    yield (
        "high_latitude_haversine_and_tie_breaking",
        make_grid(
            ["2024-02-28", "2024-03-01"], [60, 61], [0, 3],
            [[[0, 10], [20, 30]], [[1, 11], [21, 31]]],
        ),
        [
            # Coordinate-wise nearest would choose (60, 0) incorrectly.
            ("GEODESIC", "2024-02-28", 60.495, 1.17, 18),
            ("GEODESIC", "2024-03-01", 60.495, 1.17, 25),
            # Equal great-circle distances to (60, 0) and (60, 3).
            ("TIE", "2024-02-28", 60, 1.5, -3),
            ("UNMATCHED", "2024-02-28", 70, 40, 25),
        ],
        {
            ("GEODESIC", "2024-02-28"): (61, 0, 2),
            ("GEODESIC", "2024-03-01"): (61, 0, -4),
            ("TIE", "2024-02-28"): (60, 0, 3),
        },
        {"missing_observation": 0, "outside_grid": 1, "unavailable_date": 0, "missing_grid": 0},
    )
    yield (
        "international_date_line",
        make_grid(["2018-11-01"], [-10, 10], [-179, 179],
                  [[[14, 16], [24, 26]]]),
        [
            ("EAST", "2018-11-01", 10, 179.8, 25),
            ("WEST", "2018-11-01", 10, -179.8, 25),
            ("REMOTE", "2018-11-01", 0, 0, 15),
        ],
        {
            ("EAST", "2018-11-01"): (10, 179, 1),
            ("WEST", "2018-11-01"): (10, -179, -1),
        },
        {"missing_observation": 0, "outside_grid": 1, "unavailable_date": 0, "missing_grid": 0},
    )
    yield (
        "zero_valid_pairs_and_header_only_csv",
        make_grid(["2022-01-01"], [0], [0], [[[np.nan]]]),
        [
            ("FAR", "2022-01-01", 85, 0, 0),
            ("MISSING", "2022-01-01", 0, 0, -999),
            ("NO_DATE", "2022-01-02", 0, 0, 4),
            ("NO_MODEL", "2022-01-01", 0, 0, 1),
        ],
        {},
        {"missing_observation": 1, "outside_grid": 1, "unavailable_date": 1, "missing_grid": 1},
    )


def inspect_manual_expectations(pairs_path, metrics_path, rows, expected_pairs, excluded):
    with pairs_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames == PAIRS, "Pair columns/order differ from contract"
        actual = list(reader)
    assert len(actual) == len(expected_pairs), "Unexpected pair count"
    actual_keys = [(r["station_id"], r["date"]) for r in actual]
    assert actual_keys == sorted(expected_pairs), "Unexpected pairing or order"
    for record in actual:
        key = record["station_id"], record["date"]
        glat, glon, err = expected_pairs[key]
        for field, wanted in (("grid_lat", glat), ("grid_lon", glon), ("error_c", err)):
            value = float(record[field])
            assert math.isfinite(value) and abs(value - wanted) <= 1e-4, (key, field, value, wanted)
    info = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert info["n_excluded"] == excluded, "Exclusion counts differ from independently specified counts"
    assert info["n_input_rows"] == len(rows), "Incorrect number of station input rows"
    assert info["overall"]["n_pairs"] == len(expected_pairs)
    assert set(info["by_station"]) == {r[0] for r in rows}, "Missing zero-match station"
    errors = [item[2] for item in expected_pairs.values()]
    if errors:
        expected_stats = {
            "bias_c": math.fsum(errors) / len(errors),
            "mae_c": math.fsum(abs(e) for e in errors) / len(errors),
            "rmse_c": math.sqrt(math.fsum(e * e for e in errors) / len(errors)),
            "max_abs_error_c": max(abs(e) for e in errors),
        }
        for key, expected in expected_stats.items():
            assert abs(info["overall"][key] - expected) <= 1e-4, f"incorrect {key}"
    else:
        assert all(info["overall"][key] is None for key in STAT_KEYS), "Empty metrics must be null"
    for sid in info["by_station"]:
        expected_errors = [err for (station, _), (_, _, err) in expected_pairs.items() if station == sid]
        station_stats = info["by_station"][sid]
        assert station_stats["n_pairs"] == len(expected_errors)
        if not expected_errors:
            assert all(station_stats[key] is None for key in STAT_KEYS), f"{sid}: missing null metrics"
    return len(actual), sum(excluded.values())


def run_positive(solver, verify, work):
    first = None
    count = 0
    for name, ds, rows, expected_pairs, excluded in positive_cases():
        case = work / "positive" / name
        daily, stations = save_input(case, ds, rows)
        results = case / "results"
        attempt = execute(solver, "--daily", daily, "--stations", stations, "--output-dir", results)
        require_pass(attempt, f"positive/{name}: solver")
        pairs, metrics = results / "station_pairs.csv", results / "metrics.json"
        matched, dropped = inspect_manual_expectations(pairs, metrics, rows, expected_pairs, excluded)
        with contextlib.redirect_stdout(io.StringIO()):
            verify(daily, stations, pairs, metrics)
        print(f"PASS: unseen {name} ({matched} pairs, {dropped} exclusions)", flush=True)
        count += 1
        if first is None:
            first = (daily, stations, pairs, metrics)
    return count, first


def modify_dataset(ds, change):
    ds = ds.copy(deep=True)
    if change == "kelvin_units":
        ds.tmax_c.attrs["units"] = "K"
    elif change == "missing_utc":
        del ds.attrs["time_standard"]
    elif change == "duplicate_grid_time":
        ds = ds.assign_coords(time=pd.to_datetime(["2025-08-03", "2025-08-03"]))
    elif change == "decreasing_grid_time":
        ds = ds.assign_coords(time=pd.to_datetime(["2025-08-05", "2025-08-03"]))
    elif change == "nonmidnight_grid_time":
        ds = ds.assign_coords(time=pd.to_datetime(["2025-08-03 01:00", "2025-08-05 00:00"]))
    elif change == "decreasing_latitude":
        ds = ds.assign_coords(latitude=[11.0, 10.0])
    elif change == "invalid_grid_longitude":
        ds = ds.assign_coords(longitude=[20.0, 181.0])
    elif change == "nonfinite_grid_latitude":
        ds = ds.assign_coords(latitude=[10.0, math.nan])
    elif change == "missing_tmax_variable":
        ds = ds.drop_vars("tmax_c")
    elif change == "wrong_tmax_dimensions":
        ds = ds.transpose("latitude", "time", "longitude")
    else:
        raise AssertionError(f"Unknown dataset mutation: {change}")
    return ds


def run_invalid(solver, work, workers):
    base = make_grid(["2025-08-03", "2025-08-05"], [10, 11], [20, 22],
                     [[[20, 25], [35, 40]], [[21, 26], [36, 41]]])
    rows = [
        ("A", "2025-08-03", 10, 20, 18),
        ("A", "2025-08-05", 10, 20, 19),
        ("B", "2025-08-03", 11, 22, 39),
    ]
    variations = [
        ("duplicate_station_date", base, rows + [rows[0]], FIELDS),
        ("inconsistent_station_position", base, rows + [("A", "2025-08-07", 10.5, 20, 19)], FIELDS),
        ("invalid_station_latitude", base, [("A", "2025-08-03", 91, 20, 18)] + rows[1:], FIELDS),
        ("invalid_station_longitude", base, [("A", "2025-08-03", 10, 181, 18)] + rows[1:], FIELDS),
        ("nonfinite_station_coordinate", base, [("A", "2025-08-03", "nan", 20, 18)] + rows[1:], FIELDS),
        ("blank_station_identifier", base, [("", "2025-08-03", 10, 20, 18)] + rows[1:], FIELDS),
        ("malformed_station_date", base, [("A", "03-08-2025", 10, 20, 18)] + rows[1:], FIELDS),
        ("impossible_station_date", base, [("A", "2025-02-30", 10, 20, 18)] + rows[1:], FIELDS),
        ("missing_station_column", base, rows, FIELDS[:-1]),
        ("empty_station_records", base, [], FIELDS),
    ]
    grid_changes = [
        "kelvin_units", "missing_utc", "duplicate_grid_time", "decreasing_grid_time",
        "nonmidnight_grid_time", "decreasing_latitude", "invalid_grid_longitude",
        "nonfinite_grid_latitude", "missing_tmax_variable", "wrong_tmax_dimensions",
    ]
    variations += [(change, modify_dataset(base, change), rows, FIELDS) for change in grid_changes]
    jobs = []
    for name, ds, station_rows, header in variations:
        case = work / "invalid" / name
        daily, stations = save_input(case, ds, station_rows, header)
        jobs.append((name, daily, stations, case / "results"))

    def run_job(job):
        name, daily, stations, output = job
        return name, execute(solver, "--daily", daily, "--stations", stations,
                             "--output-dir", output)

    # Every case has distinct files; parallel subprocesses reduce startup overhead.
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for name, attempt in pool.map(run_job, jobs):
            require_rejection(attempt, f"invalid/{name}")
            print(f"PASS: rejected invalid {name}", flush=True)
    return len(jobs)


def run_mutations(verify, first, work):
    daily, stations, original_pairs, original_metrics = first
    def mutate_pairs_error(pairs, metrics):
        with pairs.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        rows[0]["error_c"] = str(-float(rows[0]["error_c"]))
        write_pair_rows(pairs, rows)
    def mutate_pairs_distance(pairs, metrics):
        with pairs.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        rows[0]["distance_km"] = str(float(rows[0]["distance_km"]) + 1.5)
        write_pair_rows(pairs, rows)
    def mutate_missing_outlier(pairs, metrics):
        with pairs.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        write_pair_rows(pairs, rows[1:])
    def mutate_rmse(pairs, metrics):
        data = json.loads(metrics.read_text(encoding="utf-8"))
        data["overall"]["rmse_c"] += 10.0
        metrics.write_text(json.dumps(data), encoding="utf-8")
    def mutate_station_coverage(pairs, metrics):
        data = json.loads(metrics.read_text(encoding="utf-8"))
        del data["by_station"]["NANMODEL"]
        metrics.write_text(json.dumps(data), encoding="utf-8")
    def mutate_exclusion_counts(pairs, metrics):
        data = json.loads(metrics.read_text(encoding="utf-8"))
        data["n_excluded"]["outside_grid"] += 1
        metrics.write_text(json.dumps(data), encoding="utf-8")
    changes = [
        ("reversed_error_sign", mutate_pairs_error),
        ("wrong_haversine_distance", mutate_pairs_distance),
        ("removed_valid_outlier", mutate_missing_outlier),
        ("corrupted_global_rmse", mutate_rmse),
        ("omitted_zero_match_station", mutate_station_coverage),
        ("incorrect_exclusion_counts", mutate_exclusion_counts),
    ]
    for name, mutate in changes:
        folder = work / "mutation" / name
        folder.mkdir(parents=True)
        pairs, metrics = folder / "station_pairs.csv", folder / "metrics.json"
        shutil.copy2(original_pairs, pairs)
        shutil.copy2(original_metrics, metrics)
        mutate(pairs, metrics)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                verify(daily, stations, pairs, metrics)
        except AssertionError:
            print(f"PASS: independent verifier rejected {name}", flush=True)
        else:
            raise AssertionError(f"mutation/{name}: bad output was accepted")
    return len(changes)


def write_pair_rows(path, rows):
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=PAIRS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    benchmark = Path(__file__).resolve().parents[1]
    parser.add_argument("--solver", type=Path, default=benchmark / "solution" / "solve_station.py")
    parser.add_argument("--verifier", type=Path, default=benchmark / "tests" / "verify.py")
    parser.add_argument("--workers", type=int, default=4, help="parallel invalid-input CLI checks")
    args = parser.parse_args()
    solver, verifier = args.solver.resolve(), args.verifier.resolve()
    for path in (solver, verifier):
        if not path.is_file():
            parser.error(f"Python program not found: {path}")
    if args.workers < 1 or args.workers > 8:
        parser.error("--workers must be between 1 and 8")
    spec = importlib.util.spec_from_file_location("independent_station_verifier", verifier)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "verify", None)):
        parser.error("independent verifier must expose verify(daily, stations, pairs, metrics)")
    with tempfile.TemporaryDirectory(prefix="gcb-station-regression-") as name:
        workspace = Path(name)
        a, first = run_positive(solver, module.verify, workspace)
        b = run_invalid(solver, workspace, args.workers)
        c = run_mutations(module.verify, first, workspace)
    print(f"\nALL CONTROLS PASSED: {a} unseen fixtures, {b} invalid-input rejections, "
          f"{c} verifier fault-detection checks", flush=True)
    print("Results apply to synthetic scientific fixtures; Harbor Oracle/Nop controls not yet run.")


if __name__ == "__main__":
    main()
