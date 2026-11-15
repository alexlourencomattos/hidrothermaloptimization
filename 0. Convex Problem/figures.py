"""Recompute chart data with stdlib Python; render PNGs using Windows .NET.

Run from any directory: python figures.py
No Python packages are required. Rendering requires Windows PowerShell 5.1.
"""

import csv
import json
from pathlib import Path
import subprocess

from model import build, dispatch, example
from solvers import admm, interior_point


def write_csv(path, header, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(rows)


def export_data(destination):
    destination.mkdir(parents=True, exist_ok=True)
    storage, costs = [], []
    for scenario in ("base", "dry", "reserve"):
        case = example(scenario)
        qp = build(case)
        result = interior_point(qp)
        if not result.converged or qp.violation(result.x) > 1e-6:
            raise RuntimeError(f"Cannot plot an unverified solution: {scenario}")
        rows = dispatch(case, result.x)
        costs.append((scenario, qp.objective(result.x), qp.violation(result.x), result.iterations))
        storage.append((scenario, 0, case.initial_storage, case.storage_capacity, case.final_storage))
        storage.extend((scenario, row["period"], row["storage"], case.storage_capacity, case.final_storage)
                       for row in rows)
        if scenario == "base":
            write_csv(destination / "dispatch.csv", ("period", "demand", "T1", "T2", "hydro"),
                      ((r["period"], r["demand"], *r["thermal"], r["hydro"]) for r in rows))
            histories = []
            for name, solved in (("interior_point", result), ("admm", admm(qp))):
                if not solved.converged or qp.violation(solved.x) > 1e-6:
                    raise RuntimeError(f"Cannot plot an unverified solution: {name}")
                histories.extend((name, *entry) for entry in solved.history)
            write_csv(destination / "convergence.csv",
                      ("algorithm", "iteration", "objective", "primal", "dual", "complementarity"), histories)
    write_csv(destination / "storage.csv", ("scenario", "period", "storage", "capacity", "final_target"), storage)
    write_csv(destination / "costs.csv", ("scenario", "objective", "constraint_violation", "iterations"), costs)
    (destination / "parameters.json").write_text(json.dumps(dict(
        tolerance=1e-6, rho=1.0, units="normalized", storage_solver="interior_point",
        convergence_note="Residual definitions differ between algorithms; see ESTUDO.md.",
        data_source="model.example; recomputed by figures.py", scenarios=["base", "dry", "reserve"]),
        indent=2), encoding="utf-8")


def main():
    root = Path(__file__).resolve().parent.parent
    destination = root / "figures" / "data"
    export_data(destination)
    subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    str(Path(__file__).with_name("plot_charts.ps1")), "-OutputDirectory", str(root / "figures")],
                   check=True)
    print(f"Figures and numerical source data: {root / 'figures'}")


if __name__ == "__main__":
    main()
