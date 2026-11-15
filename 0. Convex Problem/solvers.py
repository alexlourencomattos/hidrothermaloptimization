"""Dense educational QP solvers. Standard library only; not production solvers.

min 0.5*x' H x + c' x, subject to lower <= A*x <= upper.
Equal lower/upper values represent equality constraints.
"""

from dataclasses import dataclass
from math import isfinite, sqrt


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def matvec(a, x):
    return [dot(row, x) for row in a]


def transpose_vec(a, x, n):
    return [sum(row[j] * value for row, value in zip(a, x)) for j in range(n)]


def norm(x):
    return max((abs(v) for v in x), default=0.0)


def solve(a, b):
    """Gaussian elimination with partial pivoting (small dense systems)."""
    n = len(b)
    rows = [list(row) + [value] for row, value in zip(a, b)]
    for k in range(n):
        pivot = max(range(k, n), key=lambda i: abs(rows[i][k]))
        if abs(rows[pivot][k]) < 1e-14:
            raise ArithmeticError("Singular Newton system; inspect model scaling.")
        rows[k], rows[pivot] = rows[pivot], rows[k]
        for i in range(k + 1, n):
            factor = rows[i][k] / rows[k][k]
            for j in range(k + 1, n + 1):
                rows[i][j] -= factor * rows[k][j]
            rows[i][k] = 0.0
    x = [0.0] * n
    for i in reversed(range(n)):
        x[i] = (rows[i][n] - sum(rows[i][j] * x[j] for j in range(i + 1, n))) / rows[i][i]
    return x


def cholesky(a):
    n = len(a)
    out = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            value = a[i][j] - sum(out[i][k] * out[j][k] for k in range(j))
            if i == j:
                if value <= 0:
                    raise ArithmeticError("Matrix is not positive definite.")
                out[i][j] = sqrt(value)
            else:
                out[i][j] = value / out[j][j]
    return out


def cholesky_solve(factor, b):
    n = len(b)
    y = [0.0] * n
    for i in range(n):
        y[i] = (b[i] - sum(factor[i][j] * y[j] for j in range(i))) / factor[i][i]
    x = [0.0] * n
    for i in reversed(range(n)):
        x[i] = (y[i] - sum(factor[j][i] * x[j] for j in range(i + 1, n))) / factor[i][i]
    return x


@dataclass
class QP:
    h: list
    c: list
    a: list
    lower: list
    upper: list

    def objective(self, x):
        return 0.5 * dot(x, matvec(self.h, x)) + dot(self.c, x)

    def violation(self, x):
        return max((max(lo - value, value - hi, 0.0)
                    for value, lo, hi in zip(matvec(self.a, x), self.lower, self.upper)), default=0.0)


@dataclass
class Result:
    x: list
    converged: bool
    iterations: int
    history: list


def admm(qp, tolerance=1e-6, max_iterations=30000, rho=1.0):
    """Unrelaxed ADMM with fixed rho and cached Cholesky factorization.

    Stop on absolute infinity norms of primal and dual ADMM residuals.
    """
    if not isfinite(rho) or not isfinite(tolerance) or rho <= 0 or tolerance <= 0 or max_iterations < 1:
        raise ValueError("rho, tolerance and max_iterations must be positive.")
    n, m = len(qp.c), len(qp.a)
    system = [[qp.h[i][j] + rho * sum(row[i] * row[j] for row in qp.a)
               for j in range(n)] for i in range(n)]
    factor = cholesky(system)
    z = [min(max(0.0, lo), hi) for lo, hi in zip(qp.lower, qp.upper)]
    y = [0.0] * m
    history = []
    for iteration in range(1, max_iterations + 1):
        rhs = transpose_vec(qp.a, [rho * zi - yi for zi, yi in zip(z, y)], n)
        x = cholesky_solve(factor, [v - c for v, c in zip(rhs, qp.c)])
        ax = matvec(qp.a, x)
        previous = z
        z = [min(max(value + yi / rho, lo), hi)
             for value, yi, lo, hi in zip(ax, y, qp.lower, qp.upper)]
        residual = [value - zi for value, zi in zip(ax, z)]
        y = [yi + rho * ri for yi, ri in zip(y, residual)]
        primal = norm(residual)
        dual = norm(transpose_vec(qp.a, [rho * (zi - old) for zi, old in zip(z, previous)], n))
        history.append((iteration, qp.objective(x), primal, dual, None))
        if max(primal, dual) <= tolerance:
            return Result(x, True, iteration, history)
    return Result(x, False, max_iterations, history)


