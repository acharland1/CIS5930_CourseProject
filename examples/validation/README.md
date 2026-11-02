# Recorded demo validation

These are actual generated outputs, not illustrative data.

- `open-workload-summary.csv`: 18 runs with 100 tasks, 20/25/30 vehicles,
  open traffic, ample/constrained service, all planners, and seed 0.
- `bottleneck-smoke-summary.csv`: 36 integration runs spanning both layouts,
  both service levels, all fleets and planners, seed 0, and 20 tasks. The file
  includes successful open runs and bottleneck timeouts.
- `open-workload-comparison.png`: charts from the 18-run workload summary.
  Hatched waiting bars represent service queues; solid waiting bars represent traffic.
- `viewer.png`: a 30-vehicle, 100-task dynamic-priority run at tick 180, seed 7.

See `../../docs/validation.md` for test results, reproduction commands, and limits.
The full per-tick/action evidence bundles are generated locally under `runs/`.
The one-seed comparisons here do not establish a statistically general winner.
