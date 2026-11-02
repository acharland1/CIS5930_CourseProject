import json

import pytest
from pettingzoo.test import parallel_api_test, parallel_seed_test

from port_agv import Config, PortEnv
from port_agv.planners import make_planner
from port_agv.report import paired_summary
from port_agv.runner import replay, run


@pytest.mark.integration
def test_pettingzoo_parallel_contract():
    env = PortEnv(Config(fleet=20, tasks=4, max_ticks=75))
    parallel_api_test(env, num_cycles=100)


@pytest.mark.integration
def test_pettingzoo_parallel_seed_contract():
    parallel_seed_test(lambda: PortEnv(Config(fleet=20, tasks=4, max_ticks=75)), num_cycles=60)


@pytest.mark.integration
def test_evidence_bundle_replays_exactly_and_does_not_overwrite(tmp_path):
    directory = tmp_path / "one-run"
    config = Config(fleet=1, tasks=2, max_ticks=1200)
    summary = run(config, "dynamic", directory)
    assert summary["success"]
    assert replay(directory)["trace_hash"] == summary["trace_hash"]
    assert summary["activity_vehicle_ticks"] == summary["fleet"] * summary["ticks"]
    assert (directory / "vehicles.csv").exists()
    with pytest.raises(FileExistsError):
        run(config, "dynamic", directory)


def test_tampered_action_trace_fails_replay(tmp_path):
    directory = tmp_path / "tamper"
    run(Config(fleet=1, tasks=1, max_ticks=50), "fixed", directory)
    path = directory / "actions.jsonl"
    entries = [json.loads(line) for line in path.read_text().splitlines()]
    entries[0]["tick"] = 123
    path.write_text("\n".join(json.dumps(x) for x in entries)+"\n")
    with pytest.raises(ValueError, match="clock"):
        replay(directory)


def test_planner_state_trace_is_reproducible():
    config = Config(fleet=20, tasks=5, max_ticks=120)
    a, b = run(config), run(config)
    assert a["trace_hash"] == b["trace_hash"]
    assert a["completed_tasks"] == b["completed_tasks"]


def test_all_reservation_prefixes_obey_authoritative_occupancy():
    env = PortEnv(Config(fleet=30, tasks=10, max_ticks=100))
    env.reset(seed=0)
    planner = make_planner("reservations")
    while env.agents:
        decision = planner.plan(env.snapshot())
        env.submit(decision)
        env.step(decision.actions)
        assert env.collisions == 0 and env.failure is None
        assert not any(e["kind"] == "rejected" for e in env.last_events)


def test_rendering_returns_a_frame_without_changing_the_trace(monkeypatch):
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    env = PortEnv(Config(fleet=20), render_mode="rgb_array")
    env.reset(seed=1)
    before = env.trace_hash
    try:
        frame = env.render()
        assert frame.shape == (840, 1260, 3)
        assert env.trace_hash == before and env.tick == 0
    finally:
        env.close()


def test_paired_statistics_do_not_mix_conditions_or_invent_single_seed_intervals():
    rows = []
    for method, count in (("dynamic", 5), ("fixed", 3)):
        rows.append({"fleet": 20, "layout": "open", "capacity": "ample", "seed": 1,
                     "planner": method, "completed_tasks": count,
                     "mean_completion_seconds": None, "mean_wait_per_vehicle_seconds": 2,
                     "traffic_wait_seconds": 10, "service_queue_seconds": 5, "planner_p95_ms": 1})
    result = paired_summary(rows)
    completed = next(r for r in result if r["metric"] == "completed_tasks")
    assert completed["mean_delta_vs_dynamic"] == -2
    assert completed["paired_seeds"] == 1 and completed["bootstrap_low"] is None


def test_viewer_keyboard_controls_with_an_offscreen_display(monkeypatch):
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    import pygame
    from port_agv.viewer import CELL, LEFT, TOP, Renderer, demo
    probe = PortEnv(Config(fleet=20, tasks=2, max_ticks=20))
    probe.reset(seed=probe.config.seed)
    parked = probe.vehicles["agv_001"].cell
    observed = []
    original = Renderer.render

    def record(self, env):
        observed.append((env.tick, env.config.fleet, env.config.layout,
                         env.config.capacity, env.planner_name, self.paused, self.selected))
        return original(self, env)

    frames = iter([
        [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE),
         pygame.event.Event(pygame.KEYDOWN, key=pygame.K_n),
         pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(LEFT+CELL*parked[0]+CELL//2,
                                                        TOP+CELL*parked[1]+CELL//2))],
        [pygame.event.Event(pygame.KEYDOWN, key=k) for k in
         (pygame.K_p, pygame.K_f, pygame.K_l, pygame.K_c, pygame.K_r)],
        [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)],
    ])
    monkeypatch.setattr(pygame.event, "get", lambda: next(frames))
    monkeypatch.setattr(Renderer, "render", record)
    demo(Config(fleet=20, tasks=2, max_ticks=20))
    assert observed[0] == (1, 20, "open", "ample", "dynamic", True, "agv_001")
    assert observed[1] == (0, 25, "bottleneck", "constrained", "fixed", True, None)


def test_report_generates_charts_and_keeps_cache_with_results(tmp_path, monkeypatch):
    import csv
    import os
    from port_agv.report import generate_report
    monkeypatch.delenv("MPLCONFIGDIR", raising=False)
    rows = []
    for planner in ("dynamic", "fixed", "reservations"):
        for seed in (0, 1):
            rows.append({"fleet": 20, "layout": "open", "capacity": "ample", "seed": seed,
                "planner": planner, "completed_tasks": 3, "mean_completion_seconds": 50,
                "mean_wait_per_vehicle_seconds": 4, "traffic_wait_seconds": 60,
                "service_queue_seconds": 20, "planner_p95_ms": 1,
                "deadlock_episodes": 0, "timeout": False, "success": True, "failure": ""})
    summary = tmp_path / "summary.csv"
    with summary.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    chart = generate_report(summary)
    assert chart.exists() and chart.stat().st_size > 1000
    assert (tmp_path / "report.md").exists()
    assert (tmp_path / "paired_differences.csv").exists()
    assert os.environ["MPLCONFIGDIR"] == str(tmp_path / ".matplotlib")
