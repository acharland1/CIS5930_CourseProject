"""Configuration and immutable records shared by the kernel and planners."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Mapping, TYPE_CHECKING

if TYPE_CHECKING:
    from .layout import Network

Cell = tuple[int, int]
DELTAS: tuple[Cell, ...] = ((0, 0), (0, -1), (1, 0), (0, 1), (-1, 0))
CATEGORIES = ("moving", "traffic_wait", "service_queue", "service", "idle")


@dataclass(frozen=True)
class Config:
    fleet: int = 20
    layout: str = "open"
    capacity: str = "ample"
    tasks: int = 100
    release_interval: int = 2
    max_ticks: int = 10_000
    horizon: int = 10
    deadlock_ticks: int = 20
    seed: int = 7

    def __post_init__(self):
        for key in ("fleet", "tasks", "release_interval", "max_ticks", "horizon", "deadlock_ticks", "seed"):
            if type(getattr(self, key)) is not int:
                raise ValueError(f"{key} must be an integer")
        if self.seed < 0:
            raise ValueError("seed cannot be negative")
        if not 1 <= self.fleet <= 30:
            raise ValueError("fleet must be between 1 and 30 (study: 20, 25, 30)")
        if self.layout not in ("open", "bottleneck"):
            raise ValueError("layout must be open or bottleneck")
        if self.capacity not in ("ample", "constrained"):
            raise ValueError("capacity must be ample or constrained")
        if self.tasks < 0 or self.release_interval < 0:
            raise ValueError("task count and release interval cannot be negative")
        if min(self.max_ticks, self.horizon, self.deadlock_ticks) < 1:
            raise ValueError("tick limit, horizon and deadlock threshold must be positive")

    @property
    def service_ticks(self) -> int:
        return 5 if self.capacity == "ample" else 20

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class TaskSpec:
    id: int
    release: int
    pickup: str
    dropoff: str


@dataclass
class Task:
    spec: TaskSpec
    status: str = "unreleased"
    assigned: str | None = None
    completed: int | None = None
    custody: str = "source"


@dataclass
class Vehicle:
    id: str
    cell: Cell
    home: Cell
    task: int | None = None
    phase: str = "idle"
    loaded: bool = False
    service_until: int | None = None
    wait_age: int = 0
    category: str = "idle"
    reason: str = ""
    blocker: str | None = None
    secondary_blocker: str | None = None
    no_progress: int = 0
    last_progress: int = 0


@dataclass(frozen=True)
class VehicleView:
    id: str
    cell: Cell
    home: Cell
    goal: Cell
    task: int | None
    phase: str
    loaded: bool
    wait_age: int
    service_remaining: int

    @property
    def busy(self) -> bool:
        return self.service_remaining > 0


@dataclass(frozen=True)
class Snapshot:
    tick: int
    network: Network
    vehicles: tuple[VehicleView, ...]
    occupants: Mapping[Cell, str]
    blocked_cells: frozenset[Cell] = frozenset()


@dataclass(frozen=True)
class Decision:
    tick: int
    actions: Mapping[str, int]
    priority: tuple[str, ...]
    diagnostics: Mapping[str, int | float]
    waits: Mapping[str, str]
    blockers: Mapping[str, str] = field(default_factory=dict)


def action_between(a: Cell, b: Cell) -> int:
    return DELTAS.index((b[0] - a[0], b[1] - a[1]))
