import { useState } from 'react'
import {
  ArrowRight, Ban, Binary, CalendarDays, ChartNoAxesCombined, ChevronDown, Download, FlaskConical,
  GitBranch, GitCompareArrows, Hash, ListOrdered, Play, ScanLine, Shuffle, Swords,
} from 'lucide-react'
import { errorText, request, simulate } from './api'
import { PageTitle } from './Dashboard'
import type {
  BracketOutput, Comparison, Condition, Envelope, GroupOutput, Job, MatchOutput, Model, Scenario,
  Scope, Score, Snapshot,
} from './types'
import { dateLabel, Empty, ErrorBox, Notice, number, percent, Pill, probabilityWidth, range, Sandbox, signedPoints, SimulationBadge, TeamMark } from './ui'

const defaultSeed = 20261118
const scopeTitles: Record<Scope, string> = { match: 'Single match', remaining_group: 'Remaining group', bracket: 'Knockout bracket' }

export function Studio({ event, scope, fixtureId, setScope, setFixture }: {
  event: Snapshot; scope: Scope; fixtureId: string; setScope: (scope: Scope) => void; setFixture: (id: string) => void
}) {
  const scheduled = event.fixtures.filter((item) => item.status === 'scheduled')
  const selected = scheduled.find((item) => item.id === fixtureId) || scheduled[0]
  const [iterations, setIterations] = useState(10_000)
  const [seed, setSeed] = useState(String(defaultSeed))
  const [manual, setManual] = useState(false)
  const [vetoMaps, setVetoMaps] = useState<string[]>([])
  const [conditionId, setConditionId] = useState('')
  const [conditionResult, setConditionResult] = useState('')
  const [working, setWorking] = useState(false)
  const [phase, setPhase] = useState('')
  const [job, setJob] = useState<Job | null>(null)
  const [completed, setCompleted] = useState<Envelope<Job> | null>(null)
  const [comparison, setComparison] = useState<Comparison[] | null>(null)
  const [error, setError] = useState('')
  const steps = selected ? event.veto_orders[selected.best_of] ?? [] : []
  const conditionalFixture = scheduled.find((item) => item.id === conditionId)
  const groupCompare = scope === 'remaining_group' && !!conditionId && !!conditionResult
  const manualReady = steps.every((_, i) => !!vetoMaps[i]) && vetoMaps.filter(Boolean).length === steps.length
  const remaining = event.rules.map_pool.filter((map) => !vetoMaps.includes(map))
  const current = completed?.data.result
  const canSimulate = (scope === 'match' ? !!selected && (!manual || manualReady)
    : scope === 'bracket' ? event.bracket?.nodes.some((node) => !node.observed)
    : scheduled.length > 0) && !working
  const scoped = (['remaining_group', 'match', ...(event.bracket ? ['bracket'] : [])] as Scope[])

  function resetVeto() { setVetoMaps([]); setManual(false) }

  async function launch() {
    if (!canSimulate) return
    const seedNumber = Number(seed)
    if (!/^[0-9]+$/.test(seed) || !Number.isSafeInteger(seedNumber)) {
      setError('Enter a whole nonnegative seed up to 9,007,199,254,740,991.')
      return
    }
    const config: Scenario = { snapshot_id: event.id, scope, iterations, seed: seedNumber, conditions: [] }
    if (scope === 'match' && selected) {
      config.fixture_id = selected.id
      if (manual) config.conditions.push({ fixture_id: selected.id, veto: [...vetoMaps] })
    }
    if (groupCompare) {
      const condition: Condition = { fixture_id: conditionId }
      if (conditionResult === 'A' || conditionResult === 'B') condition.winner = conditionResult
      else condition.score = conditionResult.split('-').map(Number) as Score
      config.conditions.push(condition)
    }
    setError('')
    setWorking(true)
    setJob(null)
    setComparison(null)
    setCompleted(null)
    try {
      let baseline: Envelope<Job> | undefined
      if (groupCompare) {
        setPhase('Baseline')
        baseline = await simulate({ ...config, conditions: [] }, setJob)
      }
      setPhase(groupCompare ? 'Conditioned forecast' : 'Simulation')
      setJob(null)
      const output = await simulate(config, setJob)
      setCompleted(output)
      if (baseline) {
        const diff = await request<Comparison[]>('/v1/simulations/' + baseline.data.id + '/compare', { conditioned_id: output.data.id })
        setComparison(diff.data)
      }
    } catch (failure) {
      setError(errorText(failure))
    } finally {
      setWorking(false)
    }
  }

  return <>
    <div className="studio-title"><PageTitle title="Simulation lab" subtitle={event.title + ' · ' + event.stage} /><SimulationBadge /></div>
    <div className="scope-tabs" aria-label="Simulation scope">{scoped.map((item) =>
      <button key={item} className={scope === item ? 'active' : ''} aria-pressed={scope === item} disabled={working}
        onClick={() => { setScope(item); setError(''); setCompleted(null); setComparison(null) }}>
        {item === 'match' ? <Swords size={17} /> : item === 'bracket' ? <GitBranch size={17} /> : <ListOrdered size={17} />}
        {scopeTitles[item]}
      </button>
    )}</div>
    <div className="studio-grid">
      <section className="panel settings" aria-label="Simulation setup">
        <header className="panel-heading"><div><h2><FlaskConical size={19} /> Run setup</h2><p>Use the same seed and snapshot to replay a run.</p></div></header>
        <div className="settings-body">
          {scope === 'match' && <label>Fixture<select value={selected?.id ?? ''} disabled={working || !scheduled.length} onChange={(ev) => {
            setFixture(ev.target.value); resetVeto(); setCompleted(null)
          }}>
            {!scheduled.length && <option>No scheduled matches</option>}
            {scheduled.map((match) => <option key={match.id} value={match.id}>{match.team_a} vs {match.team_b} · BO{match.best_of}</option>)}
          </select></label>}
          <div className="form-row"><label><span><Binary size={15} /> Draws</span><select value={iterations} disabled={working} onChange={(ev) => setIterations(Number(ev.target.value))}>
            {[1000, 10000, 100000].map((amount) => <option key={amount} value={amount}>{number(amount)}</option>)}
          </select></label><label><span><Hash size={15} /> Seed</span><input value={seed} disabled={working} onChange={(ev) => setSeed(ev.target.value)} inputMode="numeric" /></label></div>
          {scope === 'remaining_group' && <>
            <div className="setup-lock"><CalendarDays size={16} /> {scheduled.length} scheduled · recorded results locked</div>
            <label>What-if fixture<select value={conditionId} disabled={working} onChange={(ev) => { setConditionId(ev.target.value); setConditionResult('') }}>
              <option value="">None · baseline forecast</option>
              {scheduled.map((match) => <option key={match.id} value={match.id}>{match.team_a} vs {match.team_b}</option>)}
            </select></label>
            {conditionalFixture && <label>Force outcome<select value={conditionResult} disabled={working} onChange={(ev) => setConditionResult(ev.target.value)}>
              <option value="">Choose an outcome</option>
              <option value="A">{conditionalFixture.team_a} wins</option>
              <option value="B">{conditionalFixture.team_b} wins</option>
              {Array.from({ length: (conditionalFixture.best_of + 1) / 2 }, (_, i) => i).flatMap((other) => {
                const target = (conditionalFixture.best_of + 1) / 2
                return [<option key={target + '-' + other} value={target + '-' + other}>{conditionalFixture.team_a} wins {target}–{other}</option>,
                  <option key={other + '-' + target} value={other + '-' + target}>{conditionalFixture.team_b} wins {target}–{other}</option>]
              })}
            </select></label>}
            {groupCompare && <Notice>ValSim runs the baseline and your scenario with the same seed, then compares their advancement ranges.</Notice>}
          </>}
          {scope === 'match' && selected && <>
            <label>Veto mode<select disabled={working} value={manual ? 'manual' : 'weighted'} onChange={(ev) => setManual(ev.target.value === 'manual')}>
              <option value="weighted">Weighted veto</option><option value="manual">Manual veto</option>
            </select></label>
            {manual && <div className="manual-veto">
              {steps.map((step, i) => <label key={i}>
                <span>{step.action === 'ban' ? <Ban size={13} /> : <ScanLine size={13} />}{step.actor === 'A' ? selected.team_a : selected.team_b} {step.action}</span>
                <select aria-label={(step.actor === 'A' ? selected.team_a : selected.team_b) + ' ' + step.action + ' ' + (i + 1)}
                  disabled={working} value={vetoMaps[i] ?? ''} onChange={(ev) => {
                    const next = Array.from({ length: steps.length }, (_, j) => vetoMaps[j] ?? '')
                    next[i] = ev.target.value
                    setVetoMaps(next)
                  }}>
                  <option value="">Choose map</option>
                  {event.rules.map_pool.filter((map) => map === vetoMaps[i] || !vetoMaps.includes(map)).map((map) => <option key={map}>{map}</option>)}
                </select>
              </label>)}
              <div className="setup-lock"><Swords size={16} /> Decider <strong>{manualReady ? remaining[0] : 'Pending'}</strong></div>
            </div>}
          </>}
          <button className="button primary run-button" onClick={launch} disabled={!canSimulate || (!!conditionalFixture && scope === 'remaining_group' && !conditionResult)}>
            {groupCompare ? <GitCompareArrows size={16} /> : <Play size={16} />}
            {working ? 'Running…' : groupCompare ? 'Run and compare' : 'Run simulation'} <ArrowRight size={16} />
          </button>
          {working && <div className="progress-block" aria-live="polite"><span>{phase}</span><strong>{job?.progress ?? 0}%</strong><progress max={100} value={job?.progress ?? 0} /></div>}
          {error && <ErrorBox message={error} />}
          {event.rules.verification === 'illustrative' && <Sandbox />}
        </div>
      </section>
      <div className="studio-results">
        {!current && (
          scope === 'match' && selected ? <div className="panel">
            <header className="panel-heading"><div><h2><Swords size={19} /> Match preview</h2><p>Best of {selected.best_of}</p></div><Pill>Scheduled</Pill></header>
            <div className="match-preview"><TeamMark code={selected.team_a} size="large" /><div><strong>{selected.team_a}</strong><small>{event.teams.find((item) => item.id === selected.team_a)?.name}</small></div>
              <span>VS</span><div><strong>{selected.team_b}</strong><small>{event.teams.find((item) => item.id === selected.team_b)?.name}</small></div><TeamMark code={selected.team_b} size="large" />
            </div>
            <div className="section-pad"><Notice>{event.rules.verification === 'illustrative' ? 'This event uses an illustrative map pool and veto order.' : 'This event uses the imported competition rules.'} Run a simulation to see score odds and one replayable veto.</Notice></div>
          </div> :
          <div className="panel initial-results">
            <Empty title={scope === 'bracket' ? 'Forecast the knockout bracket' : 'Forecast the remaining group'}>
              {scope === 'bracket' ? 'See title probabilities and paths through the imported bracket.' : 'See top-spot odds, final rank distributions and unresolved ties across all teams.'}
            </Empty>
          </div>
        )}
        {completed && current && <>
          <div className="run-receipt"><span><small>{number(current.scenario.iterations)} draws · seed {current.scenario.seed} · data as of {dateLabel(completed.meta.source.observed_on)}</small></span>
            <a className="button secondary" href={'/v1/simulations/' + completed.data.id + '/export'}><Download size={15} /> Export</a>
          </div>
          {current.scope === 'match' && <MatchResults output={current.output} />}
          {current.scope === 'remaining_group' && <GroupResults key={completed.data.id} output={current.output} comparison={comparison} />}
          {current.scope === 'bracket' && <BracketResults output={current.output} />}
          <ModelDetails model={current.model} snapshot={completed.meta.snapshot_id} hash={completed.meta.input_hash} rules={current.rules.version} />
        </>}
      </div>
    </div>
  </>
}

