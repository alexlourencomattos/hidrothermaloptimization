"""Analytical cases and independent physical/optimality checks."""

import unittest
from dataclasses import replace

from model import Case, Thermal, build, dispatch, example, physical_residuals
from solvers import admm, interior_point


class HydrothermalTests(unittest.TestCase):
    def check_solvers(self, case, expected=None):
        qp = build(case)
        results = [solver(qp, tolerance=1e-7) for solver in (interior_point, admm)]
        for result in results:
            self.assertTrue(result.converged)
            self.assertLess(qp.violation(result.x), 2e-7)
            self.assertLess(max(physical_residuals(case, result.x)), 2e-7)
            if expected is not None:
                self.assertAlmostEqual(qp.objective(result.x), expected, delta=2e-5)
        self.assertAlmostEqual(qp.objective(results[0].x), qp.objective(results[1].x), delta=2e-5)
        return qp.objective(results[0].x), results

    def test_single_period_analytical(self):
        # Available water: 3; demand: 5. Thus g=2, u=3, v=s=0.
        case = Case((5.0,), (1.0,), (Thermal("T", 10.0, 0.5, 1.0),),
                    initial_storage=2.0, storage_capacity=10.0, turbine_capacity=10.0, final_storage=0.0)
        self.check_solvers(case, expected=4.0)

    def test_thermal_economic_dispatch(self):
        # No usable water; equal marginal costs imply g1=4, g2=2.
        case = Case((6.0,), (0.0,), (Thermal("A", 10.0, 0.5, 0.0), Thermal("B", 10.0, 1.0, 0.0)),
                    initial_storage=2.0, final_storage=2.0)
        _, results = self.check_solvers(case, expected=12.0)
        for result in results:
            generation = dispatch(case, result.x)[0]["thermal"]
            self.assertAlmostEqual(generation[0], 4.0, places=5)
            self.assertAlmostEqual(generation[1], 2.0, places=5)

    def test_scenarios_and_monotonic_cost(self):
        base, _ = self.check_solvers(example())
        dry, _ = self.check_solvers(example("dry"))
        reserve, _ = self.check_solvers(example("reserve"))
        self.assertGreater(dry, base)
        self.assertGreater(reserve, base)

    def test_infeasible_case_does_not_report_success(self):
        qp = build(replace(example(), demand=(100.0,) * 6))
        result = admm(qp, max_iterations=100)
        self.assertFalse(result.converged)
        self.assertGreater(qp.violation(result.x), 1.0)

    def test_invalid_parameters(self):
        with self.assertRaises(ValueError):
            build(replace(example(), final_storage=20.0))
        with self.assertRaises(ValueError):
            build(replace(example(), inflow=(1.0,)))
        with self.assertRaises(ValueError):
            admm(build(example()), rho=0.0)


if __name__ == "__main__":
    unittest.main()
