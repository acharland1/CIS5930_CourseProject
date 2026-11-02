# Launch the visual demo on Windows

The demo opens a local window showing AGVs moving containers through the port.
You can compare planners and inspect why vehicles are waiting.

1. Install **Python 3.12** if it is not already installed.
2. On the repository page, select **Code → Download ZIP**, then extract it.
3. Open PowerShell in the extracted folder containing `pyproject.toml`.
4. Run these commands once to set up the project and launch 30 AGVs:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps -e .
.\.venv\Scripts\python.exe -m port_agv demo --fleet 30 --planner dynamic
```

For later launches, open PowerShell in the same folder and run only the last
command. Keep the terminal open while using the demo.

**Controls:** Space pauses/resumes, **N** advances one step, **P** switches
planners, **F** changes fleet size, **R** restarts, and **Esc** closes the window.
Click an AGV to see its route, task, and blocker. Switching planners or fleet
size resets the run so you can compare the same starting scenario.
