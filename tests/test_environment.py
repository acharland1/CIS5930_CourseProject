from dataclasses import replace

import numpy as np
import pytest

from port_agv.env import PortEnv, make_manifest, resolve_moves
from port_agv.layout import Network
from port_agv.model import Config, Decision
from port_agv.planners import make_planner


def test_shared_destination_has_one_winner_and_does_not_enter_loser_cell():
    before = {"a": (0, 0), "b": (2, 0), "c": (3, 0)}
    after, reasons = resolve_moves(before, {"a": (1, 0), "b": (1, 0), "c": (2, 0)}, ("a", "b", "c"))
    assert after == {"a": (1, 0), "b": (2, 0), "c": (3, 0)}
    assert reasons["b"] == ("target_conflict", "a")
    assert reasons["c"] == ("occupied_cell", "b")


def test_head_on_swap_blocks_both_and_their_followers():
    before = {"a": (0, 0), "b": (1, 0), "c": (2, 0)}
    after, reasons = resolve_moves(before, {"a": (1, 0), "b": (0, 0), "c": (1, 0)}, ("a", "b", "c"))
    assert after == before
    assert reasons["a"][0] == reasons["b"][0] == "head_on_swap"


def test_safe_simultaneous_following_does_not_depend_on_dictionary_order():
    before = {"a": (0, 0), "b": (1, 0), "c": (2, 0)}
    targets = {"a": (1, 0), "b": (2, 0), "c": (3, 0)}
    after, _ = resolve_moves(dict(reversed(list(before.items()))), targets, ("a", "b", "c"))
    assert after == targets


@pytest.mark.parametrize("layout", ["open", "bottleneck"])
def test_all_pads_and_thirty_private_parking_bays_are_reachable(layout):
    yard = Network(layout)
    yard.validate()
    assert len(yard.homes) == 30
    assert all(len(yard.adjacency[home]) == 1 for home in yard.homes)
    assert len(set(yard.homes)) == 30


def test_paired_demand_is_independent_of_fleet_layout_and_capacity():
    a = Config(fleet=20, layout="open", capacity="ample")
    b = replace(a, fleet=30, layout="bottleneck", capacity="constrained")
    assert make_manifest(a, 42) == make_manifest(b, 42)
    assert make_manifest(a, 42) != make_manifest(a, 43)


def test_illegal_action_is_logged_and_a_parked_vehicle_stays_present():
    env = PortEnv(Config(fleet=2, tasks=0, max_ticks=3))
    env.reset(seed=0)
    before = {n: c.cell for n, c in env.vehicles.items()}
    _, rewards, terms, truncs, infos = env.step({"agv_000": 99})
    assert {n: c.cell for n, c in env.vehicles.items()} == before
    assert len(env.vehicles) == 2
    assert rewards == {"agv_000": 0.0, "agv_001": 0.0}
    assert all(terms.values()) and not any(truncs.values())
    assert infos["agv_000"]["reason"] == "invalid_action"
    assert env.rejected_moves == 2


def test_stale_planner_response_is_rejected():
    env = PortEnv(Config(fleet=1, tasks=1))
    env.reset(seed=1)
    with pytest.raises(ValueError, match="stale"):
        env.submit(Decision(-1, {"agv_000": 0}, ("agv_000",), {}, {}))


def test_time_limit_is_truncation_not_completion():
    env = PortEnv(Config(fleet=1, tasks=1, max_ticks=1))
    env.reset(seed=1)
    _, _, terminations, truncations, _ = env.step({"agv_000": 0})
    assert not any(terminations.values())
    assert all(truncations.values()) and not env.success
    assert env.completed == 0


@pytest.mark.parametrize("method", ["dynamic", "fixed", "reservations"])
def test_closed_goal_reports_no_teleport_or_unsafe_motion(method):
    env = PortEnv(Config(fleet=1, tasks=1, max_ticks=30))
    env.reset(seed=1)
    goal = env._goal(env.vehicles["agv_000"])
    env.blocked_cells = frozenset([goal])
    planner = make_planner(method)
    for _ in range(30):
        decision = planner.plan(env.snapshot())
        env.submit(decision)
        env.step(decision.actions)
        assert env.vehicles["agv_000"].cell != goal
        env.check_invariants()
    assert env.collisions == 0 and env.completed == 0


def test_overlap_is_independently_detected():
    env = PortEnv(Config(fleet=2, tasks=0))
    env.reset(seed=2)
    env.vehicles["agv_001"].cell = env.vehicles["agv_000"].cell
    with pytest.raises(AssertionError, match="overlap"):
        env.check_invariants()


def test_busy_service_does_not_look_like_a_deadlock():
    env = PortEnv(Config(fleet=2, tasks=1, deadlock_ticks=2))
    env.reset(seed=0)
    a, b = env.vehicles.values()
    a.category = b.category = "traffic_wait"
    a.no_progress = b.no_progress = 50
    a.blocker, b.blocker = b.id, a.id
    b.service_until = 100
    b.category = "service"
    env._detect_deadlocks()
    assert env.deadlock_episodes == 0


@pytest.mark.integration
@pytest.mark.parametrize("method", ["dynamic", "fixed", "reservations"])
def test_complete_transport_jobs_and_container_conservation(method):
    env = PortEnv(Config(fleet=1, tasks=3, max_ticks=2000))
    env.reset(seed=7)
    planner = make_planner(method)
    while env.agents:
        decision = planner.plan(env.snapshot())
        env.submit(decision)
        env.step(decision.actions)
        env.check_invariants()
    assert env.success and env.completed == 3
    assert all(t.custody == "destination" for t in env.tasks.values())
    assert env.collisions == 0
    assert sum(sum(c.values()) for c in env.counts.values()) == env.tick


@pytest.mark.parametrize("fleet", [20, 25, 30])
def test_requested_fleets_have_valid_observations_and_unique_starts(fleet):
    env = PortEnv(Config(fleet=fleet))
    observations, _ = env.reset(seed=1)
    assert len(observations) == fleet
    assert len({c.cell for c in env.vehicles.values()}) == fleet
    assert all(env.observation_space(n).contains(o) for n, o in observations.items())
    assert env.state().shape == (fleet*11,)


@pytest.mark.parametrize("kwargs", [{"fleet": 31}, {"fleet": 20.5}, {"seed": -1}, {"tasks": -1}, {"horizon": 0}])
def test_invalid_configuration_is_rejected(kwargs):
    with pytest.raises(ValueError):
        Config(**kwargs)
