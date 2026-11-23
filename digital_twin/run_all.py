"""Execute the whole pipeline end to end (revision of TTE-Reg-2026-08-3015).

Order matters: the calibration writes the adoption coefficients the scenarios
use; the revision analyses read the deterministic results; validation reads
both.  Stages 2 and 3 are the expensive ones; pass ``--fast`` to skip them.
The TTE manuscript itself is built by the scripts in ../literature (see the
README in "Manuscript TTE/Submission").

Usage:
    py -3 run_all.py            # full pipeline
    py -3 run_all.py --fast     # without uncertainty and optimisation
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIT = HERE.parent / "literature"

FULL = [
    ("stage -1 device parameters fitted to datasheets, light-load fit",
     HERE / "fit_devices.py"),
    ("stage 0  adoption calibration and emission reconciliation", HERE / "calibrate.py"),
    ("stage 1  deterministic scenario campaign", HERE / "run_deterministic.py"),
    ("stage 1b analyses added in the revision", HERE / "run_revision_analyses.py"),
    ("stage 4  verification and validation", HERE / "run_validation.py"),
    ("stage 2  uncertainty and Morris screening", HERE / "run_uncertainty.py"),
    ("stage 3  surrogate, Sobol and NSGA-II", HERE / "run_optimization.py"),
    ("outputs  TTE tables", LIT / "tte_tables.py"),
    ("outputs  TTE figures", LIT / "tte_figures.py"),
    ("outputs  TTE numbers for the text", LIT / "tte_numbers.py"),
]
FAST_SKIP = {"run_uncertainty.py", "run_optimization.py"}


def main() -> None:
    fast = "--fast" in sys.argv
    t0 = time.perf_counter()
    for label, script in FULL:
        if fast and script.name in FAST_SKIP:
            print(f"\n=== SKIPPED ({label}) -- --fast\n", flush=True)
            continue
        print(f"\n=== {label}  [{script.name}]\n", flush=True)
        t = time.perf_counter()
        rc = subprocess.run([sys.executable, str(script)], cwd=script.parent).returncode
        if rc != 0:
            print(f"!! {script.name} exited with code {rc}", flush=True)
            sys.exit(rc)
        print(f"--- {script.name} finished in {time.perf_counter()-t:.1f} s", flush=True)
    print(f"\nPipeline complete in {time.perf_counter()-t0:.1f} s")


if __name__ == "__main__":
    main()
