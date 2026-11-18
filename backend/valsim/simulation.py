from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Callable

from .model import (
    BASE, SENSITIVITY, MatchModel, Parameters, Table, interval,
    model_card, outcome, rng_for, sampler, validate_scenario,
)
from .schema import BracketSlot, Condition, Scenario, Score, Snapshot, Team

Progress = Callable[[int], None]


def tick(index: int, n: int, progress: Progress, start: int, span: int) -> None:
    if index % max(1, n // 20) == 0 or index == n:
        progress(start + index * span // n)


def score_rows(counts: Counter[Score], n: int) -> list[dict]:
    return [{"score": score, **outcome(count, n)} for score, count in sorted(counts.items(), reverse=True)]


def score_setup(snapshot: Snapshot, scenario: Scenario) -> tuple[dict[str, Team], dict[str, Condition]]:
    return teams_with_observed_results(snapshot), {condition.fixture_id: condition for condition in scenario.conditions}


def teams_with_observed_results(snapshot: Snapshot) -> dict[str, Team]:
    table = Table.from_snapshot(snapshot)
    return {
        team.id: team.model_copy(update=dict(zip(
            ("wins", "losses", "map_wins", "map_losses", "round_wins", "round_losses"), table.totals[team.id]
        )))
        for team in snapshot.teams
    }


def matchup(snapshot: Snapshot, scenario: Scenario, progress: Progress) -> dict:
    fixture = next(match for match in snapshot.fixtures if match.id == scenario.fixture_id)
    teams, conditions = score_setup(snapshot, scenario)
    a, b, n = teams[fixture.team_a], teams[fixture.team_b], scenario.iterations
    condition = conditions.get(fixture.id)
    model = MatchModel(a, b, fixture.best_of, snapshot.rules, BASE, condition)
    veto_rng = rng_for(scenario.seed, f"veto:{fixture.id}")
    score_rng = rng_for(scenario.seed, f"score:{fixture.id}")
    paths = Counter()
    actions = Counter()
    counts = Counter()
    maps = Counter()
    samplers = {}
    example = None
    for draw in range(1, n + 1):
        path, played = model.veto(veto_rng)
        paths[path] += 1
        for index, action in enumerate(path):
            actions[index, action.map] += 1
        if played not in samplers:
            samplers[played] = sampler(model.series(played))
        score = samplers[played](score_rng.random())
        counts[score] += 1
        maps.update(snapshot.rules.map_pool[map_id] for map_id in played[:sum(score)])
        if example is None:
            example = [dict(action._asdict(), frequency=None) for action in path]
        tick(draw, n, progress, 0, 94)
    for index, action in enumerate(example):
        action["frequency"] = actions[index, action["map"]] / n
    exact = []
    for params in (BASE, *SENSITIVITY):
        variant = MatchModel(a, b, fixture.best_of, snapshot.rules, params, condition)
        exact.append(sum(p for (left, right), p in variant.fixture_distribution().items() if left > right))
    win_a = sum(count for (left, right), count in counts.items() if left > right)
    return {
        "fixture_id": fixture.id,
        "team_a": a.id, "team_b": b.id,
        "wins": {a.id: outcome(win_a, n), b.id: outcome(n - win_a, n)},
        "exact_win_a": exact[0],
        "model_sensitivity_a": [min(exact), max(exact)],
        "scores": score_rows(counts, n),
        "map_probabilities": [{"map": name, "p_a": p, "play_frequency": maps[name] / n} for name, p in zip(model.pool, model.probs)],
        "veto": example,
        "veto_paths": [
            {"actions": [action._asdict() for action in path], "probability": count / n}
            for path, count in paths.most_common(5)
        ],
    }


@dataclass(slots=True)
class Placements:
    ranks: list[float]
    lower: int = 0
    upper: int = 0
    tied: int = 0
    map_diff: Counter[int] = field(default_factory=Counter)
    series_wins: Counter[int] = field(default_factory=Counter)


def ranked_after_draws(
    snapshot: Snapshot, scenario: Scenario, params: Parameters, progress: Progress, start: int, span: int,
) -> dict[str, Placements]:
    table = Table.from_snapshot(snapshot)
    teams, conditions = score_setup(snapshot, scenario)
    fixtures = [fixture for fixture in snapshot.fixtures if fixture.status == "scheduled"]
    simulations = [
        (fixture,
         sampler(MatchModel(teams[fixture.team_a], teams[fixture.team_b], fixture.best_of, snapshot.rules,
                            params, conditions.get(fixture.id)).fixture_distribution()),
         rng_for(scenario.seed, f"group:{fixture.id}").random)
        for fixture in fixtures
    ]
    places = {team: Placements([0.0] * len(teams)) for team in teams}
    slots, n = snapshot.rules.qualification_slots, scenario.iterations
    simple_order = snapshot.rules.rank_by == ("wins", "map_diff")
    for draw in range(1, n + 1):
        if simple_order:
            totals = {team: values[:4] for team, values in table.totals.items()}
            for fixture, take, random in simulations:
                left, right = take(random())
                a, b = totals[fixture.team_a], totals[fixture.team_b]
                a[int(left < right)] += 1
                b[int(right < left)] += 1
                a[2] += left
                a[3] += right
                b[2] += right
                b[3] += left
            groups = defaultdict(list)
            for team, (won, _, map_won, map_lost) in totals.items():
                groups[won, map_won - map_lost].append(team)
            ranked = (groups[key] for key in sorted(groups, reverse=True))
        else:
            ranked_table = table.copy()
            for fixture, take, random in simulations:
                ranked_table.record(fixture, take(random()))
            totals, ranked = ranked_table.totals, ranked_table.ranked(snapshot.rules)
        offset = 0
        for tied in ranked:
            width = len(tied)
            end = offset + width
            for team in tied:
                row = places[team]
                row.lower += end <= slots
                row.upper += offset < slots
                if start == 0:
                    row.tied += width > 1
                    row.map_diff[totals[team][2] - totals[team][3]] += 1
                    row.series_wins[totals[team][0]] += 1
                    for rank in range(offset, end):
                        row.ranks[rank] += 1 / width
            offset = end
        tick(draw, n, progress, start, span)
    return places


def group(snapshot: Snapshot, scenario: Scenario, progress: Progress) -> dict:
    n = scenario.iterations
    base = ranked_after_draws(snapshot, scenario, BASE, progress, 0, 58)
    alternate = [
        ranked_after_draws(snapshot, scenario, params, progress, 58 + i * 20, 20)
        for i, params in enumerate(SENSITIVITY)
    ]
    rows = []
    for team, row in base.items():
        variants = [row, *(variant[team] for variant in alternate)]
        rows.append({
            "team": team,
            "qualification": {
                "lower": row.lower / n, "upper": row.upper / n,
                "unresolved": (row.upper - row.lower) / n,
                "sampling_95": [interval(row.lower, n)[0], interval(row.upper, n)[1]],
                "model_sensitivity": [min(v.lower for v in variants) / n, max(v.upper for v in variants) / n],
            },
            "ranks": [value / n for value in row.ranks],
            "unresolved_placement": row.tied / n,
            "map_differential": {key: value / n for key, value in sorted(row.map_diff.items())},
            "series_wins": {key: value / n for key, value in sorted(row.series_wins.items())},
        })
    return {
        "teams": rows,
        "qualification_slots": snapshot.rules.qualification_slots,
        "qualification_verified": snapshot.rules.verification == "verified",
        "rank_allocation": "Display shares each unresolved tied rank equally. Advancement bounds keep ties unresolved.",
        "fixture_count": sum(fixture.status == "scheduled" for fixture in snapshot.fixtures),
        "locked_fixture_count": sum(fixture.status == "completed" for fixture in snapshot.fixtures),
        "baseline_series_count": sum(team.wins for team in snapshot.teams),
        "observed_series_count": sum(team.wins for team in teams_with_observed_results(snapshot).values()),
    }


def bracket(snapshot: Snapshot, scenario: Scenario, progress: Progress) -> dict:
    graph = snapshot.bracket
    teams, conditions = score_setup(snapshot, scenario)
    nodes = graph.nodes
    n = scenario.iterations
    rngs = {node.id: rng_for(scenario.seed, f"bracket:{node.id}").random for node in nodes}
    draws = {}
    winners = {node.id: Counter() for node in nodes}
    appearances = {node.id: Counter() for node in nodes}
    for draw in range(1, n + 1):
        prior = {}

        def resolve(slot: BracketSlot) -> str:
            return slot.team or prior[slot.winner_of or slot.loser_of][int(slot.loser_of is not None)]

        for node in nodes:
            a, b = resolve(node.a), resolve(node.b)
            if a == b:
                raise ValueError(f"Bracket graph can send {a} to both slots of {node.id}")
            if node.observed:
                score = node.observed.score
            else:
                key = (node.id, a, b)
                if key not in draws:
                    model = MatchModel(teams[a], teams[b], node.best_of, snapshot.rules, BASE, conditions.get(node.id))
                    draws[key] = sampler(model.fixture_distribution())
                score = draws[key](rngs[node.id]())
            prior[node.id] = (a, b) if score[0] > score[1] else (b, a)
            winners[node.id][prior[node.id][0]] += 1
            appearances[node.id].update((a, b))
        tick(draw, n, progress, 0, 98)
    return {
        "title": graph.title, "final": graph.final,
        "champion": {team: outcome(winners[graph.final][team], n) for team in teams},
        "nodes": [
            {
                "id": node.id, "locked": node.observed is not None,
                "winner": {team: outcome(count, n) for team, count in sorted(winners[node.id].items())},
                "appearance": {team: count / n for team, count in sorted(appearances[node.id].items())},
            }
            for node in nodes
        ],
    }


def run(snapshot: Snapshot, scenario: Scenario, progress: Progress = lambda _: None) -> dict:
    validate_scenario(snapshot, scenario)
    engine = {"match": matchup, "remaining_group": group, "bracket": bracket}[scenario.scope]
    return {
        "scope": scenario.scope,
        "scenario": scenario.model_dump(mode="json"),
        "model": model_card(),
        "rules": snapshot.rules.model_dump(mode="json"),
        "output": engine(snapshot, scenario, progress),
    }


def compare(baseline: dict, conditioned: dict) -> list[dict]:
    if baseline["scope"] != "remaining_group" or conditioned["scope"] != "remaining_group":
        raise ValueError("Comparisons require two group simulations")
    left = baseline["scenario"]
    right = conditioned["scenario"]
    if left["conditions"] or not right["conditions"]:
        raise ValueError("Compare an unconditioned baseline with a conditioned run")
    if any(left[key] != right[key] for key in ("snapshot_id", "iterations", "seed")):
        raise ValueError("Compare runs using identical snapshot, seed, and draw count")
    if baseline["model"]["version"] != conditioned["model"]["version"]:
        raise ValueError("Compare runs using the same model version")
    previous = {row["team"]: row["qualification"] for row in baseline["output"]["teams"]}
    output = []
    for row in conditioned["output"]["teams"]:
        team = row["team"]
        before, after = previous[team], row["qualification"]
        output.append({
            "team": team, "baseline": before, "conditioned": after,
            "change": [after["lower"] - before["upper"], after["upper"] - before["lower"]],
        })
    return output
