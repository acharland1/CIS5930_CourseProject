"""Headless runs, evidence bundles, paired experiments, and replay."""
from __future__ import annotations

import csv
import hashlib
import json
import platform
import statistics
import sys
import time
from dataclasses import asdict
from importlib.metadata import version
from itertools import product
from pathlib import Path

from .env import PortEnv
from .model import CATEGORIES, Config
from .planners import PLANNERS, make_planner


def percentile(values, p):
    if not values:
        return 0.0
    data = sorted(values)
    return float(data[round((len(data)-1) * p)])


def run_id(config, planner):
    return (f"{config.layout}_{config.capacity}_f{config.fleet}_"
            f"s{config.seed}_{planner}")


class Recorder:
    def __init__(self, directory: Path, env: PortEnv, planner: str, vehicle_log=True):
        self.path = directory
        # Exclusive creation prevents accidental overwrite of experimental evidence.
        self.path.mkdir(parents=True, exist_ok=False)
        self.events = (directory / "events.jsonl").open("w", encoding="utf-8")
        self.actions = (directory / "actions.jsonl").open("w", encoding="utf-8")
        self.vehicle_file = None
        self.writer = None
        if vehicle_log:
            self.vehicle_file = (directory / "vehicles.csv").open("w", newline="", encoding="utf-8")
            fields = ["tick", "agent", "x", "y", "task", "phase", "loaded", "activity",
                      "reason", "blocker", "secondary_blocker"]
            self.writer = csv.DictWriter(self.vehicle_file, fieldnames=fields)
            self.writer.writeheader()
        manifest = [asdict(t.spec) for t in env.tasks.values()]
        manifest_hash = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
        self.metadata = {"schema_version": 1, "config": env.config.to_dict(),
            "seed": env.seed, "planner": planner, "manifest": manifest,
            "manifest_hash": manifest_hash, "yard_version": env.network.version,
            "starts": [list(c.cell) for c in env.vehicles.values()],
            "timing_mode": "virtual_time_paused_during_planning",
            "python": sys.version, "platform": platform.platform(),
            "packages": {p: version(p) for p in ("port-agv-demo", "pettingzoo", "gymnasium", "numpy")},
            "free_flow_lengths": {f"{q}-{d}": len(env.network.route(
                env.network.pads[q].cell, env.network.pads[d].cell))-1
                for q in ("Q1", "Q2") for d in ("D1", "D2")},
            "vehicle_log": vehicle_log}
        (directory / "manifest.json").write_text(json.dumps(self.metadata, indent=2), encoding="utf-8")
        self.write_events(env.last_events)

    def write_events(self, events):
        for event in events:
            self.events.write(json.dumps(event, sort_keys=True) + "\n")

    def tick(self, decision, env, elapsed):
        action = {"tick": decision.tick, "actions": dict(decision.actions),
                  "priority": list(decision.priority), "waits": dict(decision.waits),
                  "blockers": dict(decision.blockers),
                  "diagnostics": dict(decision.diagnostics), "planner_seconds": elapsed}
        self.actions.write(json.dumps(action, sort_keys=True) + "\n")
        self.write_events(env.last_events)
        if self.writer:
            self.writer.writerows(env.last_rows)

    def close(self):
        self.events.close()
        self.actions.close()
        if self.vehicle_file:
            self.vehicle_file.close()


def summarize(env, planner, times, wall_seconds, failures=0):
    task_times = [t.completed - t.spec.release for t in env.tasks.values()
                  if t.completed is not None]
    totals = {category: sum(c[category] for c in env.counts.values()) for category in CATEGORIES}
    return {"planner": planner, **env.config.to_dict(), "seed": env.seed,
        "ticks": env.tick, "completed_tasks": env.completed,
        "unfinished_tasks": len(env.tasks) - env.completed,
        "success": env.success, "timeout": env.tick >= env.config.max_ticks and not env.success,
        "failure": env.failure, "collisions": env.collisions,
        "mean_completion_seconds": statistics.mean(task_times) if task_times else None,
        "traffic_wait_seconds": totals["traffic_wait"],
        "service_queue_seconds": totals["service_queue"],
        "mean_wait_per_vehicle_seconds": (totals["traffic_wait"] + totals["service_queue"])/env.config.fleet,
        "active_service_seconds": totals["service"], "idle_seconds": totals["idle"],
        "distance_cells": totals["moving"], "deadlock_episodes": env.deadlock_episodes,
        "deadlocked_vehicles": len(env.deadlocked_agents), "rejected_moves": env.rejected_moves,
        "search_failures": failures,
        "planner_mean_ms": 1000 * statistics.mean(times) if times else 0.0,
        "planner_p95_ms": 1000 * percentile(times, .95),
        "planner_total_seconds": sum(times), "wall_seconds": wall_seconds,
        "trace_hash": env.trace_hash,
        "activity_vehicle_ticks": sum(totals.values())}


