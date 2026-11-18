from bisect import bisect
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
from itertools import accumulate
from math import exp, log, sqrt
from random import Random
from typing import Callable, Iterable, NamedTuple

from .schema import BestOf, Condition, Fixture, Rules, Scenario, Score, Snapshot, Team, validate_score

MODEL_VERSION = "aggregate-maps-v1.0.0"


class Parameters(NamedTuple):
    name: str
    prior_maps: int
    round_weight: float
    map_scale: float
    veto_temperature: float


BASE = Parameters("Baseline", 6, 0.8, 1.0, 3.0)
SENSITIVITY = (
    Parameters("More shrinkage", 12, 0.4, 0.6, 2.0),
    Parameters("Less shrinkage", 3, 1.2, 1.4, 4.0),
)


def model_card() -> dict:
    return {
        "version": MODEL_VERSION,
        "calibration": "Experimental · no held-out calibration",
        "parameters": [item._asdict() for item in (BASE, *SENSITIVITY)],
        "assumptions": [
            "Overall team strength uses map wins and losses shrunk toward 50%, plus the available round margin.",
            "Unspecified map adjustments are zero. With equal map preferences the weighted veto draws uniformly.",
            "Map outcomes are independent given matchup strengths. Veto chooses maps; side and roster effects are unavailable.",
            "The sensitivity range compares two alternative sets of model parameters. It is separate from Monte Carlo sampling error.",
        ],
    }


def strength(team: Team, params: Parameters) -> float:
    log_odds = log((team.map_wins + params.prior_maps / 2) / (team.map_losses + params.prior_maps / 2))
    won, lost = team.round_wins or 0, team.round_losses or 0
    return log_odds + params.round_weight * (won - lost) / max(1, won + lost)


def sigmoid(value: float) -> float:
    return 1 / (1 + exp(-value))


class VetoAction(NamedTuple):
    actor: str
    action: str
    map: str


class MatchModel:
    def __init__(self, a: Team, b: Team, best_of: BestOf, rules: Rules, params: Parameters, condition: Condition | None):
        self.pool = rules.map_pool
        self.steps = rules.steps_for(best_of)
        self.target = best_of // 2 + 1
        self.condition = condition
        baseline = strength(a, params) - strength(b, params)
        self.probs = tuple(
            sigmoid(baseline + params.map_scale * (a.map_adjustments.get(name, 0) - b.map_adjustments.get(name, 0)))
            for name in self.pool
        )
        self.temperature = params.veto_temperature
        self.manual = tuple(self.pool.index(name) for name in condition.veto) if condition and condition.veto is not None else None
        self.options = lru_cache(maxsize=None)(self._options)
        self.series = lru_cache(maxsize=None)(self._series)

    def _options(self, index: int, remaining: tuple[int, ...]) -> tuple[tuple[float, ...], tuple[float, ...]]:
        step = self.steps[index]
        sign = 1 if (step.actor == "A") == (step.action == "pick") else -1
        weights = tuple(exp(self.temperature * sign * (self.probs[map_id] - 0.5)) for map_id in remaining)
        total = sum(weights)
        probabilities = tuple(weight / total for weight in weights)
        return probabilities, (*tuple(accumulate(probabilities))[:-1], 1.0)

    def veto(self, rng: Random) -> tuple[tuple[VetoAction, ...], tuple[int, ...]]:
        remaining = tuple(range(len(self.pool)))
        played = []
        actions = []
        for index, step in enumerate(self.steps):
            map_id = self.manual[index] if self.manual is not None else remaining[
                bisect(self.options(index, remaining)[1], rng.random())
            ]
            remaining = tuple(item for item in remaining if item != map_id)
            actions.append(VetoAction(step.actor, step.action, self.pool[map_id]))
            if step.action == "pick":
                played.append(map_id)
        actions.append(VetoAction("—", "decider", self.pool[remaining[0]]))
        return tuple(actions), (*played, remaining[0])

    def _series(self, played: tuple[int, ...]) -> dict[Score, float]:
        if self.condition and self.condition.score is not None:
            return {self.condition.score: 1.0}
        scores: dict[Score, float] = defaultdict(float)

        def visit(a: int, b: int, chance: float) -> None:
            if a == self.target or b == self.target:
                scores[a, b] += chance
                return
            p = self.probs[played[a + b]]
            visit(a + 1, b, chance * p)
            visit(a, b + 1, chance * (1 - p))

        visit(0, 0, 1.0)
        if self.condition and self.condition.winner:
            scores = {score: p for score, p in scores.items() if (score[0] > score[1]) == (self.condition.winner == "A")}
            total = sum(scores.values())
            return {score: p / total for score, p in scores.items()}
        return scores

    def fixture_distribution(self) -> dict[Score, float]:
        if self.condition and self.condition.score is not None:
            return {self.condition.score: 1.0}
        pool = tuple(range(len(self.pool)))
        if self.manual is not None:
            return self.series(self.veto(Random(0))[1])
        if len(set(self.probs)) == 1:
            return self.series(pool[:self.target * 2 - 1])
        # Bans may arrive in different orders and leave the same state.
        # Merge those paths before expanding the next action.
        states = {(pool, ()): 1.0}
        for index, step in enumerate(self.steps):
            following = defaultdict(float)
            for (remaining, picks), chance in states.items():
                for map_id, probability in zip(remaining, self.options(index, remaining)[0], strict=True):
                    available = tuple(item for item in remaining if item != map_id)
                    picked = (*picks, map_id) if step.action == "pick" else picks
                    following[available, picked] += chance * probability
            states = following
        scores = defaultdict(float)
        for (remaining, picks), chance in states.items():
            for score, p in self.series((*picks, remaining[0])).items():
                scores[score] += chance * p
        return scores


