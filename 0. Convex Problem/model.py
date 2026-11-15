"""Deterministic hydrothermal dispatch in normalized, compatible units."""

from dataclasses import dataclass, replace
from math import inf, isfinite

from solvers import QP


@dataclass(frozen=True)
class Thermal:
    name: str
    capacity: float
    quadratic: float
    linear: float


@dataclass(frozen=True)
class Case:
    demand: tuple
    inflow: tuple
    thermals: tuple
    initial_storage: float = 5.0
    storage_capacity: float = 12.0
    turbine_capacity: float = 4.0
    productivity: float = 1.0
    final_storage: float = 5.0

    def validate(self):
        if not self.demand or len(self.demand) != len(self.inflow) or not self.thermals:
            raise ValueError("Demand/inflow must have equal, nonzero length; thermals are required.")
        numbers = (*self.demand, *self.inflow, self.initial_storage, self.storage_capacity,
                   self.turbine_capacity, self.productivity, self.final_storage)
        if any(not isfinite(v) or v < 0 for v in numbers):
            raise ValueError("Case values must be finite and nonnegative.")
        if self.productivity <= 0 or self.storage_capacity <= 0 or self.turbine_capacity <= 0:
            raise ValueError("Productivity and capacities must be positive.")
        if max(self.initial_storage, self.final_storage) > self.storage_capacity:
            raise ValueError("Initial/final storage exceeds reservoir capacity.")
        for plant in self.thermals:
            if any(not isfinite(v) for v in (plant.capacity, plant.quadratic, plant.linear)):
                raise ValueError("Thermal parameters must be finite.")
            if plant.capacity <= 0 or plant.quadratic <= 0 or plant.linear < 0:
                raise ValueError("Thermal capacity/quadratic cost must be positive; linear cost nonnegative.")


def example(scenario="base"):
    case = Case(demand=(5.0, 6.0, 8.0, 9.0, 7.0, 5.0),
                inflow=(2.0, 1.0, 1.0, 2.0, 3.0, 2.0),
                thermals=(Thermal("T1", 5.0, 0.4, 1.0), Thermal("T2", 4.0, 0.8, 2.0)))
    if scenario == "dry":
        return replace(case, inflow=tuple(0.5 * v for v in case.inflow))
    if scenario == "reserve":
        return replace(case, final_storage=8.0)
    if scenario != "base":
        raise ValueError("Unknown scenario.")
    return case


def build(case):
    case.validate()
    periods, plants = len(case.demand), len(case.thermals)
    width = plants + 3  # g_1,...,g_J, turbine release, storage, spill
    n = periods * width
    h, c = [[0.0] * n for _ in range(n)], [0.0] * n
    a, lower, upper = [], [], []

    def constraint(entries, lo, hi):
        row = [0.0] * n
        for index, value in entries:
            row[index] = value
        a.append(row)
        lower.append(lo)
        upper.append(hi)

    for t in range(periods):
        offset = t * width
        for j, plant in enumerate(case.thermals):
            h[offset + j][offset + j] = 2 * plant.quadratic
            c[offset + j] = plant.linear
            constraint([(offset + j, 1.0)], 0.0, plant.capacity)
        u, v, s = offset + plants, offset + plants + 1, offset + plants + 2
        constraint([(u, 1.0)], 0.0, case.turbine_capacity)
        constraint([(v, 1.0)], case.final_storage if t == periods - 1 else 0.0, case.storage_capacity)
        constraint([(s, 1.0)], 0.0, inf)
        constraint([(offset + j, 1.0) for j in range(plants)] + [(u, case.productivity)],
                   case.demand[t], case.demand[t])
        water = [(v, 1.0), (u, 1.0), (s, 1.0)]
        rhs = case.inflow[t]
        if t == 0:
            rhs += case.initial_storage
        else:
            water.append((v - width, -1.0))
        constraint(water, rhs, rhs)
    return QP(h, c, a, lower, upper)


def dispatch(case, x):
    plants = len(case.thermals)
    width = plants + 3
    return [dict(period=t + 1, demand=case.demand[t], inflow=case.inflow[t],
                 thermal=x[t * width:t * width + plants],
                 hydro=case.productivity * x[t * width + plants],
                 release=x[t * width + plants], storage=x[t * width + plants + 1],
                 spill=x[t * width + plants + 2]) for t in range(len(case.demand))]


def physical_residuals(case, x):
    rows = dispatch(case, x)
    energy, water = 0.0, 0.0
    previous = case.initial_storage
    for row in rows:
        energy = max(energy, abs(sum(row["thermal"]) + row["hydro"] - row["demand"]))
        water = max(water, abs(previous + row["inflow"] - row["release"] - row["spill"] - row["storage"]))
        previous = row["storage"]
    return energy, water
