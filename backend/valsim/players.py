from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from functools import cached_property, lru_cache
from math import exp
from pathlib import Path
from statistics import pstdev
from typing import Annotated, Literal, Self

from pydantic import Field, HttpUrl, SerializerFunctionWrapHandler, model_serializer, model_validator

from .player_facets import FACET_MODEL, role_shares, skill_facets
from .schema import Count, Key, Label, Record, Snapshot
from .storage import canonical, digest


PLAYER_MODEL = "group-impact-v1.0.0"
Role = Literal["Duelist", "Initiator", "Controller", "Sentinel"]
MIN_PRIOR_ROUNDS = 60
RATING_PRIOR_ROUNDS = 90
FORM_PRIOR_ROUNDS = 60
FORM_LIMIT = 8
ASSIST_WEIGHT = 0.45
HALF_LIFE_DAYS = 45
PACK_DIR = Path(__file__).resolve().parents[2] / "data" / "player_snapshots"


class PlayerSource(Record):
    id: Key
    label: Label
    url: HttpUrl
    note: str


class Player(Record):
    id: Key
    handle: Label
    team: Key
    represented_region: Label
    listed_as: Literal["player", "substitute"]
    aliases: tuple[Label, ...] = ()
    team_role: Label | None = None
    profile_url: HttpUrl | None = None


class MapScore(Record):
    name: Label
    score: tuple[Count, Count]

    @model_validator(mode="after")
    def valid_score(self) -> Self:
        won, lost = max(self.score), min(self.score)
        if won < 13 or won > 99 or won - lost < 2 or (won > 13 and won - lost != 2):
            raise ValueError("Invalid regulation or overtime map score")
        return self


class SkillTelemetry(Record):
    aim_duels_won: Count | None = None
    aim_duel_attempts: Count | None = None
    first_kills: Count | None = None
    first_deaths: Count | None = None
    utility_assists: Count | None = None
    clutches_won: Count | None = None
    clutch_opportunities: Count | None = None
    trade_kills: Count | None = None
    trade_opportunities: Count | None = None

    @model_validator(mode="after")
    def validate_opportunities(self) -> Self:
        for wins, attempts in (
            (self.aim_duels_won, self.aim_duel_attempts),
            (self.clutches_won, self.clutch_opportunities),
            (self.trade_kills, self.trade_opportunities),
        ):
            if (wins is None) != (attempts is None) or (wins is not None and attempts is not None and wins > attempts):
                raise ValueError("Supply both successes and opportunities, with successes at most opportunities")
        if (self.first_kills is None) != (self.first_deaths is None):
            raise ValueError("Supply first kills and first deaths together")
        return self


class BoxScore(Record):
    player_id: Key
    played_for: Key | None = None
    kills: Count
    deaths: Count
    assists: Count
    agents: Annotated[tuple[Label, ...], Field(min_length=1, max_length=5)]
    acs: Count | None = None
    provider_rating: Annotated[float, Field(ge=0, le=10)] | None = None
    played_rounds: Annotated[int, Field(gt=0, le=500)] | None = None
    played_maps: Annotated[int, Field(gt=0, le=5)] | None = None
    skill_telemetry: SkillTelemetry | None = None

    @model_serializer(mode="wrap")
    def serialize(self, handler: SerializerFunctionWrapHandler) -> dict:
        fields = handler(self)
        if self.skill_telemetry is None:
            fields.pop("skill_telemetry", None)
        return fields


