from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from math import sqrt
from statistics import pstdev
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .players import Appearance


FACET_MODEL = "player-facets-v1.0.0"
FACET_LABELS = {
    "AIM": "Aiming", "ENTRY": "Opening duels", "UTIL": "Utility",
    "CLUTCH": "Clutching", "IQ": "Game sense", "CONS": "Consistency", "FLEX": "Flexibility",
}
ROLE_WEIGHTS = {
    "Duelist": (25, 30, 10, 10, 10, 10, 5),
    "Initiator": (15, 12, 28, 10, 18, 12, 5),
    "Controller": (12, 8, 28, 12, 22, 13, 5),
    "Sentinel": (18, 10, 18, 18, 20, 11, 5),
}
MIN_COMPARABLE_PLAYERS = 5


@dataclass(frozen=True)
class Sample:
    value: float
    exposure: int
    roles: Counter[str]
    evidence: str


@dataclass(frozen=True)
class Rate:
    numerator: str
    denominator: str
    minimum: int
    prior: int
    scale_floor: float
    label: str
    missing: str
    opening_net: bool = False
    proxy: bool = False


RATES = {
    "AIM": Rate("aim_duels_won", "aim_duel_attempts", 25, 35, 0.08,
                "aim-duel win rate", "Aim-duel outcomes are unavailable."),
    "ENTRY": Rate("first_kills", "first_deaths", 20, 35, 0.06,
                  "net openings per round", "First kills and first deaths are unavailable.", opening_net=True),
    "UTIL": Rate("utility_assists", "rounds", 60, 120, 0.06,
                 "utility assists per round", "Utility-specific assists are unavailable."),
    "CLUTCH": Rate("clutches_won", "clutch_opportunities", 8, 30, 0.10,
                   "clutch win rate", "Clutch attempts and wins are unavailable."),
    "IQ": Rate("trade_kills", "trade_opportunities", 20, 40, 0.10,
               "trade conversion", "Trade attempts and conversions are unavailable.", proxy=True),
}
AIM_PROXY = Rate("kills", "rounds", 60, 120, 0.10,
                 "kills per round", "Kill and round totals are unavailable.", proxy=True)


def role_shares(history: list[Appearance]) -> Counter[str]:
    shares: Counter[str] = Counter()
    for item in history:
        mix = item.role_mix
        for role, count in mix.items():
            shares[role] += count / mix.total()
    total = shares.total()
    return Counter({role: count / total for role, count in shares.items()}) if total else shares


def role_weights(history: list[Appearance]) -> dict[str, float]:
    shares = role_shares(history)
    return {
        code: round(sum(ROLE_WEIGHTS[role][index] * share for role, share in shares.items()), 3)
        for index, code in enumerate(FACET_LABELS)
    } if shares else {}


def metric_counts(item: Appearance, rate: Rate) -> tuple[int, int] | None:
    if rate is AIM_PROXY:
        return item.row.kills, item.rounds
    details = item.row.skill_telemetry
    if details is None:
        return None
    numerator = getattr(details, rate.numerator)
    denominator = item.rounds if rate.denominator == "rounds" else getattr(details, rate.denominator)
    return (numerator, denominator) if numerator is not None and denominator is not None else None


def rate_sample(history: list[Appearance], rate: Rate) -> tuple[Sample | None, str, bool]:
    measured = [(item, *counts) for item in history if (counts := metric_counts(item, rate)) is not None]
    if not measured:
        return None, rate.missing, False
    numerator = sum(value for _, value, _ in measured)
    denominator = sum(count for _, _, count in measured)
    exposure = numerator + denominator if rate.opening_net else denominator
    if len(measured) < 2 or exposure < rate.minimum:
        unit = "rounds" if rate.denominator == "rounds" else "opportunities"
        return None, f"Needs at least 2 recorded series and {rate.minimum} {unit}.", True
    if rate.opening_net:
        value = (numerator - denominator) / sum(item.rounds for item, _, _ in measured)
        observation = f"{numerator} first kills · {denominator} first deaths"
    elif rate.denominator == "rounds":
        value = numerator / denominator
        observation = f"{value:.2f} {rate.label} · {denominator} rounds"
    else:
        value = numerator / denominator
        observation = f"{value:.0%} {rate.label} · {denominator} opportunities"
    return Sample(value, exposure, role_shares([item for item, _, _ in measured]), observation), "", True


