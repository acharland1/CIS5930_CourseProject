from __future__ import annotations

import argparse
import json
from dataclasses import fields
from pathlib import Path

from .model import Config
from .planners import PLANNERS


def parser():
    root = argparse.ArgumentParser(description="2D port AGV simulation and paired planner experiments")
    sub = root.add_subparsers(dest="command", required=True)
    for command in ("demo", "run", "snapshot"):
        cmd = sub.add_parser(command)
        cmd.add_argument("--config", type=Path)
        cmd.add_argument("--fleet", type=int, choices=(20, 25, 30))
        cmd.add_argument("--layout", choices=("open", "bottleneck"))
        cmd.add_argument("--capacity", choices=("ample", "constrained"))
        for option in ("seed", "tasks", "max-ticks", "horizon"):
            cmd.add_argument("--"+option, type=int)
        cmd.add_argument("--planner", choices=PLANNERS, default="dynamic")
        if command == "run":
            cmd.add_argument("--out", type=Path, required=True)
            cmd.add_argument("--no-vehicle-log", action="store_true")
        if command == "snapshot":
            cmd.add_argument("--ticks", type=int, default=180)
            cmd.add_argument("--out", type=Path, required=True)
    cmd = sub.add_parser("compare")
    cmd.add_argument("--out", type=Path, required=True)
    cmd.add_argument("--fleets", nargs="+", type=int, choices=(20, 25, 30), default=[20, 25, 30])
    cmd.add_argument("--layouts", nargs="+", choices=("open", "bottleneck"), default=["open", "bottleneck"])
    cmd.add_argument("--capacities", nargs="+", choices=("ample", "constrained"), default=["ample", "constrained"])
    cmd.add_argument("--seeds", nargs="+", type=int, default=[0])
    cmd.add_argument("--tasks", type=int, default=100)
    cmd.add_argument("--max-ticks", type=int, default=10_000)
    cmd.add_argument("--horizon", type=int, default=10)
    cmd.add_argument("--no-vehicle-log", action="store_true")
    cmd.add_argument("--skip-report", action="store_true")
    sub.add_parser("report").add_argument("summary", type=Path)
    sub.add_parser("replay").add_argument("directory", type=Path)
    return root


def config_from_args(args):
    values = json.loads(args.config.read_text(encoding="utf-8")) if args.config else {}
    allowed = {f.name for f in fields(Config)}
    if set(values) - allowed:
        raise ValueError(f"unknown configuration fields: {sorted(set(values)-allowed)}")
    for key in allowed:
        value = getattr(args, key, None)
        if value is not None:
            values[key] = value
    return Config(**values)


def main(argv=None):
    root = parser()
    args = root.parse_args(argv)
    try:
        if args.command == "demo":
            from .viewer import demo
            demo(config_from_args(args), args.planner)
        elif args.command == "run":
            from .runner import run
            summary = run(config_from_args(args), args.planner, args.out, not args.no_vehicle_log)
            print(json.dumps(summary, indent=2))
        elif args.command == "compare":
            from .runner import compare
            compare(args.out, args.fleets, args.layouts, args.capacities, args.seeds,
                    args.tasks, args.max_ticks, args.horizon, not args.no_vehicle_log)
            if not args.skip_report:
                from .report import generate_report
                print(generate_report(args.out / "summary.csv"))
        elif args.command == "report":
            from .report import generate_report
            print(generate_report(args.summary))
        elif args.command == "replay":
            from .runner import replay
            print(json.dumps(replay(args.directory), indent=2))
        elif args.command == "snapshot":
            import os
            os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
            import pygame
            from .env import PortEnv
            from .planners import make_planner
            env = PortEnv(config_from_args(args), render_mode="rgb_array")
            try:
                env.reset(seed=env.config.seed)
                env.planner_name = args.planner
                planner = make_planner(args.planner, env.config.horizon)
                if args.ticks < 0:
                    raise ValueError("snapshot ticks cannot be negative")
                for _ in range(args.ticks):
                    if not env.agents:
                        break
                    decision = planner.plan(env.snapshot())
                    env.submit(decision); env.step(decision.actions)
                env.render()
                args.out.parent.mkdir(parents=True, exist_ok=True)
                pygame.image.save(env._viewer.surface, str(args.out))
                print(args.out)
            finally:
                env.close()
    except (ValueError, FileExistsError, FileNotFoundError) as error:
        root.error(str(error))


if __name__ == "__main__":
    main()
