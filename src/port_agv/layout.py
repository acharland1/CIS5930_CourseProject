"""Synthetic 40 x 30 yard; routing topology is separate from occupancy."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from .model import Cell


@dataclass(frozen=True)
class Pad:
    name: str
    cell: Cell
    queue: tuple[Cell, ...]
    kind: str


class Network:
    width = 40
    height = 30
    version = "synthetic-yard-v1"

    def __init__(self, layout="open"):
        if layout not in ("open", "bottleneck"):
            raise ValueError("unknown layout")
        self.layout = layout
        edges: dict[Cell, set[Cell]] = {}

        def path(points, two_way=False):
            for a, b in zip(points, points[1:]):
                edges.setdefault(a, set()).add(b)
                edges.setdefault(b, set())
                if two_way:
                    edges[b].add(a)

        for y, east in ((5, True), (11, False), (17, True), (23, False)):
            xs = range(3, 37) if east else range(36, 2, -1)
            path([(x, y) for x in xs])
        path([(36, y) for y in range(5, 24)])
        path([(3, y) for y in range(23, 4, -1)])
        if layout == "open":
            path([(14, y) for y in range(5, 24)])
            path([(25, y) for y in range(23, 4, -1)])
        else:
            path([(19, y) for y in range(5, 24)], two_way=True)

        pads = {}
        for name, x in (("Q1", 8), ("Q2", 30)):
            points = [(x-2, 5), (x-2, 4), (x-2, 3), (x-1, 3),
                      (x, 3), (x+1, 3), (x+2, 3), (x+2, 4), (x+2, 5)]
            path(points)
            pads[name] = Pad(name, (x, 3), tuple(points[1:4]), "pickup")
        for name, x in (("D1", 10), ("D2", 30)):
            points = [(x+2, 23), (x+2, 24), (x+2, 25), (x+1, 25),
                      (x, 25), (x-1, 25), (x-2, 25), (x-2, 24), (x-2, 23)]
            path(points)
            pads[name] = Pad(name, (x, 25), tuple(points[1:4]), "dropoff")
        homes = tuple((x, 19) for x in range(5, 35) if x not in (14, 19, 25))
        for x, y in homes:
            path([(x, 17), (x, 18), (x, y)], two_way=True)
        for x in (8, 9, 10):
            path([(x, 11), (x, 10), (x, 9)], two_way=True)
        homes += tuple((x, 9) for x in (8, 9, 10))

        self.adjacency: Mapping[Cell, tuple[Cell, ...]] = MappingProxyType(
            {a: tuple(sorted(bs)) for a, bs in sorted(edges.items())})
        self.pads: Mapping[str, Pad] = MappingProxyType(pads)
        self.homes = homes
        self.queue_pad = MappingProxyType({c: name for name, pad in pads.items()
                                           for c in pad.queue})
        self.pad_at = MappingProxyType({pad.cell: name for name, pad in pads.items()})
        reverse = {c: [] for c in self.adjacency}
        for a, bs in self.adjacency.items():
            for b in bs:
                reverse[b].append(a)
        self.reverse = MappingProxyType({c: tuple(sorted(bs)) for c, bs in reverse.items()})
        self._distances: dict[Cell, dict[Cell, int]] = {}

    def distances(self, goal: Cell) -> Mapping[Cell, int]:
        if goal not in self.adjacency:
            return MappingProxyType({})
        if goal not in self._distances:
            dist = {goal: 0}
            queue = deque([goal])
            while queue:
                b = queue.popleft()
                for a in self.reverse[b]:
                    if a not in dist:
                        dist[a] = dist[b] + 1
                        queue.append(a)
            self._distances[goal] = dist
        return MappingProxyType(self._distances[goal])

    def route(self, start: Cell, goal: Cell) -> tuple[Cell, ...]:
        dist = self.distances(goal)
        if start not in dist:
            return ()
        result = [start]
        while result[-1] != goal:
            result.append(next(b for b in self.adjacency[result[-1]]
                               if dist.get(b) == dist[result[-1]] - 1))
        return tuple(result)

    def validate(self):
        relevant = self.homes + tuple(p.cell for p in self.pads.values())
        for goal in relevant:
            dist = self.distances(goal)
            if any(c not in dist for c in relevant):
                raise ValueError(f"unreachable parking or service location: {goal}")
