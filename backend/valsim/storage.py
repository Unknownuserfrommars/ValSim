import json
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import sqlite3
from typing import Iterator

from .model import MODEL_VERSION
from .schema import Scenario, Snapshot


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


class RevisionConflict(ValueError):
    pass


class Store:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def migrate(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            for migration in sorted(Path(__file__).with_name("migrations").glob("*.sql")):
                number = int(migration.name.split("_", 1)[0])
                if number <= version:
                    continue
                for statement in migration.read_text(encoding="utf-8").split(";"):
                    if statement.strip():
                        db.execute(statement)
                db.execute(f"PRAGMA user_version = {number}")

    def save_snapshot(self, snapshot: Snapshot) -> str:
        payload = canonical(snapshot.model_dump(mode="json"))
        input_hash = digest(payload)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT input_hash FROM snapshots WHERE id = ?", (snapshot.id,)).fetchone()
            if old and old["input_hash"] != input_hash:
                raise RevisionConflict("This snapshot ID already exists. Use a new revision ID for corrections.")
            if not old:
                db.execute(
                    "INSERT INTO snapshots (id, event_id, input_hash, payload) VALUES (?, ?, ?, ?)",
                    (snapshot.id, snapshot.event_id, input_hash, payload),
                )
        return input_hash

    def snapshot(self, snapshot_id: str) -> tuple[Snapshot, str] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM snapshots WHERE id = ?", (snapshot_id,)).fetchone()
        return self.decode_snapshot(row) if row else None

    def event(self, event_id: str) -> tuple[Snapshot, str] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM snapshots WHERE event_id = ? ORDER BY rowid DESC LIMIT 1",
                             (event_id,)).fetchone()
        return self.decode_snapshot(row) if row else None

    def events(self) -> list[tuple[Snapshot, str]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM snapshots WHERE rowid IN (SELECT MAX(rowid) FROM snapshots GROUP BY event_id) "
                "ORDER BY rowid DESC"
            ).fetchall()
        return [self.decode_snapshot(row) for row in rows]

    def revisions(self, event_id: str) -> list[dict]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT id, input_hash, received_at, payload FROM snapshots WHERE event_id = ? ORDER BY rowid DESC",
                (event_id,),
            ).fetchall()
        return [{
            "id": row["id"], "input_hash": row["input_hash"], "received_at_utc": row["received_at"] + "Z",
            "observed_on": json.loads(row["payload"])["source"]["observed_on"],
        } for row in rows]

    @staticmethod
    def decode_snapshot(row: sqlite3.Row) -> tuple[Snapshot, str]:
        return Snapshot.model_validate_json(row["payload"]), row["input_hash"]

    def queue(self, scenario: Scenario, input_hash: str) -> tuple[str, bool]:
        config = scenario.model_dump(mode="json")
        config["conditions"].sort(key=lambda condition: condition["fixture_id"])
        payload = canonical(config)
        run_id = digest(canonical([input_hash, MODEL_VERSION, config]))
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT status FROM simulations WHERE id = ?", (run_id,)).fetchone()
            if not old:
                db.execute(
                    "INSERT INTO simulations (id, snapshot_id, model_version, config, status) VALUES (?, ?, ?, ?, 'queued')",
                    (run_id, scenario.snapshot_id, MODEL_VERSION, payload),
                )
            elif old["status"] == "failed":
                db.execute("UPDATE simulations SET status = 'queued', error = NULL, progress = 0 WHERE id = ?", (run_id,))
            else:
                return run_id, False
        return run_id, True

    def recover(self) -> list[str]:
        with self.connect() as db:
            db.execute("UPDATE simulations SET status = 'failed', error = 'Interrupted job used a previous model version' "
                       "WHERE model_version != ? AND status IN ('queued', 'running')", (MODEL_VERSION,))
            db.execute("UPDATE simulations SET status = 'queued', progress = 0 WHERE status = 'running'")
            rows = db.execute("SELECT id FROM simulations WHERE status = 'queued' ORDER BY rowid").fetchall()
        return [row["id"] for row in rows]

    def claim(self, run_id: str) -> Scenario | None:
        with self.connect() as db:
            result = db.execute("UPDATE simulations SET status = 'running' WHERE id = ? AND status = 'queued'", (run_id,))
            if not result.rowcount:
                return None
            row = db.execute("SELECT config FROM simulations WHERE id = ?", (run_id,)).fetchone()
        return Scenario.model_validate_json(row["config"])

    def progress(self, run_id: str, progress: int) -> None:
        with self.connect() as db:
            db.execute("UPDATE simulations SET progress = ? WHERE id = ?", (progress, run_id))

    def finish(self, run_id: str, result: dict) -> None:
        with self.connect() as db:
            db.execute("UPDATE simulations SET status = 'complete', progress = 100, result = ? WHERE id = ?",
                       (canonical(result), run_id))

    def fail(self, run_id: str, error: str) -> None:
        with self.connect() as db:
            db.execute("UPDATE simulations SET status = 'failed', error = ? WHERE id = ?", (error, run_id))

    def simulation(self, run_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT simulations.*, snapshots.input_hash FROM simulations JOIN snapshots ON snapshots.id = snapshot_id "
                "WHERE simulations.id = ?", (run_id,),
            ).fetchone()
        if not row:
            return None
        value = dict(row)
        value["config"] = json.loads(value["config"])
        if value["result"]:
            value["result"] = json.loads(value["result"])
        return value