class Series(Record):
    id: Key
    played_on: date
    team_a: Key
    team_b: Key
    event: Label | None = None
    source_id: Key
    source_url: HttpUrl
    maps: Annotated[tuple[MapScore, ...], Field(min_length=1, max_length=5)]
    players: Annotated[tuple[BoxScore, ...], Field(min_length=1, max_length=24)]

    @cached_property
    def series_score(self) -> tuple[int, int]:
        won_a = sum(result.score[0] > result.score[1] for result in self.maps)
        return won_a, len(self.maps) - won_a

    @cached_property
    def round_score(self) -> tuple[int, int]:
        return sum(game.score[0] for game in self.maps), sum(game.score[1] for game in self.maps)

    @property
    def rounds(self) -> int:
        return sum(self.round_score)

    @model_validator(mode="after")
    def validate_series(self) -> Self:
        if self.team_a == self.team_b:
            raise ValueError("A player series requires two teams")
        if max(self.series_score) == min(self.series_score):
            raise ValueError("A completed series needs a winner")
        if len({game.name for game in self.maps}) != len(self.maps):
            raise ValueError("The same map cannot appear twice in a series")
        if len({row.player_id for row in self.players}) != len(self.players):
            raise ValueError("Duplicate player within a series")
        for row in self.players:
            if (row.played_rounds or self.rounds) > self.rounds or (row.played_maps or len(self.maps)) > len(self.maps):
                raise ValueError("Player exposure exceeds the series totals")
            if len(set(row.agents)) != len(row.agents) or len(row.agents) > (row.played_maps or len(self.maps)):
                raise ValueError("Player agent list has duplicates or exceeds the map sample")
            self.validate_telemetry(row)
        return self

    def validate_telemetry(self, row: BoxScore) -> None:
        details = row.skill_telemetry
        if details is None:
            return
        rounds = row.played_rounds or self.rounds
        if ((details.first_kills or 0) + (details.first_deaths or 0) > rounds
                or (details.first_kills or 0) > row.kills or (details.first_deaths or 0) > row.deaths
                or (details.utility_assists or 0) > row.assists or (details.trade_kills or 0) > row.kills
                or (details.clutch_opportunities or 0) > rounds):
            raise ValueError("Skill telemetry exceeds the series exposure or recorded box-score totals")


class PlayerPack(Record):
    id: Key
    event_id: Key
    observed_through: date
    agent_roles: dict[Label, Role] = Field(default_factory=dict, max_length=200)
    sources: tuple[PlayerSource, ...]
    roster: tuple[Player, ...]
    group_series: tuple[Series, ...]
    earlier_series: tuple[Series, ...]

    @cached_property
    def roster_by_id(self) -> dict[str, Player]:
        return {player.id: player for player in self.roster}

    @cached_property
    def input_hash(self) -> str:
        return digest(canonical(self.model_dump(mode="json")))

    @model_validator(mode="after")
    def validate_pack(self) -> Self:
        matches = self.group_series + self.earlier_series
        sources = {source.id for source in self.sources}
        if len(set(series.id for series in matches)) != len(matches) or len(self.roster_by_id) != len(self.roster):
            raise ValueError("Player and series IDs must be unique")
        if any(series.event is not None for series in self.group_series) or any(not series.event for series in self.earlier_series):
            raise ValueError("Earlier series require an event label")
        for series in matches:
            if series.source_id not in sources or series.played_on > self.observed_through:
                raise ValueError("Series needs a recorded source and date within the dataset")
            for row in series.players:
                player = self.roster_by_id.get(row.player_id)
                team = row.played_for or (player.team if player else None)
                if team not in (series.team_a, series.team_b) or not player or (series.event is None and team != player.team):
                    raise ValueError(f"Unknown player or team mismatch for {row.player_id} in {series.id}")
        return self


@lru_cache(maxsize=1)
def load_player_packs() -> dict[str, PlayerPack]:
    packs: dict[str, PlayerPack] = {}
    for path in sorted(PACK_DIR.glob("*.json")):
        pack = PlayerPack.model_validate_json(path.read_bytes())
        if pack.event_id in packs:
            raise ValueError(f"More than one player snapshot for event {pack.event_id}")
        packs[pack.event_id] = pack
    return packs


@dataclass(frozen=True, slots=True)
class Appearance:
    series: Series
    row: BoxScore
    agent_roles: dict[str, Role]

    @property
    def rounds(self) -> int:
        return self.row.played_rounds or self.series.rounds

    @property
    def maps(self) -> int:
        return self.row.played_maps or len(self.series.maps)

    @property
    def impact(self) -> float:
        return (self.row.kills - self.row.deaths + ASSIST_WEIGHT * self.row.assists) / self.rounds

    @property
    def role_mix(self) -> Counter[Role]:
        return Counter(self.agent_roles[agent] for agent in self.row.agents if agent in self.agent_roles)


