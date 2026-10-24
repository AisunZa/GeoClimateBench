r"""Developer-only fault-injection checks for GeoClimateBench Daily QC.

Run from Windows Anaconda PowerShell:
    .\.venv\Scripts\python.exe .\benchmarks\daily-max-qc\fault_injection.py

Uses the existing geoclimatebench-qc-verifier Docker image. Does not edit
benchmark files, alter the Git branch, or run in the Harbor agent environment.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOLUTION = ROOT / "solution" / "solve_daily.py"
VERIFIER_IMAGE = "geoclimatebench-qc-verifier"
INPUT = "/tests/data/hourly_synthetic.nc"
OUTPUT = "/app/results/daily_max.nc"

# Each replacement must occur exactly once in the reference solution.
MUTANTS = (
    (
        "Kelvin-to-Celsius conversion removed",
        "sampled_max - 273.15",
        "sampled_max",
        "Celsius maxima, coverage, or exclusions incorrect",
    ),
    (
        "24-hour threshold instead of 18",
        "counts >= 18",
        "counts >= 24",
        "Celsius maxima, coverage, or exclusions incorrect",
    ),
    (
        "Physical temperature bounds removed",
        "valid = data.t2m.where(np.isfinite(data.t2m) & (data.t2m >= 180) & (data.t2m <= 340))",
        "valid = data.t2m.where(np.isfinite(data.t2m))",
        "valid-hour counts",
    ),
)


def docker(workdir: Path, *command: str) -> subprocess.CompletedProcess[str]:
    """Execute inside the already built verifier image with a temporary /app."""
    mount = f"type=bind,source={workdir.resolve()},target=/app"
    return subprocess.run(
        ["docker", "run", "--rm", "--mount", mount, VERIFIER_IMAGE, *command],
        capture_output=True,
        text=True,
        errors="replace",
        check=False,
    )


def info(proc: subprocess.CompletedProcess[str]) -> str:
    return (proc.stdout + "\n" + proc.stderr).strip()


def run_public(workdir: Path) -> None:
    proc = docker(
        workdir, "python", "/app/solve.py", "--input", INPUT, "--output", OUTPUT
    )
    if proc.returncode != 0:
        raise RuntimeError("Solver failed before grading; test inconclusive:\n" + info(proc)[-2500:])
    if not (workdir / "results" / "daily_max.nc").is_file():
        raise RuntimeError("Solver did not create the required output file")


def grade(workdir: Path, *, expect_pass: bool, expected_failure: str = "") -> str:
    proc = docker(workdir, "python", "/tests/verify.py")
    output = info(proc)
    if expect_pass:
        if proc.returncode != 0 or "ALL SCIENTIFIC CHECKS PASSED" not in output:
            raise RuntimeError("Correct reference failed verification:\n" + output[-2500:])
        return "ALL SCIENTIFIC CHECKS PASSED"
    errors = [line.strip() for line in output.splitlines() if "AssertionError:" in line]
    if proc.returncode == 0 or not errors:
        raise RuntimeError("Faulty solver was not rejected by a scientific assertion:\n" + output[-2500:])
    if expected_failure not in errors[-1]:
        raise RuntimeError("Fault rejected for an unexpected reason:\n" + output[-2500:])
    return errors[-1]


def make_workdir() -> tempfile.TemporaryDirectory[str]:
    return tempfile.TemporaryDirectory(prefix="geoclimatebench-fault-")


def main() -> int:
    if not SOLUTION.is_file():
        print(f"ERROR: Reference solution not found: {SOLUTION}")
        return 1
    if not (ROOT / "tests" / "data" / "hourly_synthetic.nc").is_file():
        print("ERROR: benchmark tests/data/hourly_synthetic.nc is missing")
        return 1
    if shutil.which("docker") is None:
        print("ERROR: Docker command was not found. Open Anaconda PowerShell with Docker Desktop running.")
        return 1
    check_image = subprocess.run(
        ["docker", "image", "inspect", VERIFIER_IMAGE],
        capture_output=True, text=True, check=False,
    )
    if check_image.returncode != 0:
        print(f"ERROR: Missing Docker image {VERIFIER_IMAGE}. Build tests/Dockerfile first.")
        return 1

    source = SOLUTION.read_text(encoding="utf-8")
    passed = 0
    try:
        # Positive control: demonstrates that the test harness accepts valid code.
        with make_workdir() as temp:
            workdir = Path(temp)
            (workdir / "results").mkdir()
            (workdir / "solve.py").write_text(source, encoding="utf-8")
            run_public(workdir)
            grade(workdir, expect_pass=True)
            print("[PASS] Correct reference implementation accepted")
            passed += 1

        # Negative controls: each scientific mutation must be rejected.
        for label, old, new, scientific_error in MUTANTS:
            if source.count(old) != 1:
                raise RuntimeError(f"Mutation text changed in reference solution: {label}")
            with make_workdir() as temp:
                workdir = Path(temp)
                (workdir / "results").mkdir()
                (workdir / "solve.py").write_text(source.replace(old, new), encoding="utf-8")
                run_public(workdir)
                reason = grade(workdir, expect_pass=False, expected_failure=scientific_error)
                print(f"[PASS] Rejected: {label}\n       {reason}")
                passed += 1

        # A hardcoded-output cheat should pass the supplied file but fail on
        # independent new input files created inside the verifier.
        with make_workdir() as temp:
            workdir = Path(temp)
            (workdir / "results").mkdir()
            solution_file = workdir / "solve.py"
            solution_file.write_text(source, encoding="utf-8")
            run_public(workdir)  # calculate the canned answer only once
            shutil.copyfile(workdir / "results" / "daily_max.nc", workdir / "canned.nc")
            solution_file.write_text(
                "import argparse, shutil\n"
                "from pathlib import Path\n"
                "parser = argparse.ArgumentParser()\n"
                "parser.add_argument('--input', required=True)\n"
                "parser.add_argument('--output', required=True)\n"
                "args = parser.parse_args()\n"
                "Path(args.output).parent.mkdir(parents=True, exist_ok=True)\n"
                "shutil.copyfile('/app/canned.nc', args.output)\n",
                encoding="utf-8",
            )
            (workdir / "results" / "daily_max.nc").unlink()
            run_public(workdir)
            reason = grade(workdir, expect_pass=False, expected_failure="hidden fixture")
            print(f"[PASS] Rejected: hardcoded public result\n       {reason}")
            passed += 1
    except (OSError, RuntimeError) as exc:
        print(f"\n[FAIL] {exc}")
        return 1

    print(f"\nSUCCESS: {passed}/5 controls produced the expected outcomes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
