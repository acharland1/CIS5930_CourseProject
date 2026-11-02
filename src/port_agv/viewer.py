"""2D inspection UI. Rendering never advances authoritative simulation time."""
from __future__ import annotations

import os
import time

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from dataclasses import replace
import numpy as np

CELL, LEFT, TOP = 22, 28, 110
WIDTH, HEIGHT = 1260, 840
INK = (27, 43, 57)
COLORS = {"empty": (36, 116, 190), "loaded": (231, 169, 48),
          "waiting": (204, 76, 68), "service": (131, 95, 173), "idle": (73, 142, 114)}


class Renderer:
    def __init__(self, mode="rgb_array"):
        import pygame
        self.pg = pygame
        pygame.font.init()
        self.mode = mode
        if mode == "human":
            pygame.display.init()
            self.surface = pygame.display.set_mode((WIDTH, HEIGHT))
            pygame.display.set_caption("Port AGV Lab | 2D multiagent path planning")
        else:
            self.surface = pygame.Surface((WIDTH, HEIGHT))
        self.font = pygame.font.SysFont("Segoe UI", 17)
        self.small = pygame.font.SysFont("Segoe UI", 13)
        self.tiny = pygame.font.SysFont("Segoe UI", 10, bold=True)
        self.title = pygame.font.SysFont("Segoe UI", 27, bold=True)
        self.selected = None
        self.paused = False
        self.speed = 12

    def text(self, text, x, y, color=INK, small=False):
        font = self.small if small else self.font
        self.surface.blit(font.render(str(text), True, color), (x, y))

    def rect(self, cell):
        return self.pg.Rect(LEFT + CELL*cell[0], TOP + CELL*cell[1], CELL, CELL)

    def render(self, env):
        pg, surface = self.pg, self.surface
        surface.fill((241, 245, 248))
        pg.draw.rect(surface, (19, 42, 60), (0, 0, WIDTH, 83))
        surface.blit(self.title.render("PORT AGV LAB", True, (255, 255, 255)), (28, 15))
        self.text("2D terminal operations / reproducible planning experiments", 30, 53, (183, 208, 223), True)
        self.text(f"{env.config.fleet} AGVs    |    {env.planner_name.upper()}", 815, 26, (225, 238, 246))
        pg.draw.rect(surface, (227, 234, 228), (LEFT, TOP, 40*CELL, 30*CELL), border_radius=5)
        pg.draw.rect(surface, (185, 217, 229), (LEFT, TOP, 40*CELL, 2*CELL))
        self.text("QUAYSIDE / CONTAINER PICKUP", LEFT+10, TOP+7, small=True)

        for y in (7, 8, 13, 14, 21):
            for x in range(6, 35, 3):
                if any((x+d, y) in env.network.adjacency for d in (0, 1)):
                    continue
                color = (121, 151, 168) if (x+y) % 2 else (166, 174, 151)
                r = self.rect((x, y)); r.width = CELL*2-3; r.height = CELL-4
                pg.draw.rect(surface, color, r, border_radius=2)
                pg.draw.line(surface, (238, 241, 240), (r.x+8, r.y+3), (r.x+8, r.bottom-3))
        for cell, dests in env.network.adjacency.items():
            r = self.rect(cell)
            pg.draw.rect(surface, (102, 119, 130), r)
            for dest in dests:
                dx, dy = dest[0]-cell[0], dest[1]-cell[1]
                if (cell[0]+cell[1]) % 3 == 0:
                    cx, cy = r.center
                    pg.draw.line(surface, (191, 207, 214), (cx-dx*4, cy-dy*4), (cx+dx*4, cy+dy*4), 1)
                    pg.draw.line(surface, (191, 207, 214), (cx+dx*4, cy+dy*4),
                                 (cx+dx*1-dy*2, cy+dy*1+dx*2), 1)
        for name, pad in env.network.pads.items():
            for cell in pad.queue:
                pg.draw.rect(surface, (168, 180, 139), self.rect(cell).inflate(-2, -2))
            pg.draw.rect(surface, (231, 199, 119), self.rect(pad.cell).inflate(-1, -1))
            label = self.tiny.render(name, True, INK)
            r = self.rect(pad.cell)
            surface.blit(label, (r.x+2, r.y-13 if pad.kind == "pickup" else r.bottom+1))
        for home in env.network.homes:
            pg.draw.rect(surface, (202, 215, 203), self.rect(home).inflate(-2, -2))
        for cell in env.blocked_cells:
            r = self.rect(cell)
            pg.draw.rect(surface, (161, 50, 47), r)
            pg.draw.line(surface, (255, 255, 255), r.topleft, r.bottomright, 2)
        if self.selected in env.vehicles:
            car = env.vehicles[self.selected]
            path = env.network.route(car.cell, env._goal(car))
            if len(path) > 1:
                pg.draw.lines(surface, (44, 196, 209), False, [self.rect(c).center for c in path], 3)
        for car in env.vehicles.values():
            key = ("service" if car.service_until is not None else
                   "waiting" if car.category in ("traffic_wait", "service_queue") else
                   "idle" if car.phase == "idle" else "loaded" if car.loaded else "empty")
            r = self.rect(car.cell).inflate(-3, -3)
            pg.draw.rect(surface, COLORS[key], r, border_radius=3)
            label = self.tiny.render(car.id[-2:], True, (255, 255, 255))
            surface.blit(label, label.get_rect(center=r.center))
            if car.id == self.selected:
                pg.draw.rect(surface, (11, 203, 217), r.inflate(4, 4), width=2, border_radius=3)

        x = 938
        pg.draw.rect(surface, (255, 255, 255), (922, TOP, 311, 660), border_radius=9)
        self.text("RUN STATUS", x, TOP+14)
        stats = [("Clock", f"{env.tick:,} s"), ("Deliveries", f"{env.completed} / {len(env.tasks)}"),
                 ("Traffic", env.config.layout), ("Service", env.config.capacity),
                 ("Deadlock episodes", str(env.deadlock_episodes)),
                 ("Playback", f"{'PAUSED' if self.paused else 'PLAYING'} / {self.speed} ticks/s")]
        for i, (key, value) in enumerate(stats):
            y = TOP+49+i*27
            self.text(key, x, y, (102, 118, 130), True)
            self.text(value, x+137, y, small=True)
        y = TOP+228
        self.text("WAITING / VEHICLE-SECONDS", x, y, small=True)
        for offset, (cat, label) in enumerate((("traffic_wait", "Traffic"), ("service_queue", "Service queue"))):
            total = sum(count[cat] for count in env.counts.values())
            self.text(f"{label}: {total:,}", x, y+26+offset*25)
        self.text("SELECTED VEHICLE", x, TOP+332, small=True)
        if self.selected in env.vehicles:
            car = env.vehicles[self.selected]
            lines = [car.id, f"Task: {car.task if car.task is not None else 'none'} / {car.phase}",
                     f"Activity: {car.category}", f"Wait: {car.reason or '-'}",
                     f"Blocker: {car.blocker or '-'}", f"Capacity: {car.secondary_blocker or '-'}"]
            for i, line in enumerate(lines):
                self.text(line, x, TOP+358+i*23, small=True)
        else:
            self.text("Click an AGV to inspect its blocker.", x, TOP+363, small=True)
        for i, (key, color) in enumerate(COLORS.items()):
            cx = x + (i % 2)*140; cy = TOP+530+(i//2)*25
            pg.draw.circle(surface, color, (cx+6, cy+8), 5)
            self.text(key.capitalize(), cx+18, cy, small=True)
        if env.done:
            label = "COMPLETE" if env.success else "STOPPED: " + (env.failure or "time limit")
            self.text(label, x, TOP+625, (40, 126, 100) if env.success else COLORS["waiting"], True)
        self.text("SPACE pause   N step   +/- speed   R reset   P planner   F fleet   L layout   C capacity   ESC exit",
                  LEFT, 790, small=True)
        self.text("One cell / second. Synthetic teaching model. 20-30 vehicle scope.", LEFT, 814, (108, 123, 133), True)
        if self.mode == "human":
            pg.display.flip()
            return None
        return np.transpose(pg.surfarray.array3d(surface), (1, 0, 2)).copy()

    def close(self):
        if self.mode == "human":
            self.pg.display.quit()


def demo(config, planner_name="dynamic"):
    import pygame
    from .env import PortEnv
    from .planners import PLANNERS, make_planner
    renderer = Renderer("human")
    clock = pygame.time.Clock()
    config_now, name_now = config, planner_name

    def reset():
        env = PortEnv(config_now)
        env.reset(seed=config_now.seed)
        env.planner_name = name_now
        return env, make_planner(name_now, config_now.horizon)

    env, planner = reset()
    running, step_once, elapsed = True, False, 0.0
    try:
        while running:
            dt = clock.tick(60)/1000
            changed = False
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    x, y = event.pos
                    cell = ((x-LEFT)//CELL, (y-TOP)//CELL)
                    renderer.selected = next((c.id for c in env.vehicles.values() if c.cell == cell), None)
                elif event.type == pygame.KEYDOWN:
                    key = event.key
                    if key == pygame.K_ESCAPE:
                        running = False
                    elif key == pygame.K_SPACE:
                        renderer.paused = not renderer.paused
                    elif key == pygame.K_n:
                        renderer.paused = True
                        step_once = True
                    elif key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                        renderer.speed = min(120, renderer.speed*2)
                    elif key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                        renderer.speed = max(1, renderer.speed//2)
                    elif key == pygame.K_r:
                        changed = True
                    elif key == pygame.K_p:
                        name_now = PLANNERS[(PLANNERS.index(name_now)+1) % len(PLANNERS)]
                        changed = True
                    elif key == pygame.K_f:
                        fleets = (20, 25, 30)
                        fleet = fleets[(fleets.index(config_now.fleet)+1) % 3] if config_now.fleet in fleets else 20
                        config_now = replace(config_now, fleet=fleet); changed = True
                    elif key == pygame.K_l:
                        config_now = replace(config_now, layout="bottleneck" if config_now.layout == "open" else "open")
                        changed = True
                    elif key == pygame.K_c:
                        config_now = replace(config_now, capacity="constrained" if config_now.capacity == "ample" else "ample")
                        changed = True
            if changed:
                env.close()
                env, planner = reset()
                elapsed = 0
                renderer.selected = None
            if not renderer.paused:
                elapsed += dt
            else:
                elapsed = 0
            steps = min(8, int(elapsed*renderer.speed)) if not renderer.paused else int(step_once)
            for _ in range(steps):
                if not env.agents:
                    break
                decision = planner.plan(env.snapshot())
                env.submit(decision)
                env.step(decision.actions)
            if steps and not renderer.paused:
                elapsed = max(0, elapsed-steps/renderer.speed)
            step_once = False
            renderer.render(env)
    finally:
        env.close()
        renderer.close()
