"""Interchangeable shortest-path and bounded rolling-horizon coordinators."""
from __future__ import annotations

import heapq
from collections import deque
from types import MappingProxyType

from .model import Decision, Snapshot, action_between

PLANNERS = ("dynamic", "fixed", "reservations")


def priority_order(snapshot, dynamic=True):
    return tuple(c.id for c in sorted(snapshot.vehicles,
                 key=lambda c: (-c.wait_age if dynamic else 0, c.id)))


def route_without_closures(network, start, goal, blocked):
    if not blocked:
        return network.route(start, goal)
    queue = deque([start])
    parent = {start: None}
    while queue:
        a = queue.popleft()
        if a == goal:
            path = []
            while a is not None:
                path.append(a)
                a = parent[a]
            return tuple(reversed(path))
        for b in network.adjacency[a]:
            if b not in blocked and b not in parent:
                parent[b] = a
                queue.append(b)
    return ()


class ShortestPlanner:
    def __init__(self, dynamic=True):
        self.dynamic = dynamic
        self.name = "dynamic" if dynamic else "fixed"

    def plan(self, snapshot: Snapshot):
        actions, waits = {}, {}
        for car in snapshot.vehicles:
            if car.busy or car.cell == car.goal:
                actions[car.id] = 0
                continue
            path = route_without_closures(snapshot.network, car.cell, car.goal,
                                          snapshot.blocked_cells)
            actions[car.id] = action_between(path[0], path[1]) if len(path) > 1 else 0
            if not path:
                waits[car.id] = "unreachable_goal"
        return Decision(snapshot.tick, MappingProxyType(actions),
                        priority_order(snapshot, self.dynamic),
                        MappingProxyType({"search_failures": len(waits), "expanded": 0}),
                        MappingProxyType(waits))


class ReservationPlanner:
    """Prioritized space-time search; always retains a feasible joint incumbent.

    Other vehicles start with full-horizon holds. Replacing one hold is allowed
    only if its entire route (including its endpoint) is feasible. This is
    deliberately conservative and provides no deadlock-freedom guarantee.
    """
    name = "reservations"

    def __init__(self, horizon=10, max_expansions=5000):
        if horizon < 1 or max_expansions < 1:
            raise ValueError("positive horizon and search budget required")
        self.horizon = horizon
        self.max_expansions = max_expansions

    def plan(self, snapshot: Snapshot):
        h = self.horizon
        order = priority_order(snapshot)
        cars = {c.id: c for c in snapshot.vehicles}
        vertices = {(c.cell, t): c.id for c in snapshot.vehicles for t in range(h + 1)}
        edges = {}
        paths = {c.id: [c.cell] * (h + 1) for c in snapshot.vehicles}
        actions, waits, blockers = {}, {}, {}
        expanded, failures = 0, 0
        for name in order:
            car = cars[name]
            if car.busy or car.cell == car.goal:
                actions[name] = 0
                continue
            for t in range(1, h + 1):
                del vertices[(car.cell, t)]
            path, count, blocker = self._search(snapshot, car, vertices, edges)
            expanded += count
            if path is None:
                path = [car.cell] * (h + 1)
                failures += 1
                waits[name] = "reservation_search_limit" if count >= self.max_expansions else "no_reserved_route"
            paths[name] = path
            for t, cell in enumerate(path):
                if t:
                    vertices[(cell, t)] = name
                    edges[(path[t-1], cell, t)] = name
            actions[name] = action_between(path[0], path[1])
            if actions[name] == 0:
                waits.setdefault(name, "reservation_wait")
                if blocker:
                    blockers[name] = blocker
        # Validate all intervals before dispatching any prefix.
        for t in range(1, h + 1):
            cells = [paths[n][t] for n in order]
            if len(set(cells)) != len(cells):
                raise AssertionError("reservation incumbent contains vertex conflict")
            transitions = {(paths[n][t-1], paths[n][t]): n for n in order}
            if any(a != b and (b, a) in transitions for a, b in transitions):
                raise AssertionError("reservation incumbent contains opposite-edge conflict")
        return Decision(snapshot.tick, MappingProxyType(actions), order,
                        MappingProxyType({"search_failures": failures, "expanded": expanded}),
                        MappingProxyType(waits), MappingProxyType(blockers))

    def _search(self, snapshot, car, vertices, edges):
        dist = snapshot.network.distances(car.goal)
        if car.cell not in dist:
            return None, 0, None
        # Full-horizon paths make all endpoints explicitly safe and occupied.
        start = (car.cell, 0)
        parent = {start: None}
        queue = [(dist[car.cell], dist[car.cell], 0, car.cell)]
        count, blocking = 0, None
        best = None
        best_score = (float("inf"), float("inf"))
        while queue and count < self.max_expansions:
            _, _, time, cell = heapq.heappop(queue)
            count += 1
            state = (cell, time)
            if time == self.horizon:
                score = (dist.get(cell, float("inf")), cell != car.goal)
                if score < best_score:
                    best, best_score = state, score
                if cell == car.goal:
                    break
                continue
            # A goal is held until the horizon, modeling subsequent handover conservatively.
            neighbors = (cell,) if cell == car.goal else (*snapshot.network.adjacency[cell], cell)
            for dest in neighbors:
                if dest in snapshot.blocked_cells and dest != cell:
                    continue
                owner = vertices.get((dest, time + 1))
                opposite = edges.get((dest, cell, time + 1))
                if owner or (dest != cell and opposite):
                    if time == 0 and dest != cell:
                        blocking = owner or opposite
                    continue
                nxt = (dest, time + 1)
                if nxt not in parent:
                    parent[nxt] = state
                    remaining = dist.get(dest, 1_000_000)
                    heapq.heappush(queue, (time + 1 + remaining, remaining, time + 1, dest))
        if best is None:
            return None, count, blocking
        path = []
        while best is not None:
            path.append(best[0])
            best = parent[best]
        return list(reversed(path)), count, blocking


def make_planner(name, horizon=10):
    if name not in PLANNERS:
        raise ValueError(f"unknown planner {name!r}")
    return ReservationPlanner(horizon) if name == "reservations" else ShortestPlanner(name == "dynamic")