def sampler(distribution: dict[Score, float]) -> Callable[[float], Score]:
    values = tuple(distribution)
    edges = tuple(accumulate(distribution.values()))[:-1]
    return lambda draw: values[bisect(edges, draw)]


def rng_for(seed: int, label: str) -> Random:
    digest = sha256(f"{seed}:{label}".encode()).digest()
    return Random(int.from_bytes(digest[:16], "big"))


def interval(successes: int, n: int) -> list[float]:
    # Wilson score interval remains meaningful at the two endpoints.
    p, z = successes / n, 1.959963984540054
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    radius = z * sqrt(p * (1 - p) / n + z**2 / (4 * n * n)) / denom
    return [max(0.0, center - radius), min(1.0, center + radius)]


def outcome(count: int, n: int) -> dict:
    return {"probability": count / n, "sampling_95": interval(count, n)}


@dataclass(slots=True)
class Table:
    # wins, losses, map wins, map losses, round wins, round losses
    totals: dict[str, list[int | None]]
    head_to_head: dict[frozenset[str], tuple[int, dict[str, int]]]

    @classmethod
    def from_snapshot(cls, snapshot: Snapshot) -> "Table":
        table = cls({
            team.id: [team.wins, team.losses, team.map_wins, team.map_losses, team.round_wins, team.round_losses]
            for team in snapshot.teams
        }, {})
        for fixture in snapshot.fixtures:
            if fixture.status == "completed":
                table.record(fixture, fixture.score, fixture.round_score, update_totals=not snapshot.aggregate_includes_completed)
        return table

    def copy(self) -> "Table":
        return Table(
            {team: values.copy() for team, values in self.totals.items()},
            {pair: (games, wins.copy()) for pair, (games, wins) in self.head_to_head.items()},
        )

    def record(self, fixture: Fixture, score: Score, rounds: tuple[int, int] | None = None, *, update_totals: bool = True) -> None:
        a, b = fixture.team_a, fixture.team_b
        games, wins = self.head_to_head.get(frozenset((a, b)), (0, {a: 0, b: 0}))
        wins[a if score[0] > score[1] else b] += 1
        self.head_to_head[frozenset((a, b))] = (games + 1, wins)
        if not update_totals:
            return
        for i, team in enumerate((a, b)):
            values = self.totals[team]
            values[int(score[i] < score[1 - i])] += 1
            values[2] += score[i]
            values[3] += score[1 - i]
            if values[4] is None or rounds is None:
                values[4:6] = [None, None]
            else:
                values[4] += rounds[i]
                values[5] += rounds[1 - i]

    def ranked(self, rules: Rules) -> list[tuple[str, ...]]:
        def split(teams: tuple[str, ...], criteria: tuple[str, ...]) -> Iterable[tuple[str, ...]]:
            if len(teams) == 1 or not criteria:
                yield teams
                return
            criterion, *remaining = criteria
            values = self._criterion(teams, criterion, rules.pairings_per_group)
            if values is None:
                yield teams
                return
            groups = defaultdict(list)
            for team in teams:
                groups[values[team]].append(team)
            for value in sorted(groups, reverse=True):
                yield from split(tuple(groups[value]), tuple(remaining))

        return list(split(tuple(self.totals), rules.rank_by))

    def _criterion(self, teams: tuple[str, ...], criterion: str, pairings: int) -> dict[str, int] | None:
        if criterion == "wins":
            return {team: self.totals[team][0] for team in teams}
        if criterion == "map_diff":
            return {team: self.totals[team][2] - self.totals[team][3] for team in teams}
        if criterion == "round_diff":
            if any(self.totals[team][4] is None for team in teams):
                return None
            return {team: self.totals[team][4] - self.totals[team][5] for team in teams}
        total = dict.fromkeys(teams, 0)
        for index, a in enumerate(teams):
            for b in teams[index + 1:]:
                recorded = self.head_to_head.get(frozenset((a, b)))
                if not recorded or recorded[0] != pairings:
                    return None
                total[a] += recorded[1][a]
                total[b] += recorded[1][b]
        return total