def profile_model(stage: str) -> dict:
    return {
        "version": PLAYER_MODEL,
        "description": (
            f"OVR is a provisional 1–99 {stage} score. It compares each player's earlier {stage} series "
            "with the group by the roles observed in those series. Impact per round uses kills, deaths "
            "and assists. Small samples are pulled toward the group average."
        ),
        "form": (
            f"FORM compares the latest covered {stage} series with the earlier baseline. It is reduced "
            "for small samples and capped at ±8 points. Current is OVR plus FORM."
        ),
        "coverage": (
            f"Earlier events are shown as context. {stage} box scores supply K/D/A and agents. "
            "ACS and source ratings appear only where available. ValSim ratings are experimental."
        ),
        "facets": (
            "Facets compare the covered group series against players with similar agent roles on a provisional 1–99 scale. "
            "When aim-duel data is sparse, AIM uses kills per round as a proxy. IQ uses trade conversion where measured. "
            "CONS rewards less variation in role-adjusted impact. FLEX credits repeat agent picks and roles with adequate "
            "impact across at least two single-role series and 50 rounds. Role weights are the specification’s starting priors. "
            "OVR uses the separate group impact model."
        ),
        "roles": "Roles come from observed agent picks. Agent counts indicate series appearances, with one mention per agent per series.",
        "settings": {
            "assist_weight": ASSIST_WEIGHT, "baseline_half_life_days": HALF_LIFE_DAYS,
            "min_prior_series": 2, "min_prior_rounds": MIN_PRIOR_ROUNDS,
            "rating_prior_rounds": RATING_PRIOR_ROUNDS, "form_prior_rounds": FORM_PRIOR_ROUNDS,
            "form_max_points": FORM_LIMIT,
        },
    }


def as_rating(z_score: float) -> float:
    signal = max(-25, min(25, 0.86 + 0.80 * z_score))
    return 1 + 98 / (1 + exp(-signal))


def rate_basis(sample: list[Appearance]) -> bool:
    return len(sample) >= 2 and sum(item.rounds for item in sample) >= MIN_PRIOR_ROUNDS


def appearance_groups(series: tuple[Series, ...], as_of: date, agent_roles: dict[str, Role]) -> dict[str, list[Appearance]]:
    groups = defaultdict(list)
    for match in sorted(series, key=lambda item: (item.played_on, item.id)):
        if match.played_on <= as_of:
            for row in match.players:
                groups[row.player_id].append(Appearance(match, row, agent_roles))
    return groups


class RoleBenchmark:
    def __init__(self, group: dict[str, list[Appearance]]):
        sample = [item for history in group.values() if rate_basis(history[:-1]) for item in history[:-1]]
        total = sum(item.rounds for item in sample)
        center = sum(item.impact * item.rounds for item in sample) / total if total else 0
        self.center = center
        self.scale = max(0.16, pstdev(item.impact for item in sample)) if sample else 0.16
        weights: Counter[Role] = Counter()
        scores: Counter[Role] = Counter()
        for item in sample:
            mix = item.role_mix
            for role, count in mix.items():
                weight = item.rounds * count / mix.total()
                weights[role] += weight
                scores[role] += weight * item.impact
        self.role_center = {
            role: (scores[role] + 180 * center) / (weight + 180)
            for role, weight in weights.items()
        }

    def relative_impact(self, item: Appearance) -> float:
        mix = item.role_mix
        center = sum(self.role_center.get(role, self.center) * count for role, count in mix.items()) / mix.total() if mix else self.center
        return (item.impact - center) / self.scale


def rating(group_history: list[Appearance], benchmark: RoleBenchmark, as_of: date) -> dict:
    prior, latest = group_history[:-1], group_history[-1] if group_history else None
    rounds = sum(row.rounds for row in prior)
    if latest is None or not rate_basis(prior):
        return {
            "ovr": None, "form": None, "current": None, "status": "unrated",
            "baseline_rounds": rounds, "baseline_series": len(prior), "latest_played_on": latest.series.played_on if latest else None,
        }
    weights = [row.rounds * 2 ** (-(as_of - row.series.played_on).days / HALF_LIFE_DAYS) for row in prior]
    exposure = sum(weights)
    signal = sum(benchmark.relative_impact(row) * weight for row, weight in zip(prior, weights, strict=True))
    career_proxy = signal / (exposure + RATING_PRIOR_ROUNDS)
    overall = round(as_rating(career_proxy))
    latest_weight = latest.rounds / (latest.rounds + FORM_PRIOR_ROUNDS)
    difference = (as_rating(benchmark.relative_impact(latest)) - as_rating(career_proxy)) * latest_weight
    form = min(FORM_LIMIT, max(-FORM_LIMIT, round(difference))) if latest.rounds >= 25 else None
    return {
        "ovr": overall, "form": form, "current": min(99, max(1, overall + form)) if form is not None else None,
        "status": "limited" if rounds < 300 else "established",
        "baseline_rounds": rounds, "baseline_series": len(prior), "latest_played_on": latest.series.played_on,
    }


