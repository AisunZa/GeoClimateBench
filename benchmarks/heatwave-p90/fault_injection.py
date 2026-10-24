r"""Developer-only fault-injection controls for GeoClimateBench Heatwave P90.

From the repository root in Windows Anaconda PowerShell:
    .\.venv\Scripts\python.exe .\benchmarks\heatwave-p90\fault_injection.py

Uses the prebuilt geoclimatebench-heatwave-verifier Docker image. No Harbor
reruns, network access, tracked-file edits, or Git operations are performed.
Negative controls must fail with a scientific verifier assertion, not merely
because the mutated program crashes or a Docker command fails.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOLUTION = ROOT / "solution" / "solve_heatwaves.py"
VERIFIER_IMAGE = "geoclimatebench-heatwave-verifier"
PUBLIC_INPUT = "/tests/data/daily_synthetic.nc"
PUBLIC_OUTPUT = "/app/results/heatwaves.nc"

# Each original fragment must appear exactly once in the committed reference.
# The expected error is asserted; an unrelated failure cannot count as a pass.
MUTANTS = (
    (
        "p95 substituted for p90",
        'np.percentile(reference[:, j, k][available[:, j, k]], 90, method="linear")',
        'np.percentile(reference[:, j, k][available[:, j, k]], 95, method="linear")',
        "moving-window p90 threshold mismatch",
    ),
    (
        "calendar window reduced from +/-7 days to zero",
        "in_window = np.minimum(distance, 365 - distance) <= 7",
        "in_window = np.minimum(distance, 365 - distance) <= 0",
        "moving-window p90 threshold mismatch",
    ),
    (
        "threshold equality counted as exceedance",
        "(target > threshold)",
        "(target >= threshold)",
        "exceedance_day differs",
    ),
    (
        "four-day runs incorrectly accepted",
        "if length >= 5:",
        "if length >= 4:",
        "heatwave_day differs",
    ),
    (
        "exactly five-day runs incorrectly rejected",
        "if length >= 5:",
        "if length >= 6:",
        "heatwave_day differs",
    ),
    (
        "300-sample boundary incorrectly requires 301",
        "samples[i] >= 300",
        "samples[i] >= 301",
        "moving-window p90 threshold mismatch",
    ),
    (
        "20-year coverage boundary incorrectly requires 21",
        "coverage_years[i] >= 20",
        "coverage_years[i] >= 21",
        "moving-window p90 threshold mismatch",
    ),
    (
        "missing target temperature treated as extreme heat",
        "np.isfinite(target) & np.isfinite(threshold) & (target > threshold)",
        "np.isfinite(threshold) & (np.nan_to_num(target, nan=999.0) > threshold)",
        "exceedance_day differs",
    ),
    (
        "missing required July target date accepted",
        "if not targets.equals(expected_target) or not baseline_mask.any():",
        "if not baseline_mask.any():",
        "Invalid input not rejected",
    ),
    (
        "unsupported February 29 accepted",
        'if t.month == 2 and t.day == 29:\n        raise ValueError("February 29 is unsupported in the 365-day climatology")',
        "if t.month == 2 and t.day == 29:\n        return 59",
        "Invalid input not rejected",
    ),
)


def docker(workdir: Path, *command: str) -> subprocess.CompletedProcess[str]:
    """Use an isolated temporary /app and the existing verifier-image /tests."""
    mount = f"type=bind,source={workdir.resolve()},target=/app"
    return subprocess.run(
        ["docker", "run", "--rm", "--network", "none", "--mount", mount,
         VERIFIER_IMAGE, *command],
        capture_output=True, text=True, errors="replace", check=False, timeout=600,
    )


def output_text(proc: subprocess.CompletedProcess[str]) -> str:
    return (proc.stdout + "\n" + proc.stderr).strip()


def run_public(workdir: Path) -> None:
    proc = docker(workdir, "python", "/app/solve.py", "--input", PUBLIC_INPUT,
                  "--output", PUBLIC_OUTPUT)
    if proc.returncode != 0:
        raise RuntimeError("Solver failed on the valid public fixture; test inconclusive:\n"
                           + output_text(proc)[-2500:])
    if not (workdir / "results" / "heatwaves.nc").is_file():
        raise RuntimeError("Solver did not write /app/results/heatwaves.nc")


def grade(workdir: Path, *, expect_pass: bool, expected_failure: str = "") -> str:
    # Invoke verify.py directly so an AssertionError makes Docker exit nonzero.
    proc = docker(workdir, "python", "/tests/verify.py")
    log = output_text(proc)
    if expect_pass:
        if proc.returncode != 0 or "ALL HEATWAVE P90 CHECKS PASSED" not in log:
            raise RuntimeError("Correct reference was not accepted:\n" + log[-2500:])
        return "ALL HEATWAVE P90 CHECKS PASSED"
    scientific_errors = [line.strip() for line in log.splitlines()
                         if "AssertionError:" in line]
    if proc.returncode == 0 or not scientific_errors:
        raise RuntimeError("Fault not rejected by scientific assertion:\n" + log[-2500:])
    if expected_failure not in scientific_errors[-1]:
        raise RuntimeError("Unexpected rejection reason:\n" + log[-2500:])
    return scientific_errors[-1]


def check_candidate(candidate: str, *, expect_pass: bool,
                    expected_failure: str = "") -> str:
    # Catch accidental syntactic mutations before starting Docker.
    compile(candidate, "solve.py", "exec")
    with tempfile.TemporaryDirectory(prefix="gcb-heatwave-fault-") as td:
        workdir = Path(td)
        (workdir / "results").mkdir()
        (workdir / "solve.py").write_text(candidate, encoding="utf-8")
        run_public(workdir)
        return grade(workdir, expect_pass=expect_pass,
                     expected_failure=expected_failure)


def check_hardcoding(reference: str) -> str:
    with tempfile.TemporaryDirectory(prefix="gcb-heatwave-hardcode-") as td:
        workdir = Path(td)
        (workdir / "results").mkdir()
        submission = workdir / "solve.py"
        submission.write_text(reference, encoding="utf-8")
        run_public(workdir)  # Build the canned answer with the reference solver.
        shutil.copyfile(workdir / "results" / "heatwaves.nc", workdir / "canned.nc")
        submission.write_text(
            "import argparse, shutil\n"
            "from pathlib import Path\n"
            "p = argparse.ArgumentParser()\n"
            "p.add_argument('--input', required=True)\n"
            "p.add_argument('--output', required=True)\n"
            "a = p.parse_args()\n"
            "Path(a.output).parent.mkdir(parents=True, exist_ok=True)\n"
            "shutil.copyfile('/app/canned.nc', a.output)\n",
            encoding="utf-8",
        )
        (workdir / "results" / "heatwaves.nc").unlink()
        run_public(workdir)  # Canned output must look valid on the public fixture.
        return grade(workdir, expect_pass=False, expected_failure="unseen fixture:")


def main() -> int:
    if not SOLUTION.is_file():
        print(f"ERROR: Missing reference solution: {SOLUTION}")
        return 1
    if not (ROOT / "tests" / "data" / "daily_synthetic.nc").is_file():
        print("ERROR: Missing tests/data/daily_synthetic.nc")
        return 1
    if shutil.which("docker") is None:
        print("ERROR: Docker CLI not found. Use Anaconda PowerShell with Docker Desktop running.")
        return 1
    image = subprocess.run(["docker", "image", "inspect", VERIFIER_IMAGE],
                           capture_output=True, text=True, check=False)
    if image.returncode != 0:
        print(f"ERROR: Missing {VERIFIER_IMAGE} image. Build tests/Dockerfile first.")
        return 1

    reference = SOLUTION.read_text(encoding="utf-8")
    total = 2 + len(MUTANTS)
    passed = 0
    try:
        check_candidate(reference, expect_pass=True)
        print("[PASS] Correct reference accepted by isolated verifier")
        passed += 1

        for label, original, replacement, expected_failure in MUTANTS:
            occurrences = reference.count(original)
            if occurrences != 1:
                raise RuntimeError(f"Mutation source mismatch ({occurrences} matches): {label}")
            reason = check_candidate(reference.replace(original, replacement, 1),
                                     expect_pass=False, expected_failure=expected_failure)
            print(f"[PASS] Rejected: {label}\n       {reason}")
            passed += 1

        reason = check_hardcoding(reference)
        print(f"[PASS] Rejected: canned public output / hardcoding\n       {reason}")
        passed += 1
    except (OSError, RuntimeError, SyntaxError, subprocess.TimeoutExpired) as exc:
        print(f"\n[FAIL] {exc}")
        print(f"Completed {passed}/{total} controls; treat this as an unverified regression run.")
        return 1
    print(f"\nSUCCESS: {passed}/{total} controls produced the expected outcomes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