def observed_standings(snapshot: Snapshot) -> list[dict]:
    table = Table.from_snapshot(snapshot)
    positions = []
    rank = 1
    names = {team.id: team.name for team in snapshot.teams}
    for tied in table.ranked(snapshot.rules):
        for team in tied:
            values = table.totals[team]
            positions.append({
                "team": team, "name": names[team], "rank": rank, "tied": len(tied) > 1,
                **dict(zip(("wins", "losses", "map_wins", "map_losses", "round_wins", "round_losses"), values)),
            })
        rank += len(tied)
    return positions


def validate_scenario(snapshot: Snapshot, scenario: Scenario) -> None:
    if scenario.snapshot_id != snapshot.id:
        raise ValueError("Scenario references a different snapshot")
    if scenario.scope == "bracket":
        if snapshot.bracket is None:
            raise ValueError("This snapshot does not have a bracket")
        eligible = {node.id: node.best_of for node in snapshot.bracket.nodes if not node.observed}
    else:
        eligible = {fixture.id: fixture.best_of for fixture in snapshot.fixtures if fixture.status == "scheduled"}
        if scenario.scope == "remaining_group" and any(fixture.status == "ongoing" for fixture in snapshot.fixtures):
            raise ValueError("Import a final score for each ongoing match before forecasting the group")
        if scenario.fixture_id is not None:
            if scenario.fixture_id not in eligible:
                raise ValueError("Select a scheduled fixture")
            eligible = {scenario.fixture_id: eligible[scenario.fixture_id]}
    if not eligible:
        raise ValueError("No unplayed fixtures in this scope")
    for condition in scenario.conditions:
        if condition.fixture_id not in eligible:
            raise ValueError(f"Fixture {condition.fixture_id} cannot be changed in this scope")
        best_of = eligible[condition.fixture_id]
        if condition.score is not None:
            validate_score(condition.score, best_of)
        if condition.veto is not None:
            steps = snapshot.rules.steps_for(best_of)
            unique = set(condition.veto)
            if len(condition.veto) != len(steps) or len(unique) != len(steps) or not unique <= set(snapshot.rules.map_pool):
                raise ValueError("Manual veto must select one unique in-pool map for every ordered action")