function MatchResults({ output }: { output: MatchOutput }) {
  const a = output.wins[output.team_a]
  const b = output.wins[output.team_b]
  return <>
    <section className="panel">
      <header className="panel-heading"><div><h2><Swords size={19} /> Match forecast</h2><p>Simulated series win probability</p></div></header>
      <div className="section-pad forecast-pad">
        <div className="duel">
          <div><span>{output.team_a}</span><strong>{percent(a.probability)}</strong></div>
          <div><span>{output.team_b}</span><strong>{percent(b.probability)}</strong></div>
        </div>
        <div className="duel-line" aria-hidden="true"><i style={{ width: probabilityWidth(a.probability) }} /></div>
        <div className="interval-row"><span>95% sampling interval</span><strong>{range(...a.sampling_95)} · {range(...b.sampling_95)}</strong></div>
        <div className="interval-row"><span>{output.team_a} model sensitivity</span><strong>{range(...output.model_sensitivity_a)}</strong></div>
        <Chart title="Series score" rows={output.scores.map((row) => [row.score.join('–'), row.probability])} />
      </div>
    </section>
    <section className="panel">
      <header className="panel-heading"><div><h2><Shuffle size={19} /> Example veto</h2><p>One seeded path and the frequency of each map at that step.</p></div></header>
      <div className="section-pad veto-results">{output.veto.map((action, i) => <div key={i}>
        <span className="mono">{i + 1}</span><span>{action.actor === 'A' ? output.team_a + ' ' : action.actor === 'B' ? output.team_b + ' ' : ''}{action.action}</span>
        <strong>{action.map}</strong><span>{percent(action.frequency)}</span>
      </div>)}</div>
      <details className="details"><summary>Map odds and veto paths <ChevronDown size={16} /></summary>
        <div className="section-pad veto-results">
          <div><span /><strong>Map</strong><strong>{output.team_a} wins</strong><strong>Played</strong></div>
          {output.map_probabilities.map((map) => <div key={map.map}><span /><span>{map.map}</span><strong>{percent(map.p_a)}</strong><span>{percent(map.play_frequency)}</span></div>)}
          <h3>Most frequent full paths</h3>
          {output.veto_paths.map((path) => <p className="path" key={path.actions.map((action) => action.map).join('|')}>
            <strong>{percent(path.probability)}</strong> {path.actions.map((action) => action.map).join(' → ')}
          </p>)}
        </div>
      </details>
    </section>
  </>
}