def interior_point(qp, tolerance=1e-6, max_iterations=100):
    """Infeasible-start primal-dual method with fixed centering sigma=0.1.

    Positive slack/dual variables are maintained by fraction-to-boundary.
    Stops on primal feasibility, stationarity and mean complementarity.
    """
    if not isfinite(tolerance) or tolerance <= 0 or max_iterations < 1:
        raise ValueError("tolerance and max_iterations must be positive.")
    n = len(qp.c)
    equalities, targets, g, bounds = [], [], [], []
    for row, lo, hi in zip(qp.a, qp.lower, qp.upper):
        if lo == hi:
            equalities.append(row)
            targets.append(lo)
        else:
            if isfinite(hi):
                g.append(row)
                bounds.append(hi)
            if isfinite(lo):
                g.append([-v for v in row])
                bounds.append(-lo)
    p, m = len(equalities), len(g)
    if m == 0:
        raise ValueError("This implementation expects at least one inequality.")
    x, y = [0.0] * n, [0.0] * p
    slack = [max(1.0, b) for b in bounds]
    z = [1.0] * m
    history = []
    for iteration in range(max_iterations + 1):
        hx, gx, ex = matvec(qp.h, x), matvec(g, x), matvec(equalities, x)
        ety, gtz = transpose_vec(equalities, y, n), transpose_vec(g, z, n)
        rd = [hx[i] + qp.c[i] + ety[i] + gtz[i] for i in range(n)]
        re = [v - b for v, b in zip(ex, targets)]
        ri = [v + s - b for v, s, b in zip(gx, slack, bounds)]
        mu = dot(slack, z) / m
        primal, dual = max(norm(re), norm(ri)), norm(rd)
        history.append((iteration, qp.objective(x), primal, dual, mu))
        if max(primal, dual, mu) <= tolerance:
            return Result(x, True, iteration, history)
        if iteration == max_iterations:
            break
        rc = [s * zi - 0.1 * mu for s, zi in zip(slack, z)]
        weights = [zi / s for zi, s in zip(z, slack)]
        correction = [(rci - zi * rii) / s for rci, zi, rii, s in zip(rc, z, ri, slack)]
        gtcorrection = transpose_vec(g, correction, n)
        matrix = [[qp.h[i][j] + sum(w * row[i] * row[j] for w, row in zip(weights, g))
                   for j in range(n)] for i in range(n)]
        kkt = [matrix[i] + [row[i] for row in equalities] for i in range(n)]
        kkt += [list(row) + [0.0] * p for row in equalities]
        direction = solve(kkt, [-rd[i] + gtcorrection[i] for i in range(n)] + [-v for v in re])
        dx, dy = direction[:n], direction[n:]
        gdx = matvec(g, dx)
        ds = [-r - v for r, v in zip(ri, gdx)]
        dz = [(-r - zi * dsi) / s for r, zi, dsi, s in zip(rc, z, ds, slack)]
        alpha = min([1.0] + [-0.995 * v / dv for values, steps in ((slack, ds), (z, dz))
                              for v, dv in zip(values, steps) if dv < 0])
        x = [v + alpha * dv for v, dv in zip(x, dx)]
        y = [v + alpha * dv for v, dv in zip(y, dy)]
        slack = [v + alpha * dv for v, dv in zip(slack, ds)]
        z = [v + alpha * dv for v, dv in zip(z, dz)]
    return Result(x, False, max_iterations, history)
