from datetime import date
from math import isfinite
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

Key = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Count = Annotated[int, Field(ge=0, le=100_000, strict=True)]
BestOf = Literal[1, 3, 5]
VetoKey = Literal["1", "3", "5"]
Status = Literal["ongoing", "upcoming", "finished"]
Criterion = Literal["wins", "map_diff", "round_diff", "head_to_head"]
Score = tuple[Annotated[int, Field(ge=0, le=3)], Annotated[int, Field(ge=0, le=3)]]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class Source(Record):
    provider: Label
    reference: Annotated[str, Field(min_length=1, max_length=2000)]
    observed_on: date
    observed_at: AwareDatetime | None = None
    method: Literal["manual", "authorized_export"]
    permission: Literal["user_supplied", "public_reference", "permissioned", "fictional_demo"]
    verification: Literal["unverified", "verified"]
    license: Annotated[str, Field(max_length=500)] | None = None
    notes: Annotated[str, Field(max_length=2000)] = ""

    @model_validator(mode="after")
    def validate_permission(self) -> Self:
        if self.permission == "permissioned" and not self.license:
            raise ValueError("Permissioned imports require the reuse terms or license reference")
        if self.permission != "permissioned" and (self.method != "manual" or self.verification != "unverified"):
            raise ValueError("Manual references must be marked manual and unverified")
        return self


class Team(Record):
    id: Key
    name: Label
    wins: Count = 0
    losses: Count = 0
    map_wins: Count = 0
    map_losses: Count = 0
    round_wins: Count | None = None
    round_losses: Count | None = None
    map_adjustments: dict[Label, float] = Field(default_factory=dict, max_length=11)

    @model_validator(mode="after")
    def validate_statistics(self) -> Self:
        if (self.round_wins is None) != (self.round_losses is None):
            raise ValueError("Supply both round totals or neither")
        if any(not isfinite(value) or abs(value) > 2 for value in self.map_adjustments.values()):
            raise ValueError("Map log-odds adjustments must be finite and between -2 and 2")
        return self


class VetoStep(Record):
    actor: Literal["A", "B"]
    action: Literal["ban", "pick"]


DEFAULT_STEPS = {
    1: ("A ban", "B ban", "A ban", "B ban", "A ban", "B ban"),
    3: ("A ban", "B ban", "A pick", "B pick", "A ban", "B ban"),
    5: ("A ban", "B ban", "A pick", "B pick", "A pick", "B pick"),
}


class Rules(Record):
    version: Key
    verification: Literal["illustrative", "verified"]
    reference: Annotated[str, Field(max_length=1000)] | None = None
    qualification_slots: Annotated[int, Field(ge=0, le=32)]
    rank_by: tuple[Criterion, ...] = ("wins", "map_diff")
    map_pool: Annotated[tuple[Label, ...], Field(min_length=1, max_length=11)]
    veto_order: dict[VetoKey, tuple[VetoStep, ...]] = Field(default_factory=dict)
    pairings_per_group: Annotated[int, Field(ge=1, le=6)] = 1
    notes: Annotated[str, Field(max_length=2000)] = ""

    def steps_for(self, best_of: BestOf) -> tuple[VetoStep, ...]:
        if str(best_of) in self.veto_order:
            return self.veto_order[str(best_of)]
        if self.verification == "illustrative" and len(self.map_pool) == 7:
            return tuple(VetoStep(actor=action[0], action=action[2:]) for action in DEFAULT_STEPS[best_of])
        raise ValueError(f"Supply an explicit veto order for BO{best_of}")

    @model_validator(mode="after")
    def validate_rules(self) -> Self:
        if self.verification == "verified" and not self.reference:
            raise ValueError("Verified rules require a source reference")
        if len({name.casefold() for name in self.map_pool}) != len(self.map_pool):
            raise ValueError("Map pool names must be unique")
        if len(self.rank_by) != len(set(self.rank_by)):
            raise ValueError("Standings criteria must be unique")
        for format_key, steps in self.veto_order.items():
            best_of = int(format_key)
            if len(steps) != len(self.map_pool) - 1 or sum(step.action == "pick" for step in steps) != best_of - 1:
                raise ValueError(f"BO{best_of} veto must leave one decider and pick {best_of - 1} maps")
        return self


def validate_score(score: Score, best_of: BestOf) -> None:
    target = best_of // 2 + 1
    if max(score) != target or min(score) >= target:
        raise ValueError(f"{score[0]}–{score[1]} is not a valid BO{best_of} score")


class Fixture(Record):
    id: Key
    team_a: Key
    team_b: Key
    date: date
    scheduled_at: AwareDatetime | None = None
    best_of: BestOf = 3
    status: Literal["scheduled", "ongoing", "completed"] = "scheduled"
    score: Score | None = None
    round_score: tuple[Count, Count] | None = None

    @model_validator(mode="after")
    def validate_fixture(self) -> Self:
        if self.team_a == self.team_b:
            raise ValueError("A fixture requires two distinct teams")
        if self.status == "completed":
            if self.score is None:
                raise ValueError("Completed fixtures require a series score")
            validate_score(self.score, self.best_of)
        elif self.score is not None or self.round_score is not None:
            raise ValueError("Only completed fixtures carry final result totals")
        return self


class BracketSlot(Record):
    team: Key | None = None
    winner_of: Key | None = None
    loser_of: Key | None = None

    @model_validator(mode="after")
    def validate_slot(self) -> Self:
        if sum(value is not None for value in (self.team, self.winner_of, self.loser_of)) != 1:
            raise ValueError("A bracket slot requires one team, source winner, or source loser")
        return self


