# Validation recorded on 2 November 2026

Validation used Python 3.12.14 on Windows with the exact versions in
`requirements-lock.txt`. These are software/demo checks on synthetic scenarios,
not terminal calibration or evidence of real-world safety.

## Automated checks

`python -m pytest -q`: **35 passed**. Two third-party PettingZoo deprecation
warnings remain; no project test failed. `python -m pip check` reported no broken
requirements. The package installed in an isolated virtual environment and its
source/tests compiled successfully.

Coverage includes the PettingZoo Parallel API and seed checks, conservation,
shared destinations, opposing swaps, follower-chain rejection, parked agents,
closures, stale responses, termination/truncation, reservation prefix safety,
same-seed traces, exact replay, tamper detection, paired statistics, charts,
and the 20/25/30-vehicle starts.

The actual Pygame event loop was exercised using an SDL offscreen display:
pause, single step, click selection, reset, planner/fleet/layout/capacity changes,
and exit. RGB output was inspected visually. This did not include manually
driving a visible native window on another machine.

## Representative experiments

| Batch | Conditions | Recorded result |
| --- | --- | --- |
| Integration matrix | 20/25/30 AGVs; open/bottleneck; ample/constrained; all three planners; seed 0; 20 tasks; 2,000-tick cap | 36 runs: all 18 open runs completed; all 18 bottleneck runs reached the cap and recorded confirmed deadlock |
| Active-fleet workload | 20/25/30 AGVs; open layout; ample/constrained; all three planners; seed 0; 100 tasks; 3,000-tick cap | 18 of 18 runs completed all 100 deliveries and parked; all 30 AGVs received work in every 30-vehicle run |

Across the **54 runs**, there were **zero collisions and zero inventory/other
invariant failures**. Overall, 36 runs completed and 18 timed out. The integration
batch has only 20 tasks, so it cannot demonstrate 25 or 30 simultaneously busy
vehicles; the separate 100-task batch verifies participation of the full fleets.

The 100-task open runs finished in 493-1,330 simulated ticks. For the 30-vehicle
dynamic baseline, ample service finished in 493 ticks versus 1,264 ticks with
constrained service. Service-queue waiting increased from 1,313 to 17,923 total
vehicle-seconds. These single-seed observations illustrate capacity effects;
they do not establish a general ranking between policies.

The shared two-way bottleneck exposes a real limitation of these simple
coordinators: dynamic/fixed shortest paths can face an opposing-path deadlock,
while conservative prioritized reservations may complete more jobs before also
stalling. Those results are retained rather than repaired invisibly. A yielding
or coordinated retreat policy would be a separately evaluated extension.

Exact recorded-action replay matched the state hashes for dynamic and reservation
runs, including a timed-out bottleneck run and the 30-vehicle, 100-task reservation
run. Planning wall times are excluded from the deterministic trace.

## Reproduce

From the installed project environment:

```powershell
python -m pytest -q
python -m port_agv compare --fleets 20 25 30 --seeds 0 --tasks 20 --max-ticks 2000 --out runs/validation-matrix
python -m port_agv compare --fleets 20 25 30 --layouts open --capacities ample constrained --seeds 0 --tasks 100 --max-ticks 3000 --out runs/validation-workload
python -m port_agv replay runs/validation-workload/open_ample_f30_s0_reservations
python -m port_agv snapshot --fleet 30 --planner dynamic --ticks 180 --out runs/preview.png
```

Use a fresh output directory when rerunning. Raw evidence is generated under
`runs/`, which is ignored by Git. Compact recorded summaries, a viewer frame,
and the open-workload chart are bundled in `examples/validation/`.

The full 360-run, ten-seed study has **not** been run. Hardware timing and
single-seed plots should not be treated as publication-quality statistical
comparisons. No upload or GitHub modification was part of this validation step.
