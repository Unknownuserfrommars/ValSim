from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import date
import csv
import json
import logging
import os
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from .imports import snapshot_from_import
from .model import MODEL_VERSION, model_card, observed_standings, validate_scenario
from .players import PlayerDirectory, player_directory
from .schema import Scenario, Snapshot, Status
from .simulation import compare, run
from .storage import RevisionConflict, Store

ROOT = Path(__file__).resolve().parents[2]
SEED_DIR = ROOT / "data" / "manual_snapshots"
DIST = ROOT / "frontend" / "dist"
MAX_IMPORT = 1_000_000
LOGGER = logging.getLogger("valsim")


class CompareRequest(BaseModel):
    conditioned_id: str


def metadata(snapshot: Snapshot | None = None, input_hash: str | None = None, *, model: str = MODEL_VERSION) -> dict:
    return {
        "api_version": 1,
        "model_version": model,
        "schema_version": snapshot.schema_version if snapshot else None,
        "snapshot_id": snapshot.id if snapshot else None,
        "input_hash": input_hash,
        "source": snapshot.source.model_dump(mode="json") if snapshot else None,
    }


def envelope(data: object, snapshot: Snapshot | None = None, input_hash: str | None = None, *, model: str = MODEL_VERSION) -> dict:
    return {"meta": metadata(snapshot, input_hash, model=model), "data": data}