function GroupResults({ output, comparison }: { output: GroupOutput; comparison: Comparison[] | null }) {
  const teams = [...output.teams].sort((a, b) => b.qualification.lower - a.qualification.lower)
  const [team, setTeam] = useState(teams[0].team)
  const focus = output.teams.find((row) => row.team === team)!
  const heading = output.qualification_slots === 0 ? 'Group forecast' : output.qualification_verified ? 'Qualification odds' : 'Sandbox top-' + output.qualification_slots + ' odds'
  return <>
    <section className="panel">
      <header className="panel-heading"><div><h2><ChartNoAxesCombined size={19} /> {heading}</h2>
        <p>{output.fixture_count} simulated fixtures · {output.observed_series_count ?? output.baseline_series_count} recorded series locked</p></div>
        {!output.qualification_verified && <Sandbox />}</header>
      <div className="table-scroll"><table className="probability-table">
        <thead><tr><th scope="col">Team</th><th scope="col">Advancement</th><th scope="col">Tie at cutoff</th><th scope="col">Model sensitivity</th></tr></thead>
        <tbody>{teams.map((row) => <tr key={row.team}><th scope="row"><button className="team-result" onClick={() => setTeam(row.team)}><TeamMark code={row.team} size="small" />{row.team}</button></th>
          <td className="advantage"><strong>{range(row.qualification.lower, row.qualification.upper)}</strong>
            <div className="indicator" aria-hidden="true"><i style={{ width: probabilityWidth(row.qualification.upper) }} /><b style={{ width: probabilityWidth(row.qualification.lower) }} /></div>
          </td><td>{percent(row.qualification.unresolved)}</td><td>{range(...row.qualification.model_sensitivity)}</td>
        </tr>)}</tbody>
      </table></div>
      <div className="panel-footer">{output.qualification_verified ? 'Ranges allow all placements within an unresolved tie.' : 'Provisional advancement under the displayed rules. Ranges include unresolved ties at the cutoff.'}</div>
    </section>
    {comparison && <section className="panel">
      <header className="panel-heading"><div><h2><GitCompareArrows size={19} /> What-if comparison</h2><p>Change in advancement odds, in percentage points.</p></div></header>
      <div className="table-scroll"><table className="probability-table">
        <thead><tr><th scope="col">Team</th><th scope="col">Baseline</th><th scope="col">Conditioned</th><th scope="col">Change</th></tr></thead>
        <tbody>{comparison.map((row) => <tr key={row.team}><th scope="row">{row.team}</th>
          <td>{range(row.baseline.lower, row.baseline.upper)}</td><td>{range(row.conditioned.lower, row.conditioned.upper)}</td>
          <td className={row.change[0] > 0 ? 'positive' : row.change[1] < 0 ? 'negative' : ''}>
            {signedPoints(row.change[0])}{Math.abs(row.change[1] - row.change[0]) > 0.00001 && ' to ' + signedPoints(row.change[1])}
          </td></tr>)}</tbody>
      </table></div>
    </section>}
    <section className="panel">
      <header className="panel-heading"><div><h2><ListOrdered size={19} /> Placement distribution</h2><p>Final ranks under the configured rules.</p></div>
        <label className="compact-field"><span className="sr-only">Placement team</span><select value={team} onChange={(ev) => setTeam(ev.target.value)}>{teams.map((row) => <option key={row.team}>{row.team}</option>)}</select></label>
      </header>
      <div className="section-pad">
        <Chart title={team + ' rank distribution'} rows={focus.ranks.map((probability, i) => [String(i + 1), probability])} />
        <div className="interval-row"><span>Unresolved rank</span><strong>{percent(focus.unresolved_placement)}</strong></div>
        <div className="interval-row"><span>Advancement 95% sampling envelope</span><strong>{range(...focus.qualification.sampling_95)}</strong></div>
        <p className="secondary-text">{output.rank_allocation}</p>
      </div>
      <details className="details"><summary>Map difference and series wins <ChevronDown size={16} /></summary><div className="section-pad detail-charts">
        <Chart title="Final map difference" rows={Object.entries(focus.map_differential).sort(([a], [b]) => Number(a) - Number(b))} />
        <Chart title="Final series wins" rows={Object.entries(focus.series_wins)} />
      </div></details>
    </section>
  </>
}