def consistency_sample(history: list[Appearance], relative_impact: Callable[[Appearance], float]) -> Sample | None:
    rounds = sum(item.rounds for item in history)
    if len(history) < 3 or rounds < 90:
        return None
    spread = pstdev(relative_impact(item) for item in history)
    return Sample(-spread, len(history), role_shares(history), f"{spread:.2f} role-adjusted impact spread · {len(history)} series")


def flexibility_sample(history: list[Appearance], relative_impact: Callable[[Appearance], float]) -> Sample | None:
    rounds = sum(item.rounds for item in history)
    if len(history) < 3 or rounds < 90 or not role_shares(history):
        return None
    picks = Counter(agent for item in history for agent in item.row.agents)
    repeated = sum(count >= 2 for count in picks.values())
    qualified = 0
    for role in ROLE_WEIGHTS:
        evidence = [item for item in history if set(item.role_mix) == {role}]
        role_rounds = sum(item.rounds for item in evidence)
        if len(evidence) >= 2 and role_rounds >= 50:
            impact = sum(relative_impact(item) * item.rounds for item in evidence) / role_rounds
            qualified += impact >= -1
    pick_label = "pick" if repeated == 1 else "picks"
    role_label = "role" if qualified == 1 else "roles"
    observation = f"{repeated} repeat agent {pick_label} · {qualified} {role_label} with sustained evidence"
    return Sample(qualified + 0.25 * repeated, len(history), role_shares(history), observation)


def grade(sample: Sample, peers: list[Sample], prior: int, floor: float, score_scale: Callable[[float], float]) -> int:
    # A pooled component prevents a small role cohort from dominating the local comparison.
    weighted = [
        (peer.value, 0.25 + sum(fraction * peer.roles[role] for role, fraction in sample.roles.items()))
        for peer in peers
    ]
    weight = sum(amount for _, amount in weighted)
    center = sum(value * amount for value, amount in weighted) / weight
    scale = max(floor, sqrt(sum(amount * (value - center) ** 2 for value, amount in weighted) / weight))
    signal = (sample.value - center) / scale * sample.exposure / (sample.exposure + prior)
    return round(score_scale(signal))


def skill_facets(
    player_id: str,
    groups: dict[str, list[Appearance]],
    role_history: list[Appearance],
    relative_impact: Callable[[Appearance], float],
    score_scale: Callable[[float], float],
) -> list[dict]:
    weights = role_weights(role_history)
    output = []
    selected = groups.get(player_id, [])
    for code, label in FACET_LABELS.items():
        if code in RATES:
            rate = RATES[code]
            sample, note, measured = rate_sample(selected, rate)
            peers = [result for rows in groups.values() if (result := rate_sample(rows, rate)[0])]
            if code == "AIM" and (sample is None or len(peers) < MIN_COMPARABLE_PLAYERS):
                rate = AIM_PROXY
                sample, note, measured = rate_sample(selected, rate)
                peers = [result for rows in groups.values() if (result := rate_sample(rows, rate)[0])]
            prior, floor, proxy = rate.prior, rate.scale_floor, rate.proxy
            if not selected:
                note = "No recorded group appearances."
            status = "insufficient" if measured or not selected else "unavailable"
        else:
            measure = consistency_sample if code == "CONS" else flexibility_sample
            sample = measure(selected, relative_impact)
            peers = [result for rows in groups.values() if (result := measure(rows, relative_impact))]
            note = "Needs at least 3 covered series and 90 rounds."
            prior, floor, proxy, status = 4, 0.20, False, "insufficient"
        value = None
        if sample:
            if len(peers) >= MIN_COMPARABLE_PLAYERS:
                value = grade(sample, peers, prior, floor, score_scale)
                status = "proxy" if proxy else "provisional"
                note = sample.evidence
            else:
                status = "insufficient"
                note = f"{sample.evidence}. Needs more comparable players."
        output.append({
            "id": code, "label": label, "score": value, "status": status,
            "evidence": note, "role_weight": weights.get(code),
        })
    return output