def run(config, planner_name="dynamic", output=None, vehicle_log=True):
    env = PortEnv(config)
    env.reset(seed=config.seed)
    env.planner_name = planner_name
    planner = make_planner(planner_name, config.horizon)
    recorder = Recorder(Path(output), env, planner_name, vehicle_log) if output else None
    times, failures = [], 0
    start = time.perf_counter()
    try:
        while env.agents:
            snapshot = env.snapshot()
            begin = time.perf_counter()
            decision = planner.plan(snapshot)
            elapsed = time.perf_counter() - begin
            times.append(elapsed)
            failures += int(decision.diagnostics.get("search_failures", 0))
            env.submit(decision)
            env.step(decision.actions)
            if recorder:
                recorder.tick(decision, env, elapsed)
        summary = summarize(env, planner_name, times, time.perf_counter()-start, failures)
        if recorder:
            (recorder.path / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
            rows = [{**asdict(t.spec), "assigned": t.assigned, "status": t.status,
                     "completed": t.completed,
                     "completion_seconds": t.completed-t.spec.release if t.completed is not None else None}
                    for t in env.tasks.values()]
            with (recorder.path / "tasks.csv").open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["id", "release", "pickup", "dropoff", "assigned",
                    "status", "completed", "completion_seconds"])
                writer.writeheader()
                writer.writerows(rows)
        return summary
    finally:
        if recorder:
            recorder.close()
        env.close()


def replay(directory):
    from .model import Decision
    directory = Path(directory)
    metadata = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    expected = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    env = PortEnv(Config(**metadata["config"]))
    try:
        env.reset(seed=metadata["seed"], options={"manifest": metadata["manifest"],
                                                "starts": metadata["starts"]})
        with (directory / "actions.jsonl").open(encoding="utf-8") as f:
            for line in f:
                entry = json.loads(line)
                if not env.agents or entry["tick"] != env.tick:
                    raise ValueError("replay actions do not match the simulation clock")
                decision = Decision(entry["tick"], entry["actions"], tuple(entry["priority"]),
                                    entry["diagnostics"], entry["waits"], entry.get("blockers", {}))
                env.submit(decision)
                env.step(decision.actions)
        if not env.done or env.trace_hash != expected["trace_hash"]:
            raise ValueError("replay diverged from the authoritative state trace")
        return {"matched": True, "ticks": env.tick, "trace_hash": env.trace_hash}
    finally:
        env.close()


def compare(output, fleets=(20, 25, 30), layouts=("open", "bottleneck"),
            capacities=("ample", "constrained"), seeds=(0,), tasks=100,
            max_ticks=10_000, horizon=10, vehicle_log=True):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    combos = list(product(fleets, layouts, capacities, seeds, PLANNERS))
    with (output / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        writer = None
        for index, (fleet, layout, capacity, seed, planner) in enumerate(combos, 1):
            config = Config(fleet=fleet, layout=layout, capacity=capacity,
                            seed=seed, tasks=tasks, max_ticks=max_ticks, horizon=horizon)
            print(f"[{index}/{len(combos)}] {run_id(config, planner)}", flush=True)
            row = run(config, planner, output / run_id(config, planner), vehicle_log)
            rows.append(row)
            if writer is None:
                writer = csv.DictWriter(f, fieldnames=list(row))
                writer.writeheader()
            writer.writerow(row)
            f.flush()
    return rows