function Chart({ title, rows }: { title: string; rows: [string, number][] }) {
  return <div className="distribution" aria-label={title}><h3>{title}</h3>{rows.map(([label, value]) =>
    <div className="bar-row" key={label}><strong>{label}</strong><div className="bar" aria-hidden="true"><i style={{ width: probabilityWidth(value) }} /></div><span>{percent(value)}</span></div>
  )}</div>
}

function BracketResults({ output }: { output: BracketOutput }) {
  return <section className="panel">
    <header className="panel-heading"><div><h2><GitBranch size={19} /> {output.title}</h2><p>Final node · {output.final}</p></div></header>
    <div className="section-pad"><Chart title="Title odds" rows={Object.entries(output.champion).sort(([, a], [, b]) => b.probability - a.probability).map(([team, row]) => [team, row.probability])} /></div>
    {output.nodes.map((node) => <details className="details" key={node.id}><summary>{node.id} {node.locked && '(recorded result)'} <ChevronDown size={16} /></summary>
      <div className="section-pad detail-charts">
        <Chart title="Winner" rows={Object.entries(node.winner).map(([team, row]) => [team, row.probability])} />
        <Chart title="Appears at node" rows={Object.entries(node.appearance)} />
      </div>
    </details>)}
  </section>
}

function ModelDetails({ model, snapshot, hash, rules }: { model: Model; snapshot: string; hash: string; rules: string }) {
  return <details className="panel details model-details">
    <summary><span><FlaskConical size={17} /> Model and replay details</span><ChevronDown size={16} /></summary>
    <div className="section-pad">
      <dl className="source-list flush">
        <dt>Model</dt><dd>{model.version}</dd><dt>Validation</dt><dd>{model.calibration}</dd>
        <dt>Snapshot</dt><dd>{snapshot}</dd><dt>Rules</dt><dd>{rules}</dd><dt>Input hash</dt><dd className="mono hash">{hash}</dd>
      </dl>
      <ul>{model.assumptions.map((item) => <li key={item}>{item}</li>)}</ul>
      <div className="table-scroll"><table><thead><tr><th>Setting</th><th>Prior maps</th><th>Round weight</th><th>Map scale</th><th>Veto temperature</th></tr></thead>
        <tbody>{model.parameters.map((item) => <tr key={item.name}><th>{item.name}</th><td>{item.prior_maps}</td><td>{item.round_weight}</td><td>{item.map_scale}</td><td>{item.veto_temperature}</td></tr>)}</tbody>
      </table></div>
    </div>
  </details>
}