def make_app(path: Path | None = None) -> FastAPI:
    store = Store(path or Path(os.environ.get("VALSIM_DATABASE", ROOT / "data" / "runtime" / "local.sqlite3")))

    def worker(run_id: str) -> None:
        try:
            scenario = store.claim(run_id)
            if scenario is None:
                return
            snapshot, _ = store.snapshot(scenario.snapshot_id)
            result = run(snapshot, scenario, lambda progress: store.progress(run_id, progress))
            store.finish(run_id, result)
        except ValueError as error:
            store.fail(run_id, str(error))
        except Exception:
            LOGGER.exception("Simulation %s failed", run_id)
            store.fail(run_id, "Simulation failed. See the local server log.")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store.migrate()
        for seed_path in sorted(SEED_DIR.glob("*.json")):
            store.save_snapshot(Snapshot.model_validate_json(seed_path.read_bytes()))
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="valsim") as executor:
            app.state.executor = executor
            for run_id in store.recover():
                executor.submit(worker, run_id)
            yield

    app = FastAPI(title="ValSim", version="0.1.0", lifespan=lifespan, docs_url="/api-docs", redoc_url=None,
                  openapi_url="/v1/openapi.json")

    def fetch_event(event_id: str, snapshot_id: str | None = None) -> tuple[Snapshot, str]:
        saved = store.snapshot(snapshot_id) if snapshot_id else store.event(event_id)
        if not saved or saved[0].event_id != event_id:
            raise HTTPException(404, "Event or snapshot not found")
        return saved

    def fetch_run(run_id: str) -> dict:
        job = store.simulation(run_id)
        if not job:
            raise HTTPException(404, "Simulation not found")
        return job

    def run_response(job: dict) -> dict:
        snapshot, input_hash = store.snapshot(job["snapshot_id"])
        return envelope(job, snapshot, input_hash, model=job["model_version"])

    @app.get("/v1/health")
    def health():
        return envelope({"status": "ok"})

    @app.get("/v1/model")
    def model_info():
        return envelope(model_card())

    @app.get("/v1/events")
    def events(
        status: Status | None = None, region: str | None = None, tier: str | None = None,
        q: Annotated[str, Query(max_length=120)] = "",
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
    ):
        matches = []
        search = q.casefold()
        for snapshot, input_hash in store.events():
            if status and status != snapshot.status:
                continue
            if region and region.casefold() != snapshot.region.casefold():
                continue
            if tier and tier.casefold() != (snapshot.tier or "").casefold():
                continue
            if search and search not in f"{snapshot.title} {snapshot.stage} {snapshot.region}".casefold():
                continue
            details = {
                key: getattr(snapshot, key) for key in ("event_id", "title", "stage", "region", "tier", "status")
            }
            details.update({"team_count": len(snapshot.teams), "remaining": sum(f.status == "scheduled" for f in snapshot.fixtures)})
            matches.append(envelope(details, snapshot, input_hash))
        return envelope({"items": matches[offset:offset + limit], "total": len(matches)})

    @app.get("/v1/events/{event_id}")
    def event(event_id: str, snapshot_id: str | None = None):
        snapshot, input_hash = fetch_event(event_id, snapshot_id)
        payload = snapshot.model_dump(mode="json")
        payload["veto_orders"] = {
            str(best_of): [step.model_dump() for step in snapshot.rules.steps_for(best_of)]
            for best_of in sorted({match.best_of for match in snapshot.fixtures if match.status == "scheduled"})
        }
        return envelope(payload, snapshot, input_hash)

    @app.get("/v1/events/{event_id}/standings")
    def standings(event_id: str, snapshot_id: str | None = None):
        snapshot, input_hash = fetch_event(event_id, snapshot_id)
        return envelope(observed_standings(snapshot), snapshot, input_hash)

    def player_response(data: object, snapshot: Snapshot, input_hash: str, directory: PlayerDirectory | None) -> dict:
        response = envelope(data, snapshot, input_hash)
        if directory:
            response["meta"].update(directory.meta())
        return response

    @app.get("/v1/events/{event_id}/players")
    def players(event_id: str, snapshot_id: str | None = None, as_of: date | None = None):
        snapshot, input_hash = fetch_event(event_id, snapshot_id)
        directory = player_directory(snapshot, as_of)
        return player_response(directory.list() if directory else [], snapshot, input_hash, directory)

    @app.get("/v1/events/{event_id}/players/{player_id}")
    def player(event_id: str, player_id: str, snapshot_id: str | None = None, as_of: date | None = None):
        snapshot, input_hash = fetch_event(event_id, snapshot_id)
        directory = player_directory(snapshot, as_of)
        profile = directory.profile(player_id) if directory else None
        if profile is None:
            raise HTTPException(404, "Player profile not found in this event")
        return player_response(profile, snapshot, input_hash, directory)

    @app.get("/v1/players/{player_id}/ratings")
    def player_ratings(player_id: str, snapshot_id: str, as_of: date | None = None):
        saved = store.snapshot(snapshot_id)
        if saved is None:
            raise HTTPException(404, "Snapshot not found")
        snapshot, input_hash = saved
        directory = player_directory(snapshot, as_of)
        profile = directory.profile(player_id) if directory else None
        if profile is None:
            raise HTTPException(404, "Player profile not found in this event")
        return player_response({
            "player_id": player_id, "rating": profile["rating"], "facets": profile["facets"], "model": profile["model"],
        }, snapshot, input_hash, directory)

    @app.get("/v1/events/{event_id}/bracket")
    def bracket(event_id: str, snapshot_id: str | None = None):
        snapshot, input_hash = fetch_event(event_id, snapshot_id)
        if snapshot.bracket is None:
            raise HTTPException(404, "This snapshot has no bracket")
        return envelope(snapshot.bracket.model_dump(mode="json"), snapshot, input_hash)

    @app.get("/v1/events/{event_id}/revisions")
    def revisions(event_id: str):
        snapshot, input_hash = fetch_event(event_id)
        return envelope(store.revisions(event_id), snapshot, input_hash)

    @app.get("/v1/matches/{fixture_id}")
    def match(fixture_id: str, snapshot_id: str):
        saved = store.snapshot(snapshot_id)
        if not saved:
            raise HTTPException(404, "Snapshot not found")
        snapshot, input_hash = saved
        fixture = next((item for item in snapshot.fixtures if item.id == fixture_id), None)
        if fixture is None:
            raise HTTPException(404, "Fixture not found")
        return envelope(fixture.model_dump(mode="json"), snapshot, input_hash)

    @app.post("/v1/imports", status_code=201)
    async def imports(request: Request):
        if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
            raise HTTPException(415, "Supply a JSON snapshot or a JSON envelope containing both CSV tables")
        content = bytearray()
        async for chunk in request.stream():
            if len(content) + len(chunk) > MAX_IMPORT:
                raise HTTPException(413, "Import exceeds the 1 MB limit")
            content.extend(chunk)
        try:
            data = json.loads(content)
            if not isinstance(data, dict):
                raise ValueError("Import must be a JSON object")
            snapshot = snapshot_from_import(data)
            input_hash = store.save_snapshot(snapshot)
        except RevisionConflict as error:
            raise HTTPException(409, str(error)) from error
        except ValidationError as error:
            raise HTTPException(422, error.errors(include_context=False, include_input=False, include_url=False)) from error
        except (ValueError, csv.Error) as error:
            raise HTTPException(422, str(error)) from error
        return envelope({"event_id": snapshot.event_id, "snapshot_id": snapshot.id}, snapshot, input_hash)

    @app.post("/v1/simulations", status_code=202)
    def create_simulation(scenario: Scenario, request: Request, response: Response):
        saved = store.snapshot(scenario.snapshot_id)
        if not saved:
            raise HTTPException(404, "Snapshot not found")
        snapshot, input_hash = saved
        try:
            validate_scenario(snapshot, scenario)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        run_id, queued = store.queue(scenario, input_hash)
        if queued:
            request.app.state.executor.submit(worker, run_id)
        job = fetch_run(run_id)
        response.headers["Location"] = f"/v1/simulations/{run_id}"
        if job["status"] == "complete":
            response.status_code = 200
        return run_response(job)

    @app.get("/v1/simulations/{run_id}")
    def simulation(run_id: str):
        return run_response(fetch_run(run_id))

    @app.get("/v1/simulations/{run_id}/export")
    def export(run_id: str):
        job = fetch_run(run_id)
        if job["status"] != "complete":
            raise HTTPException(409, "The simulation is still incomplete")
        return JSONResponse(run_response(job), headers={
            "Content-Disposition": f'attachment; filename="valsim-{run_id[:12]}.json"',
        })

    @app.post("/v1/simulations/{run_id}/compare")
    def compare_runs(run_id: str, request: CompareRequest):
        left, right = fetch_run(run_id), fetch_run(request.conditioned_id)
        if left["status"] != "complete" or right["status"] != "complete":
            raise HTTPException(409, "Both simulations must be complete")
        try:
            rows = compare(left["result"], right["result"])
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        snapshot, input_hash = store.snapshot(left["snapshot_id"])
        return envelope(rows, snapshot, input_hash, model=left["model_version"])

    if (DIST / "assets").exists():
        app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/disclaimer", include_in_schema=False)
    def disclaimer():
        return FileResponse(ROOT / "DISCLAIMER.md", media_type="text/plain")

    @app.get("/", include_in_schema=False)
    def web():
        if not (DIST / "index.html").is_file():
            raise HTTPException(503, "Build the frontend or launch the Vite development server.")
        return FileResponse(DIST / "index.html", headers={"Cache-Control": "no-cache"})

    return app


app = make_app()
