import csv
import io
from typing import Protocol

from .schema import Snapshot


class TournamentProvider(Protocol):
    def get_snapshot(self, external_id: str) -> Snapshot:
        """Return a validated point-in-time snapshot from an authorized source."""
        ...


def read_table(content: str, fields: set[str], required: set[str], numeric: set[str], limit: int) -> list[dict]:
    rows = csv.DictReader(io.StringIO(content.lstrip("\ufeff"), newline=""), strict=True)
    if not rows.fieldnames or len(rows.fieldnames) != len(set(rows.fieldnames)):
        raise ValueError("CSV headers must be unique and nonempty")
    names = set(rows.fieldnames)
    if not required <= names or not names <= fields:
        raise ValueError("CSV headers are missing required columns or contain unsupported columns")
    output = []
    for i, row in enumerate(rows, start=1):
        if i > limit or None in row or any(value is None for value in row.values()):
            raise ValueError("Malformed or oversized CSV table")
        item = {}
        for key, value in row.items():
            if value.strip():
                item[key] = int(value) if key in numeric else value
        output.append(item)
    return output


def snapshot_from_import(payload: dict) -> Snapshot:
    if "teams_csv" not in payload and "fixtures_csv" not in payload:
        return Snapshot.model_validate(payload)
    if "teams" in payload or "fixtures" in payload or any(not isinstance(payload.get(key), str) for key in ("teams_csv", "fixtures_csv")):
        raise ValueError("CSV imports require teams_csv and fixtures_csv in place of both JSON tables")
    data = payload.copy()
    counts = {"wins", "losses", "map_wins", "map_losses", "round_wins", "round_losses"}
    data["teams"] = read_table(data.pop("teams_csv"), {"id", "name"} | counts, {"id", "name"}, counts, 32)
    required = {"id", "team_a", "team_b", "date"}
    counts = {"best_of", "score_a", "score_b", "round_a", "round_b"}
    data["fixtures"] = read_table(
        data.pop("fixtures_csv"), required | counts | {"status", "scheduled_at"}, required, counts, 160,
    )
    for match in data["fixtures"]:
        for pair, key in ((("score_a", "score_b"), "score"), (("round_a", "round_b"), "round_score")):
            values = [match.pop(field, None) for field in pair]
            if any(value is not None for value in values):
                match[key] = values
    return Snapshot.model_validate(data)
