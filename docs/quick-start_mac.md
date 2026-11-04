Install Python 3.12, download and extract the GitHub project, then open Terminal in the folder containing pyproject.toml and run:
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python -m pip install --no-build-isolation --no-deps -e .
.venv/bin/python -m port_agv demo --fleet 30 --planner dynamic
For future launches, run only the last command from that folder.

The controls remain the same: Space pauses, P switches planners, F changes fleet size, and Esc closes the window.