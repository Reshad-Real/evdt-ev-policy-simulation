"""Multi-objective policy optimisation.

A compact NSGA-II implementation (fast non-dominated sorting, crowding-distance
selection, simulated-binary crossover and polynomial mutation) searches the
twenty-dimensional lever space for the Pareto-optimal frontier between net
present value, cumulative emissions avoided and network stress.  The search is
run against the surrogate emulator so that thousands of candidate policies can
be evaluated, and the resulting frontier members are then re-evaluated with the
full simulator to confirm that the surrogate did not mislead the search
(docs_reference: econ-moo-mcdm, chg-multiobj-data, grid-smart-robust).
"""
from __future__ import annotations

from typing import Callable

import numpy as np


# ---------------------------------------------------------------------------
# Dominance machinery
# ---------------------------------------------------------------------------
def fast_non_dominated_sort(objectives: np.ndarray) -> list[np.ndarray]:
    """Rank a population by Pareto dominance (objectives are minimised)."""
    n = objectives.shape[0]
    dominated: list[list[int]] = [[] for _ in range(n)]
    counts = np.zeros(n, dtype=int)
    fronts: list[list[int]] = [[]]
    for p in range(n):
        for q in range(n):
            if p == q:
                continue
            if np.all(objectives[p] <= objectives[q]) and np.any(objectives[p] < objectives[q]):
                dominated[p].append(q)
            elif np.all(objectives[q] <= objectives[p]) and np.any(objectives[q] < objectives[p]):
                counts[p] += 1
        if counts[p] == 0:
            fronts[0].append(p)
    i = 0
    while fronts[i]:
        nxt: list[int] = []
        for p in fronts[i]:
            for q in dominated[p]:
                counts[q] -= 1
                if counts[q] == 0:
                    nxt.append(q)
        i += 1
        fronts.append(nxt)
    return [np.array(f, dtype=int) for f in fronts[:-1]]


def crowding_distance(objectives: np.ndarray) -> np.ndarray:
    """Crowding distance within one front."""
    n, m = objectives.shape
    dist = np.zeros(n)
    if n <= 2:
        return np.full(n, np.inf)
    for j in range(m):
        idx = np.argsort(objectives[:, j])
        dist[idx[0]] = dist[idx[-1]] = np.inf
        span = objectives[idx[-1], j] - objectives[idx[0], j]
        if span < 1e-12:
            continue
        dist[idx[1:-1]] += (objectives[idx[2:], j] - objectives[idx[:-2], j]) / span
    return dist


# ---------------------------------------------------------------------------
# Variation operators
# ---------------------------------------------------------------------------
def sbx_crossover(p1: np.ndarray, p2: np.ndarray, rng: np.random.Generator,
                  eta: float = 15.0, prob: float = 0.9
                  ) -> tuple[np.ndarray, np.ndarray]:
    c1, c2 = p1.copy(), p2.copy()
    if rng.random() > prob:
        return c1, c2
    for i in range(p1.size):
        if rng.random() > 0.5:
            continue
        if abs(p1[i] - p2[i]) < 1e-12:
            continue
        u = rng.random()
        beta = (2.0 * u) ** (1.0 / (eta + 1.0)) if u <= 0.5 \
            else (1.0 / (2.0 * (1.0 - u))) ** (1.0 / (eta + 1.0))
        c1[i] = 0.5 * ((1 + beta) * p1[i] + (1 - beta) * p2[i])
        c2[i] = 0.5 * ((1 - beta) * p1[i] + (1 + beta) * p2[i])
    return np.clip(c1, 0.0, 1.0), np.clip(c2, 0.0, 1.0)


def polynomial_mutation(x: np.ndarray, rng: np.random.Generator,
                        eta: float = 20.0, prob: float | None = None) -> np.ndarray:
    y = x.copy()
    p = prob if prob is not None else 1.0 / x.size
    for i in range(x.size):
        if rng.random() > p:
            continue
        u = rng.random()
        delta = ((2.0 * u) ** (1.0 / (eta + 1.0)) - 1.0) if u < 0.5 \
            else (1.0 - (2.0 * (1.0 - u)) ** (1.0 / (eta + 1.0)))
        y[i] = float(np.clip(y[i] + delta, 0.0, 1.0))
    return y


