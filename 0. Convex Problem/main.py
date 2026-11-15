"""Run: python main.py --scenario base --output results/base"""

import argparse
import csv
import json
import platform
from dataclasses import asdict
from math import isfinite
from pathlib import Path
from time import perf_counter

from model import build, dispatch, example, physical_residuals
from solvers import admm, interior_point


def run():
    parser = argparse.ArgumentParser(description="Hydrothermal convex QP: pure Python.")
    parser.add_argument("--scenario", choices=("base", "dry", "reserve"), default="base")
    parser.add_argument("--tolerance", type=float, default=1e-6)
    parser.add_argument("--rho", type=float, default=1.0, help="ADMM penalty parameter")
    parser.add_argument("--output", type=Path, help="Optional CSV output directory")
    args = parser.parse_args()
    if not all(isfinite(v) and v > 0 for v in (args.tolerance, args.rho)):
        parser.error("tolerance and rho must be positive")
    case = example(args.scenario)
    qp = build(case)
    print(f"Scenario: {args.scenario} | variables: {len(qp.c)} | constraints: {len(qp.a)}")
    print("Costs and physical quantities use normalized study units.\n")
    results, summary = {}, []
    if args.output:
        args.output.mkdir(parents=True, exist_ok=True)
        metadata = dict(scenario=args.scenario, tolerance=args.tolerance, rho=args.rho,
                        python=platform.python_version(), platform=platform.platform(), case=asdict(case))
        (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    for name, solver, options in (("interior_point", interior_point, {}), ("admm", admm, {"rho": args.rho})):
        start = perf_counter()
        result = solver(qp, tolerance=args.tolerance, **options)
        seconds = perf_counter() - start
        results[name] = result
        energy, water = physical_residuals(case, result.x)
        last = result.history[-1]
        summary.append((name, result.converged, result.iterations, seconds, qp.objective(result.x),
                        qp.violation(result.x), energy, water, last[3], last[4]))
        print(f"{name}: converged={result.converged}, iterations={result.iterations}, "
              f"cost={qp.objective(result.x):.8f}, seconds={seconds:.4f}")
        print(f"  constraint violation={qp.violation(result.x):.3e}; energy={energy:.3e}; water={water:.3e}")
        if args.output:
            with (args.output / f"{name}_history.csv").open("w", newline="", encoding="utf-8") as stream:
                writer = csv.writer(stream)
                writer.writerow(("iteration", "objective", "primal_residual", "dual_residual", "mean_complementarity"))
                writer.writerows(result.history)
            with (args.output / f"{name}_dispatch.csv").open("w", newline="", encoding="utf-8") as stream:
                writer = csv.writer(stream)
                writer.writerow(("period", "demand", "inflow", *(p.name for p in case.thermals), "hydro", "release", "storage", "spill"))
                for row in dispatch(case, result.x):
                    writer.writerow((row["period"], row["demand"], row["inflow"], *row["thermal"],
                                     row["hydro"], row["release"], row["storage"], row["spill"]))
    if args.output:
        with (args.output / "summary.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(("algorithm", "converged", "iterations", "seconds", "objective", "constraint_violation",
                             "energy_residual", "water_residual", "dual_residual", "mean_complementarity"))
            writer.writerows(summary)
    print("\nDispatch from interior-point method:")
    for row in dispatch(case, results["interior_point"].x):
        thermal = ", ".join(f"{p.name}={g:.4f}" for p, g in zip(case.thermals, row["thermal"]))
        print(f"  t={row['period']}: {thermal}, hydro={row['hydro']:.4f}, "
              f"storage={row['storage']:.4f}, spill={row['spill']:.4f}")
    if all(result.converged for result in results.values()):
        gap = abs(qp.objective(results["admm"].x) - qp.objective(results["interior_point"].x))
        print(f"\nAbsolute objective difference: {gap:.3e}")
    else:
        raise SystemExit("At least one solver did not converge; do not interpret its dispatch as optimal.")


if __name__ == "__main__":
    run()
