# ValSim

ValSim is a local tournament explorer and Monte Carlo simulator for map-based esports. The bundled **Relay Invitational** is a fictional two-group tournament you can open immediately after setup.

**Unofficial project.** ValSim is independent of Riot Games and esports organizers. The [disclaimer](DISCLAIMER.md) explains the status of the demo, forecasts, and data.

## Run locally

Use Python 3.12 or 3.13 and Node.js 22 or later.

On Windows, open PowerShell in the repository and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\Start-ValSim.ps1
```

On macOS or Linux, run:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
npm --prefix frontend ci
npm --prefix frontend run build
python -m uvicorn backend.valsim.api:app --host 127.0.0.1 --port 8765
```

Open [ValSim](http://127.0.0.1:8765). The API reference is at [API docs](http://127.0.0.1:8765/api-docs).

## What you can do

- Switch groups and browse standings, completed results, scheduled fixtures, and roster profiles.
- Simulate a match with a weighted or manual veto. Run the remaining group or an imported knockout bracket with a reproducible seed.
- Compare a forced result with a baseline. Inspect placement probabilities, unresolved ties, sampling uncertainty, and model sensitivity.
- View overall, form, and seven role-aware player attributes. Each grade exposes its evidence, and unsupported grades are shown as unavailable.
- Export simulation runs as JSON with their configuration, input hash, and model version.

## Bring your own data

Import a permitted event snapshot from **Data sources** using JSON or the JSON envelope with CSV tables. The bundled files in `data/manual_snapshots` show the schema. Give corrections a fresh snapshot ID and keep the same event ID. Set `aggregate_includes_completed` to true when the team's totals already include all completed fixtures in the file. Use a UTC offset when supplying fixture times.

Player datasets can be placed in `data/player_snapshots`. Match their event ID to the event snapshot. The bundled demos show roster entries, the `agent_roles` mapping, historical appearances, and optional `skill_telemetry` for the seven attributes. Restart ValSim after adding player datasets. Event snapshots and simulation runs are stored in SQLite. ValSim reads player datasets from JSON. `VALSIM_DATABASE` overrides the database path.

## Test

```text
python -m pip install -r requirements-dev.txt
python -m pytest -q
npm --prefix frontend ci
npm --prefix frontend run build
```

MIT licensed. See [LICENSE](LICENSE) and the [disclaimer](DISCLAIMER.md).
