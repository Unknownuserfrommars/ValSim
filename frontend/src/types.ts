export type Source = {
  provider: string
  reference: string
  observed_on: string
  observed_at: string | null
  method: 'manual' | 'authorized_export'
  permission: 'user_supplied' | 'public_reference' | 'permissioned' | 'fictional_demo'
  verification: 'unverified' | 'verified'
  license: string | null
  notes: string
}
export type Meta = { model_version: string; schema_version: number; snapshot_id: string; input_hash: string; source: Source }
export type Envelope<T> = { meta: Meta; data: T }
export type BestOf = 1 | 3 | 5
export type Score = [number, number]
export type Fixture = {
  id: string; team_a: string; team_b: string; date: string; scheduled_at: string | null
  status: 'scheduled' | 'ongoing' | 'completed'; best_of: BestOf; score: Score | null
}
export type Team = {
  id: string; name: string; wins: number; losses: number; map_wins: number; map_losses: number
  round_wins: number | null; round_losses: number | null
}
export type Standing = Omit<Team, 'id'> & { team: string; rank: number; tied: boolean }
export type Step = { actor: 'A' | 'B'; action: 'ban' | 'pick' }
export type Rules = {
  version: string; verification: 'verified' | 'illustrative'; reference: string | null
  qualification_slots: number; rank_by: string[]; map_pool: string[]; notes: string
}
export type Bracket = {
  title: string; final: string; nodes: { id: string; best_of: BestOf; observed: Fixture | null }[]
}
export type Snapshot = {
  id: string; event_id: string; title: string; stage: string; region: string; status: string; tier: string | null
  source: Source; rules: Rules; teams: Team[]; fixtures: Fixture[]
  veto_orders: Partial<Record<BestOf, Step[]>>; bracket: Bracket | null
}
export type EventCard = Pick<Snapshot, 'event_id' | 'title' | 'stage' | 'region' | 'tier' | 'status'> &
  { team_count: number; remaining: number }
export type Revision = { id: string; input_hash: string; observed_on: string; received_at_utc: string }
export type Condition = { fixture_id: string; winner?: 'A' | 'B'; score?: Score; veto?: string[] }
export type Scope = 'match' | 'remaining_group' | 'bracket'
export type Scenario = { snapshot_id: string; scope: Scope; fixture_id?: string; seed: number; iterations: number; conditions: Condition[] }
export type Outcome = { probability: number; sampling_95: [number, number] }
export type Bounds = {
  lower: number; upper: number; unresolved: number; sampling_95: [number, number]; model_sensitivity: [number, number]
}
export type GroupTeam = {
  team: string; qualification: Bounds; ranks: number[]; unresolved_placement: number
  map_differential: Record<string, number>; series_wins: Record<string, number>
}
export type GroupOutput = {
  teams: GroupTeam[]; qualification_slots: number; qualification_verified: boolean
  rank_allocation: string; fixture_count: number; locked_fixture_count: number; baseline_series_count: number; observed_series_count: number
}
export type VetoAction = { actor: string; action: string; map: string; frequency: number }
export type MatchOutput = {
  fixture_id: string; team_a: string; team_b: string; wins: Record<string, Outcome>
  exact_win_a: number; model_sensitivity_a: [number, number]; scores: (Outcome & { score: Score })[]
  veto: VetoAction[]; veto_paths: { actions: VetoAction[]; probability: number }[]
  map_probabilities: { map: string; p_a: number; play_frequency: number }[]
}
export type BracketOutput = {
  title: string; final: string; champion: Record<string, Outcome>
  nodes: { id: string; locked: boolean; winner: Record<string, Outcome>; appearance: Record<string, number> }[]
}
export type Model = {
  version: string; calibration: string; parameters: {
    name: string; prior_maps: number; round_weight: number; map_scale: number; veto_temperature: number
  }[]; assumptions: string[]
}
export type CommonResult = { scenario: Scenario; model: Model; rules: Rules }
export type Result = CommonResult & (
  { scope: 'match'; output: MatchOutput } |
  { scope: 'remaining_group'; output: GroupOutput } |
  { scope: 'bracket'; output: BracketOutput }
)
export type Job = {
  id: string; status: 'queued' | 'running' | 'complete' | 'failed'; progress: number
  error: string | null; config: Scenario; result: Result | null
}
export type Comparison = { team: string; baseline: Bounds; conditioned: Bounds; change: [number, number] }
export type PlayerMeta = {
  player_data_id: string; player_input_hash: string; player_model_version: string; facet_model_version: string
  as_of: string; group_series_covered: number
  player_sources: { id: string; label: string; url: string; note: string }[]
}
export type PlayerRating = {
  ovr: number | null; form: number | null; current: number | null
  status: 'unrated' | 'limited' | 'established'
  baseline_rounds: number; baseline_series: number; latest_played_on: string | null
}
export type PlayerSummary = {
  id: string; handle: string; team: string; represented_region: string
  listed_as: 'player' | 'substitute'; aliases: string[]; team_role: string | null; profile_url: string | null
  primary_role: string | null; roles: string[]; role_evidence: string | null
  agents: { name: string; role: string | null; series: number }[]
  stats: {
    series: number; maps: number; rounds: number; kills: number; deaths: number; assists: number
    kd: number | null; kpr: number | null; apr: number | null
  }
  rating: PlayerRating
}
export type PlayerHistory = {
  id: string; played_on: string; event: string; played_for: string; opponent: string; score: Score; rounds: number
  maps: string[]; kills: number; deaths: number; assists: number; acs: number | null
  agents: string[]; provider_rating: number | null; impact: number; source_url: string
}
export type PlayerFacet = {
  id: 'AIM' | 'ENTRY' | 'UTIL' | 'CLUTCH' | 'IQ' | 'CONS' | 'FLEX'
  label: string
  score: number | null
  status: 'proxy' | 'provisional' | 'insufficient' | 'unavailable'
  evidence: string
  role_weight: number | null
}
export type PlayerProfile = PlayerSummary & {
  facets: PlayerFacet[]
  history: PlayerHistory[]; earlier_history: PlayerHistory[]
  model: { version: string; description: string; form: string; coverage: string; roles: string; facets: string }
}
export type View = 'overview' | 'events' | 'matches' | 'players' | 'simulations' | 'source'
