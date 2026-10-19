"""Run the task-04 real-data local benchmark grader (from repository root)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from geoclimatebench.realdata_grader import RealDataGradingError, grade_real_berlin


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hourly", type=Path,
                    default=Path("data/era5_berlin_2022_07_normalized.nc"))
    ap.add_argument("--stations", type=Path, default=Path("data/dwd_berlin_2022_07.csv"))
    ap.add_argument("--archive", type=Path, default=None,
                    help="Original DWD ZIP archive; discovered in downloads/ if omitted")
    ap.add_argument("--output", type=Path, default=Path("results/real_berlin_2022_07"))
    args = ap.parse_args()
    if args.archive is None:
        matches = sorted(Path("downloads").glob("tageswerte_KL_00433_*_hist.zip"))
        if len(matches) != 1:
            ap.error("Exactly one DWD historical archive must exist in downloads/; "
                     "otherwise specify --archive PATH")
        args.archive = matches[0]
    try:
        score = grade_real_berlin(hourly=args.hourly, stations=args.stations,
                                  archive=args.archive, output=args.output)
    except (RealDataGradingError, ValueError, OSError, KeyError) as ex:
        print(json.dumps({"status": "FAIL", "task_id": 4, "reason": str(ex)}, indent=2))
        return 1
    print(json.dumps(score, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