class BracketNode(Record):
    id: Key
    a: BracketSlot
    b: BracketSlot
    best_of: BestOf = 3
    observed: Fixture | None = None


class Bracket(Record):
    title: Label
    nodes: Annotated[tuple[BracketNode, ...], Field(min_length=1, max_length=80)]
    final: Key

    @model_validator(mode="after")
    def validate_graph(self) -> Self:
        prior: set[str] = set()
        for node in self.nodes:
            if node.id in prior or node.a == node.b:
                raise ValueError("Invalid or duplicate bracket node")
            for slot in (node.a, node.b):
                dependency = slot.winner_of or slot.loser_of
                if dependency and dependency not in prior:
                    raise ValueError("Bracket nodes must follow their winner/loser dependencies")
            if node.observed and (
                node.observed.status != "completed" or node.observed.best_of != node.best_of
            ):
                raise ValueError("An observed bracket match must be completed with the configured best-of")
            prior.add(node.id)
        if self.final != self.nodes[-1].id:
            raise ValueError("The final must be the last bracket node")
        return self


class Snapshot(Record):
    schema_version: Literal[1] = 1
    id: Key
    event_id: Key
    title: Label
    stage: Label
    region: Label
    tier: Label | None = None
    status: Status
    source: Source
    rules: Rules
    teams: Annotated[tuple[Team, ...], Field(min_length=2, max_length=32)]
    fixtures: Annotated[tuple[Fixture, ...], Field(max_length=160)]
    aggregate_includes_completed: bool = False
    bracket: Bracket | None = None

    @model_validator(mode="after")
    def validate_snapshot(self) -> Self:
        known = {team.id for team in self.teams}
        if len(known) != len(self.teams):
            raise ValueError("Team IDs must be unique")
        if self.rules.qualification_slots >= len(known):
            raise ValueError("Advancement slots must be fewer than the number of teams")
        pool = set(self.rules.map_pool)
        if any(not set(team.map_adjustments) <= pool for team in self.teams):
            raise ValueError("Team map adjustments reference a map outside this event pool")
        for attr_a, attr_b in (("wins", "losses"), ("map_wins", "map_losses")):
            if sum(getattr(team, attr_a) for team in self.teams) != sum(getattr(team, attr_b) for team in self.teams):
                raise ValueError(f"Group baseline {attr_a} and {attr_b} must balance")
        ids: set[str] = set()
        pairs: dict[frozenset[str], int] = {}
        formats: set[BestOf] = set()
        for fixture in self.fixtures:
            pair = frozenset((fixture.team_a, fixture.team_b))
            if not pair <= known or fixture.id in ids:
                raise ValueError(f"Unknown team or duplicate fixture ID in {fixture.id}")
            ids.add(fixture.id)
            pairs[pair] = pairs.get(pair, 0) + 1
            if pairs[pair] > self.rules.pairings_per_group:
                raise ValueError(f"Too many group fixtures between {fixture.team_a} and {fixture.team_b}")
            if fixture.status == "scheduled":
                formats.add(fixture.best_of)
        if self.bracket:
            self.validate_bracket(known)
            formats.update(node.best_of for node in self.bracket.nodes if not node.observed)
        for best_of in formats:
            self.rules.steps_for(best_of)
        return self

    def validate_bracket(self, known: set[str]) -> None:
        resolved: dict[str, tuple[str, str]] = {}
        for node in self.bracket.nodes:
            for slot in (node.a, node.b):
                if slot.team and slot.team not in known:
                    raise ValueError(f"Unknown bracket team {slot.team}")
            if node.observed:
                def team_for(slot: BracketSlot) -> str | None:
                    if slot.team:
                        return slot.team
                    previous = resolved.get(slot.winner_of or slot.loser_of or "")
                    return previous[int(slot.loser_of is not None)] if previous else None

                actual = node.observed
                if (actual.team_a, actual.team_b) != (team_for(node.a), team_for(node.b)):
                    raise ValueError("Observed bracket teams must agree with locked graph inputs")
                resolved[node.id] = (
                    (actual.team_a, actual.team_b) if actual.score[0] > actual.score[1]
                    else (actual.team_b, actual.team_a)
                )


class Condition(Record):
    fixture_id: Key
    winner: Literal["A", "B"] | None = None
    score: Score | None = None
    veto: Annotated[tuple[Label, ...], Field(max_length=10)] | None = None

    @model_validator(mode="after")
    def validate_condition(self) -> Self:
        if self.winner is not None and self.score is not None:
            raise ValueError("Use either a winner or a score for the same fixture")
        if self.winner is None and self.score is None and self.veto is None:
            raise ValueError("A condition must set a winner, score, or veto")
        return self


class Scenario(Record):
    snapshot_id: Key
    scope: Literal["match", "remaining_group", "bracket"]
    fixture_id: Key | None = None
    iterations: Annotated[int, Field(ge=1, le=100_000, strict=True)] = 10_000
    seed: Annotated[int, Field(ge=0, le=2**53 - 1, strict=True)] = 20261118
    conditions: Annotated[tuple[Condition, ...], Field(max_length=160)] = ()

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        if (self.scope == "match") != (self.fixture_id is not None):
            raise ValueError("Exactly the match scope requires a fixture ID")
        ids = [condition.fixture_id for condition in self.conditions]
        if len(ids) != len(set(ids)):
            raise ValueError("Supply at most one condition per fixture")
        return self