# ---------------------------------------------------------------------------
# NSGA-II
# ---------------------------------------------------------------------------
def nsga2(evaluate: Callable[[np.ndarray], np.ndarray], n_var: int,
          n_obj: int, pop_size: int = 96, generations: int = 60,
          seed: int = 7) -> dict:
    """Minimise ``evaluate`` (population -> objective matrix) over the unit cube."""
    rng = np.random.default_rng(seed)
    pop = rng.random((pop_size, n_var))
    obj = evaluate(pop)
    history = []

    for gen in range(generations):
        # --- tournament selection on rank then crowding --------------------
        fronts = fast_non_dominated_sort(obj)
        rank = np.empty(pop_size, dtype=int)
        crowd = np.empty(pop_size)
        for r, f in enumerate(fronts):
            rank[f] = r
            crowd[f] = crowding_distance(obj[f])
        parents = np.empty_like(pop)
        for i in range(pop_size):
            a, b = rng.integers(0, pop_size, 2)
            better = a if (rank[a] < rank[b] or
                           (rank[a] == rank[b] and crowd[a] > crowd[b])) else b
            parents[i] = pop[better]

        # --- variation -----------------------------------------------------
        children = np.empty_like(pop)
        for i in range(0, pop_size, 2):
            c1, c2 = sbx_crossover(parents[i], parents[min(i + 1, pop_size - 1)], rng)
            children[i] = polynomial_mutation(c1, rng)
            if i + 1 < pop_size:
                children[i + 1] = polynomial_mutation(c2, rng)
        child_obj = evaluate(children)

        # --- environmental selection ---------------------------------------
        merged = np.vstack([pop, children])
        merged_obj = np.vstack([obj, child_obj])
        fronts = fast_non_dominated_sort(merged_obj)
        new_idx: list[int] = []
        for f in fronts:
            if len(new_idx) + f.size <= pop_size:
                new_idx.extend(f.tolist())
            else:
                d = crowding_distance(merged_obj[f])
                take = f[np.argsort(-d)][: pop_size - len(new_idx)]
                new_idx.extend(take.tolist())
                break
        pop = merged[new_idx]
        obj = merged_obj[new_idx]
        history.append({"generation": gen,
                        "best": obj.min(axis=0).tolist(),
                        "front_size": int(fast_non_dominated_sort(obj)[0].size)})

    fronts = fast_non_dominated_sort(obj)
    front = fronts[0]
    return {"population": pop, "objectives": obj,
            "pareto_x": pop[front], "pareto_f": obj[front],
            "history": history}


def hypervolume_2d(points: np.ndarray, reference: np.ndarray) -> float:
    """Two-dimensional hypervolume indicator for a minimisation front."""
    p = points[np.all(points < reference[None, :], axis=1)]
    if p.size == 0:
        return 0.0
    p = p[np.argsort(p[:, 0])]
    hv = 0.0
    prev_y = reference[1]
    for x, y in p:
        if y < prev_y:
            hv += (reference[0] - x) * (prev_y - y)
            prev_y = y
    return float(hv)


def knee_point(front: np.ndarray) -> int:
    """Index of the knee of a Pareto front by maximum distance to the chord."""
    if front.shape[0] < 3:
        return 0
    f = (front - front.min(axis=0)) / np.maximum(front.max(axis=0) - front.min(axis=0), 1e-12)
    a, b = f[np.argmin(f[:, 0])], f[np.argmin(f[:, 1])]
    ab = b - a
    nrm = np.linalg.norm(ab)
    if nrm < 1e-12:
        return 0
    # z-component of the 2-D cross product (np.cross no longer accepts 2-D
    # vectors in NumPy 2.5)
    rel = f - a
    d = np.abs(ab[0] * rel[:, 1] - ab[1] * rel[:, 0]) / nrm
    return int(np.argmax(d))
