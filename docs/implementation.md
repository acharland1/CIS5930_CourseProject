# Implementation decisions and delivery gates

## Scope and source precedence

The repository's revised/refocused Word plan defines the immediate deliverable:
20-30 AGVs in 2D and three comparable pathing methods. The industrial simulator
plan supplies the broader architecture and evidence principles. Its 3D and
large-fleet ambitions are deferred, not claimed as implemented here.

## Kernel timing

At reset, release and assignment events due at time zero are processed before
observations. Each step applies actions for `[t, t+1)`, records that interval's
activity, advances the integer clock, processes service completions/releases and
assignments due at `t+1`, and starts handover for arrived vehicles. A five-tick
service therefore occupies five complete future intervals. The next observation
contains the fully prepared next decision state. This resolves the revised
plan's event-ordering detail explicitly (industrial plan section 7).

Movement resolution is deterministic: target contention, opposite-edge swaps,
and iterative dependency checks precede one atomic position update. Following
into a cell vacated in the same tick is legal; a follower cannot enter a cell
whose occupant was rejected. This is a grid motion contract, not continuous-time
vehicle collision validation (sections 5 and 8 of the broader plan).

## Planner boundary

Planners receive frozen vehicle snapshots and read-only graph mappings. They
return an action map, a complete priority order, wait explanations, and search
diagnostics. Physical occupancy and task custody remain authoritative in `env.py`.
Timestamped submissions reject stale decisions. All methods share the dispatcher,
cost units, service timing, and rejection rules (sections 6-10).

The reservation implementation is a conservative prioritized baseline, not a
full RHCR/LNS solver. Starting with safe holds preserves a feasible incumbent,
but can prevent an earlier planner from assuming that a lower-priority vehicle
will move away. Safe holding, route failures, actual waiting, and timeouts are
reported; deadlock freedom and optimality are not claimed.

## Evidence and evaluation

Separate random streams generate start-bay ordering and task releases/targets.
The exact manifest is saved rather than regenerated from event order. Every
comparison pairs the same seed, workload, and faults (none in this initial study)
across policies. Holding service constant isolates a traffic-layout comparison;
holding layout constant isolates service capacity. Free-flow path distances are
recorded to expose the remaining layout-distance confound (sections 16-18).

Each vehicle has exactly one activity category per interval. An immediate wait
chain that terminates at a busy service vehicle is classified as service-queue
waiting, including spillback outside marked queue cells. Its service resource is
also recorded as a secondary blocker. Other rejected/policy waits are traffic
waits. This is an operational attribution rule, not proof of independent causes.

Deadlock detection confirms only a persistent wait cycle without an immediate
free escape or a busy service vehicle in the chain. It can miss cases requiring
deeper reachability analysis; the independent timeout metric preserves those
stalls. Planning cost is measured separately and never changes virtual-time
state or trace hashes.

## Milestones

1. Environment: legal 20/25/30 starts, physical queue limits, task custody,
   complete pickup/delivery, and off-lane final parking.
2. Baselines: one interface for dynamic and fixed priorities, with deterministic
   ties and no dispatcher differences.
3. Reservations: valid complete joint prefixes, bounded search, safe fallback,
   and visible failures rather than silent corrections.
4. Integration: API/seed checks, replay evidence, a 30-AGV demo, paired results,
   all five metric groups, charts, and run instructions.

Tests and command-line entry points are supplied for these gates. Measured
verification results belong in a subsequent validation report after running them.
