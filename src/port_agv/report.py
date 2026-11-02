"""Plots and paired-seed summaries; no planner rankings are assumed."""
from __future__ import annotations

import csv
import os
from collections import defaultdict
from pathlib import Path

import numpy as np

from .planners import PLANNERS

COLORS = {"dynamic": "#2878ad", "fixed": "#da9d38", "reservations": "#4c947e"}


def numeric(value):
    return None if value in (None, "", "None", "null") else float(value)


def condition(row):
    return int(row["fleet"]), row["layout"], row["capacity"]


def paired_summary(rows):
    groups = defaultdict(dict)
    metrics = ("completed_tasks", "mean_completion_seconds", "mean_wait_per_vehicle_seconds",
               "traffic_wait_seconds", "service_queue_seconds", "planner_p95_ms")
    for row in rows:
        groups[(*condition(row), int(row["seed"]))][row["planner"]] = row
    pairs = defaultdict(list)
    for key, methods in sorted(groups.items()):
        if "dynamic" not in methods:
            continue
        for method in ("fixed", "reservations"):
            if method not in methods:
                continue
            for metric in metrics:
                a, b = numeric(methods[method][metric]), numeric(methods["dynamic"][metric])
                if a is not None and b is not None:
                    pairs[(*key[:3], method, metric)].append(a-b)
    rng = np.random.default_rng(0)
    result = []
    for key, differences in sorted(pairs.items()):
        values = np.asarray(differences)
        low = high = None
        if len(values) > 1:
            samples = rng.choice(values, size=(2000, len(values)), replace=True).mean(axis=1)
            low, high = map(float, np.quantile(samples, [.025, .975]))
        result.append(dict(zip(("fleet", "layout", "capacity", "planner", "metric"), key)) |
                      {"paired_seeds": len(values), "mean_delta_vs_dynamic": float(values.mean()),
                       "bootstrap_low": low, "bootstrap_high": high})
    return result


def generate_report(summary_file):
    path = Path(summary_file)
    # Keep font-cache writes alongside run artifacts, including sandboxed runs.
    cache = path.resolve().parent / ".matplotlib"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError("summary has no finished runs")
    conditions = sorted({condition(r) for r in rows})
    groups = defaultdict(list)
    for row in rows:
        groups[(condition(row), row["planner"])].append(row)
    fig, axes = plt.subplots(3, 2, figsize=(max(14, len(conditions)*1.9), 12), layout="constrained")
    panels = [("Completed deliveries", "completed_tasks", "Tasks"),
              ("Completion time for completed tasks", "mean_completion_seconds", "Simulated seconds"),
              ("Waiting per vehicle", "mean_wait_per_vehicle_seconds", "Vehicle seconds"),
              ("Runs with confirmed deadlock", "deadlock_episodes", "Fraction of runs"),
              ("Planner p95 per decision", "planner_p95_ms", "Milliseconds"),
              ("Runs reaching the time limit", "timeout", "Fraction of runs")]
    labels = [f"{fleet} AGVs\n{layout}\n{capacity}" for fleet, layout, capacity in conditions]
    for axis, (title, metric, ylabel) in zip(axes.flat, panels):
        for index, method in enumerate(PLANNERS):
            values = []
            for cond in conditions:
                records = groups[(cond, method)]
                if metric == "timeout":
                    data = [float(r[metric] == "True") for r in records]
                elif metric == "deadlock_episodes":
                    data = [float(float(r[metric]) > 0) for r in records]
                else:
                    data = [numeric(r[metric]) for r in records]
                    data = [v for v in data if v is not None]
                values.append(np.mean(data) if data else np.nan)
            positions = np.arange(len(conditions))+(index-1)*.25
            if metric == "mean_wait_per_vehicle_seconds":
                traffic, service = [], []
                for cond in conditions:
                    records = groups[(cond, method)]
                    traffic.append(np.mean([float(r["traffic_wait_seconds"])/int(r["fleet"])
                                            for r in records]) if records else np.nan)
                    service.append(np.mean([float(r["service_queue_seconds"])/int(r["fleet"])
                                            for r in records]) if records else np.nan)
                axis.bar(positions, traffic, .23, label=method, color=COLORS[method])
                axis.bar(positions, service, .23, bottom=traffic, color=COLORS[method],
                         alpha=.45, hatch="//", edgecolor=COLORS[method])
                title = "Waiting: traffic solid / service queue hatched"
            else:
                axis.bar(positions, values, .23, label=method, color=COLORS[method])
        axis.set_title(title, loc="left", fontweight="bold")
        axis.set_ylabel(ylabel)
        if metric in ("timeout", "deadlock_episodes"):
            axis.set_ylim(0, 1.05)
        elif metric == "completed_tasks":
            axis.set_ylim(0, max(1, max(float(r["completed_tasks"]) for r in rows))*1.2)
        axis.set_xticks(range(len(conditions)), labels, fontsize=8)
        axis.grid(axis="y", alpha=.18)
        axis.set_axisbelow(True)
        axis.spines[["right", "top"]].set_visible(False)
    axes[0, 0].legend(frameon=False)
    fig.suptitle("Port AGV planner comparison | paired demand and fault-free service scenarios", fontsize=17)
    fig.savefig(path.parent / "comparison.png", dpi=160)
    plt.close(fig)
    paired = paired_summary(rows)
    if paired:
        with (path.parent / "paired_differences.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(paired[0]))
            writer.writeheader(); writer.writerows(paired)
    completed = sum(r["success"] == "True" for r in rows)
    failures = sum(r.get("failure", "") not in ("", "None") for r in rows)
    notes = f"""# Experiment report

{len(rows)} runs recorded; {completed} completed every task and parked every vehicle.
{failures} runs recorded a simulation correctness failure.

See `comparison.png`, `summary.csv`, and `paired_differences.csv`.
Every comparison is grouped by fleet, layout, and service capacity. Raw logs
separate traffic waiting, service-queue waiting, handling, movement, and idle time.
Inspect the corresponding run's `summary.json` for both waiting components.

Paired differences are **candidate minus dynamic-priority baseline** on the
same seed and condition. More completed tasks is better; lower time and waiting
is better. Bootstrap percentile intervals resample paired seed differences
(2,000 draws, analysis seed 0). They are absent for a single seed and may be
unstable with few seeds. Completion-time means omit unfinished tasks and must
always be read together with completion counts and timeouts. Planning timing
is hardware-dependent and excluded from deterministic trace hashes.

The open and bottleneck graphs also differ in free-flow route length. Per-run
manifests record those lengths; a layout effect alone is not proof of poor
coordination. Compare capacity while holding layout fixed and traffic while
holding service fixed. A full service queue can spill into traffic; report that
interaction rather than claiming independent additive causes.

This is a synthetic one-cell AGV model. No real terminal calibration, continuous
vehicle geometry, or field safety claim is implied.
"""
    (path.parent / "report.md").write_text(notes, encoding="utf-8")
    return path.parent / "comparison.png"