def player_roles(history: list[Appearance]) -> dict:
    agents = Counter(agent for item in history for agent in item.row.agents)
    agent_roles = history[0].agent_roles if history else {}
    roles = role_shares(history)
    ordered = sorted(roles, key=lambda role: (-roles[role], role))
    primary = ordered[0] if ordered and roles[ordered[0]] >= 0.6 else "Flex" if ordered else None
    return {
        "primary_role": primary,
        "roles": ordered,
        "agents": [{"name": name, "role": agent_roles.get(name), "series": count} for name, count in sorted(agents.items(), key=lambda item: (-item[1], item[0]))],
    }


def total_stats(history: list[Appearance]) -> dict:
    rounds = sum(row.rounds for row in history)
    kills = sum(item.row.kills for item in history)
    deaths = sum(item.row.deaths for item in history)
    assists = sum(item.row.assists for item in history)
    return {
        "series": len(history), "maps": sum(item.maps for item in history), "rounds": rounds,
        "kills": kills, "deaths": deaths, "assists": assists, "kd": kills / deaths if deaths else None,
        "kpr": kills / rounds if rounds else None, "apr": assists / rounds if rounds else None,
    }


def history_row(item: Appearance, team: str, group_label: str) -> dict:
    match = item.series
    represented_team = item.row.played_for or team
    side = int(match.team_b == represented_team)
    score = match.series_score
    return {
        "id": match.id, "played_on": match.played_on, "event": match.event or group_label,
        "played_for": represented_team, "opponent": match.team_a if side else match.team_b, "score": [score[side], score[1 - side]],
        "rounds": item.rounds, "maps": [game.name for game in match.maps],
        "kills": item.row.kills, "deaths": item.row.deaths, "assists": item.row.assists,
        "acs": item.row.acs, "provider_rating": item.row.provider_rating,
        "agents": item.row.agents, "impact": round(item.impact, 3),
        "source_url": str(match.source_url),
    }


class PlayerDirectory:
    def __init__(self, pack: PlayerPack, snapshot: Snapshot, requested: date | None):
        self.pack = pack
        self.stage = snapshot.stage
        self.group_label = f"{snapshot.title} · {snapshot.stage}"
        self.as_of = min(requested or snapshot.source.observed_on, snapshot.source.observed_on, pack.observed_through)
        self.groups = appearance_groups(pack.group_series, self.as_of, pack.agent_roles)
        self.prior = appearance_groups(pack.earlier_series, self.as_of, pack.agent_roles)
        self.benchmark = RoleBenchmark(self.groups)
        self.teams = {team.id for team in snapshot.teams}

    def meta(self) -> dict:
        return {
            "player_data_id": self.pack.id, "player_input_hash": self.pack.input_hash,
            "player_model_version": PLAYER_MODEL, "facet_model_version": FACET_MODEL, "as_of": self.as_of,
            "group_series_covered": sum(series.played_on <= self.as_of for series in self.pack.group_series),
            "player_sources": [source.model_dump(mode="json") for source in self.pack.sources],
        }

    def summary(self, player: Player) -> dict:
        group_history = self.groups.get(player.id, [])
        earlier_history = self.prior.get(player.id, [])
        return {
            **player.model_dump(mode="json"),
            **player_roles(group_history or earlier_history),
            "role_evidence": self.stage if group_history else "Earlier events" if earlier_history else None,
            "stats": total_stats(group_history),
            "rating": rating(group_history, self.benchmark, self.as_of),
        }

    def list(self) -> list[dict]:
        return [self.summary(player) for player in self.pack.roster if player.team in self.teams]

    def profile(self, player_id: str) -> dict | None:
        player = self.pack.roster_by_id.get(player_id)
        if player is None or player.team not in self.teams:
            return None
        role_history = self.groups.get(player_id) or self.prior.get(player_id, [])
        return {
            **self.summary(player),
            "facets": skill_facets(player_id, self.groups, role_history, self.benchmark.relative_impact, as_rating),
            "history": [history_row(item, player.team, self.group_label) for item in reversed(self.groups.get(player.id, []))],
            "earlier_history": [history_row(item, player.team, self.group_label) for item in reversed(self.prior.get(player.id, []))],
            "model": profile_model(self.stage),
        }


def player_directory(snapshot: Snapshot, as_of: date | None = None) -> PlayerDirectory | None:
    pack = load_player_packs().get(snapshot.event_id)
    return PlayerDirectory(pack, snapshot, as_of) if pack else None
