import { useEffect, useRef, useState } from 'react'
import {
  ArrowLeft, ArrowRight, CalendarDays, ChevronRight, Database, Download, FileCheck2, FlaskConical, GitBranch,
  Globe2, Layers3, ListOrdered, Radio, Search, ShieldCheck, Upload, Users2,
} from 'lucide-react'
import { errorText, request } from './api'
import type { Envelope, EventCard, Meta, Revision, Snapshot, Standing } from './types'
import { dateLabel, Empty, ErrorBox, FixtureRow, Notice, Pill, Sandbox, signed, TeamLabel } from './ui'

export function Dashboard({ event, standings, onMatch, onGroup, onBracket, onMatches, onSource, onEvents, onRoster }: {
  event: Snapshot; standings: Standing[]; onMatch: (id: string) => void
  onGroup: () => void; onBracket: () => void; onMatches: () => void; onSource: () => void; onEvents: () => void; onRoster: (team: string) => void
}) {
  const scheduled = event.fixtures.filter((match) => match.status === 'scheduled')
  const days = [...new Set(scheduled.map((match) => match.date))].sort()
  const [day, setDay] = useState(days[0] ?? '')
  const dayRows = scheduled.filter((match) => match.date === day)
  const slots = event.rules.qualification_slots
  return <>
    <button className="breadcrumb back-link" onClick={onEvents}><ArrowLeft size={13} /> Events</button>
    <section className="hero">
      <div className="hero-contours" aria-hidden="true"><i /><i /><i /><i /><b /><b /><b /></div>
      <div className="hero-main">
        <div className="hero-tags">
          <Pill tone="mint"><span className="status-dot" /> {event.stage}</Pill>
          <span className="hero-region"><Globe2 size={14} /> {event.region}</span>
        </div>
        <h1>{event.title}</h1>
        <p>Explore the standings and simulate the remaining matches.</p>
        <div className="hero-actions">
          {scheduled.length > 0 && <button className="button primary" onClick={onGroup}><FlaskConical size={16} /> Simulate group <ArrowRight size={15} /></button>}
          {event.bracket && <button className={'button ' + (scheduled.length ? 'secondary' : 'primary')} onClick={onBracket}><GitBranch size={16} /> Simulate bracket</button>}
          <button className="button secondary" onClick={onSource}><Database size={15} /> View source</button>
        </div>
      </div>
      <div className="hero-reference"><Database size={15} /><div><span>{event.source.verification === 'verified' ? 'Verified snapshot' : event.source.permission === 'fictional_demo' ? 'Fictional demo' : event.source.permission === 'user_supplied' ? 'User-supplied snapshot' : 'Source snapshot'}</span><strong>{dateLabel(event.source.observed_on, { year: 'numeric' })}</strong></div></div>
    </section>
    <div className="stats-strip" aria-label="Event summary">
      <Stat icon={<Users2 size={18} />} label="Teams" value={event.teams.length} />
      <Stat icon={<CalendarDays size={18} />} label="Remaining matches" value={scheduled.length} />
      <Stat icon={<Layers3 size={18} />} label={event.rules.verification === 'verified' ? 'Advancement slots' : 'Sandbox top spots'} value={slots || '—'} />
      <Stat icon={<ShieldCheck size={18} />} label="Recorded series" value={standings.reduce((total, team) => total + team.wins, 0)} />
    </div>
    <div className="overview-grid">
      <section className="panel compact-panel">
        <header className="panel-heading"><div><h2><ListOrdered size={19} /> Group standings</h2><p>Recorded results through {dateLabel(event.source.observed_on)}</p></div>
          <Pill tone="blue">{event.source.permission === 'fictional_demo' ? 'Sample results' : 'Observed snapshot'}</Pill>
        </header>
        <div className="table-scroll">
          <table className="standings">
            <thead><tr><th scope="col">Rank</th><th scope="col">Team</th><th scope="col">W–L</th><th scope="col">Maps</th><th scope="col">Diff</th><th scope="col">Rounds</th></tr></thead>
            <tbody>{standings.map((team) => {
              const diff = team.map_wins - team.map_losses
              return <tr key={team.team}>
                <td className="rank-cell">{team.rank}{team.tied && <span title="Unresolved tie">=</span>}</td>
                <th scope="row"><button className="team-roster-link" onClick={() => onRoster(team.team)} aria-label={'View ' + team.team + ' roster'}><TeamLabel code={team.team} name={team.name} /></button></th>
                <td className="record-cell">{team.wins}–{team.losses}</td>
                <td>{team.map_wins}–{team.map_losses}</td>
                <td className={diff > 0 ? 'positive' : diff < 0 ? 'negative' : 'text-muted'}>{signed(diff)}</td>
                <td>{team.round_wins === null ? '—' : team.round_wins + '–' + team.round_losses}</td>
              </tr>
            })}</tbody>
          </table>
        </div>
        <footer className="panel-footer"><span>Displayed by {event.rules.rank_by.map(criterionLabel).join(', ') || 'shared rank'}. Equal records share a rank.</span>
          {event.rules.verification === 'illustrative' && <Sandbox />}
        </footer>
      </section>
      <div className="overview-side">
        <section className="panel compact-panel">
          <header className="panel-heading"><div><h2><CalendarDays size={18} /> Upcoming matches</h2><p>Choose a fixture to preview its veto and odds.</p></div></header>
          {days.length ? <>
            <div className="day-tabs" aria-label="Fixture date">{days.map((item) =>
              <button key={item} className={day === item ? 'active' : ''} onClick={() => setDay(item)} aria-pressed={day === item}>
                {dateLabel(item)}
              </button>
            )}</div>
            <div className="fixture-list">{dayRows.map((fixture) => <FixtureRow key={fixture.id} fixture={fixture} teams={event.teams} onSelect={onMatch} />)}</div>
          </> : <Empty title="Schedule complete">This snapshot has no scheduled fixtures.</Empty>}
          <button className="panel-footer footer-button" onClick={onMatches}>Full schedule <ArrowRight size={15} /></button>
        </section>
        <section className="mini-feature">
          <div className="feature-icon"><FlaskConical size={22} /></div>
          <div><h3>Group forecast</h3><p>Run 10,000 draws to see placement ranges, top-{slots || 'N'} odds and unresolved ties.</p>
          <button className="text-button" onClick={onGroup} disabled={!scheduled.length}>Open simulation lab <ArrowRight size={14} /></button></div>
        </section>
      </div>
    </div>
  </>
}

function Stat({ icon, label, value }: { icon: React.ReactNode; label: string; value: number | string }) {
  return <div className="event-stat"><span className="stat-icon">{icon}</span><div><strong>{value}</strong><span>{label}</span></div></div>
}

export const criterionLabel = (criterion: string) => ({
  wins: 'series wins', map_diff: 'map difference', round_diff: 'round difference', head_to_head: 'head-to-head wins',
}[criterion] ?? criterion)

export function Schedule({ event, onMatch }: { event: Snapshot; onMatch: (id: string) => void }) {
  const [filter, setFilter] = useState('all')
  const fixtures = event.fixtures.filter((match) => filter === 'all' || match.status === filter)
  const days = [...new Set(fixtures.map((match) => match.date))].sort()
  return <>
    <PageTitle title="Match schedule" subtitle={event.title + ' · ' + event.stage} />
    <div className="toolbar">
      <label>Match status<select value={filter} onChange={(ev) => setFilter(ev.target.value)}>
        <option value="all">All matches</option><option value="scheduled">Scheduled</option>
        <option value="completed">Completed</option><option value="ongoing">In progress</option>
      </select></label>
    </div>
    {!days.length && <Empty title="No matches in this view">The source provides aggregate standings for older series. Individual results appear here when included in a snapshot.</Empty>}
    <div className="schedule-grid">{days.map((date) =>
      <section className="panel compact-panel" key={date}>
        <header className="panel-heading"><div><h2><CalendarDays size={18} /> {dateLabel(date, { weekday: 'long' })}</h2></div></header>
        <div className="fixture-list">{fixtures.filter((match) => match.date === date).map((fixture) =>
          <div key={fixture.id}>
            <FixtureRow fixture={fixture} teams={event.teams} onSelect={onMatch} />
            {fixture.scheduled_at && <small className="fixture-time">{new Date(fixture.scheduled_at).toLocaleString()}</small>}
          </div>
        )}</div>
      </section>
    )}</div>
    <Notice>Fixture dates follow the source display. Local start times appear only where the input includes a timestamp with a timezone.</Notice>
  </>
}

export function Events({ events, onOpen }: { events: Envelope<EventCard>[]; onOpen: (id: string) => void }) {
  const [search, setSearch] = useState('')
  const [region, setRegion] = useState('')
  const [tier, setTier] = useState('')
  const [status, setStatus] = useState('')
  const filtered = events.filter(({ data }) => (!region || data.region === region)
    && (!tier || data.tier === tier) && (!status || data.status === status)
    && (data.title + ' ' + data.stage).toLowerCase().includes(search.trim().toLowerCase()))
  const regions = [...new Set(events.map(({ data }) => data.region))]
  const tiers = [...new Set(events.flatMap(({ data }) => data.tier ? [data.tier] : []))]
  return <>
    <PageTitle title="Events" subtitle="Browse available tournament snapshots." />
    <div className="toolbar event-filters">
      <label>Search<div className="search-input"><Search size={17} /><input placeholder="Tournament or stage" value={search} onChange={(ev) => setSearch(ev.target.value)} /></div></label>
      <label>Status<select value={status} onChange={(ev) => setStatus(ev.target.value)}><option value="">All statuses</option>
        <option value="ongoing">Ongoing</option><option value="upcoming">Upcoming</option><option value="finished">Finished</option>
      </select></label>
      <label>Region<select value={region} onChange={(ev) => setRegion(ev.target.value)}><option value="">All regions</option>{regions.map((row) => <option key={row}>{row}</option>)}</select></label>
      {tiers.length > 0 && <label>Tier<select value={tier} onChange={(ev) => setTier(ev.target.value)}><option value="">All tiers</option>{tiers.map((row) => <option key={row}>{row}</option>)}</select></label>}
    </div>
    {!filtered.length && <Empty title="No matching events">Change the filters or import a snapshot under Data sources.</Empty>}
    <div className="schedule-grid">{filtered.map(({ data, meta }) =>
      <button className="panel event-card" key={data.event_id} onClick={() => onOpen(data.event_id)}>
        <div className="event-card-top"><Pill tone="mint">{data.stage}</Pill><span>{data.region}</span></div>
        <h2>{data.title}</h2><p>{data.team_count} teams · {data.remaining} scheduled · {data.status}</p>
        <footer><span><Database size={14} /> {dateLabel(meta.source.observed_on)}</span><ChevronRight size={19} /></footer>
      </button>
    )}</div>
  </>
}

export function PageTitle({ title, subtitle }: { title: string; subtitle: string }) {
  return <header className="page-title"><h1>{title}</h1><p>{subtitle}</p></header>
}

export function SourceView({ event, meta, onImport, onRevision, onPlayers }: {
  event: Snapshot; meta: Meta; onImport: (eventId: string, revision: string) => void; onRevision: (revision: string) => void; onPlayers: () => void
}) {
  const [file, setFile] = useState<File | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const [loading, setLoading] = useState(false)
  const [revisions, setRevisions] = useState<Revision[]>([])
  const [revisionError, setRevisionError] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    setRevisionError('')
    request<Revision[]>('/v1/events/' + event.event_id + '/revisions')
      .then(({ data }) => { if (active) setRevisions(data) })
      .catch((failure) => { if (active) setRevisionError(errorText(failure)) })
    return () => { active = false }
  }, [event.event_id, event.id])
  async function importSnapshot() {
    if (!file || loading) return
    setError('')
    setMessage('')
    if (file.size > 1_000_000) { setError('Choose a snapshot smaller than 1 MB.'); return }
    setLoading(true)
    try {
      const payload = JSON.parse(await file.text())
      const response = await request<{ event_id: string; snapshot_id: string }>('/v1/imports', payload)
      setMessage('Imported ' + response.data.snapshot_id)
      setFile(null)
      if (fileInput.current) fileInput.current.value = ''
      onImport(response.data.event_id, response.data.snapshot_id)
    } catch (failure) {
      setError(errorText(failure))
    } finally {
      setLoading(false)
    }
  }
  return <>
    <PageTitle title="Data sources" subtitle="Inspect event provenance, rules and revision history." />
    <div className="source-grid">
      <section className="panel">
        <header className="panel-heading"><div><h2><Database size={19} /> Source record</h2><p>{event.title} · {event.stage}</p></div>
          <Pill tone={meta.source.verification === 'verified' ? 'mint' : 'amber'}>{meta.source.verification === 'verified' ? 'Verified' : 'Unverified'}</Pill>
        </header>
        <dl className="source-list">
          <dt>Provider</dt><dd>{meta.source.provider}</dd>
          <dt>Reference</dt><dd>{meta.source.reference}</dd>
          <dt>Observed date</dt><dd>{dateLabel(meta.source.observed_on, { year: 'numeric' })}</dd>
          {meta.source.observed_at && <><dt>Observed timestamp</dt><dd>{new Date(meta.source.observed_at).toLocaleString()}</dd></>}
          <dt>Permission</dt><dd>{meta.source.permission === 'permissioned' ? meta.source.license : meta.source.permission === 'fictional_demo' ? 'Original fictional demo' : meta.source.permission === 'user_supplied' ? 'User supplied' : 'Public reference · manual transcription'}</dd>
          <dt>Method</dt><dd>{meta.source.method === 'manual' ? 'Manual transcription' : 'Authorized export'}</dd>
          <dt>Snapshot revision</dt><dd className="mono">{meta.snapshot_id}</dd>
          <dt>Input hash</dt><dd className="mono hash">{meta.input_hash}</dd>
        </dl>
        {meta.source.notes && <div className="section-pad"><Notice>{meta.source.notes}</Notice></div>}
      </section>
      <section className="panel">
        <header className="panel-heading"><div><h2><FileCheck2 size={19} /> Competition rules</h2><p>{event.rules.version}</p></div>{event.rules.verification === 'illustrative' && <Sandbox />}</header>
        <dl className="source-list">
          <dt>Ranking criteria</dt><dd>{event.rules.rank_by.map(criterionLabel).join(' → ') || 'Shared rank'}</dd>
          <dt>Advancement places</dt><dd>{event.rules.qualification_slots}</dd>
          <dt>Map pool</dt><dd>{event.rules.map_pool.join(', ')}</dd>
          {event.rules.reference && <><dt>Source reference</dt><dd>{event.rules.reference}</dd></>}
        </dl>
        {event.rules.notes && <div className="section-pad"><Notice>{event.rules.notes}</Notice></div>}
        <div className="section-pad"><div className="source-callout"><Radio size={17} />
          <div>Event standings use an imported snapshot. <button className="text-button" onClick={onPlayers}>Browse player sources <ArrowRight size={13} /></button></div>
        </div></div>
      </section>
      <section className="panel">
        <header className="panel-heading"><div><h2><Upload size={19} /> Import a snapshot</h2><p>Upload a JSON snapshot or a JSON envelope containing CSV tables.</p></div></header>
        <div className="section-pad import-form">
          <label>Snapshot file<input type="file" ref={fileInput} accept=".json,application/json" onChange={(ev) => setFile(ev.target.files?.[0] ?? null)} /></label>
          <div className="inline-actions">
            <button className="button primary" disabled={!file || loading} onClick={importSnapshot}><Upload size={15} /> {loading ? 'Importing…' : 'Validate and import'}</button>
            <a className="button secondary" href={'/v1/events/' + event.event_id + '?snapshot_id=' + event.id} onClick={(ev) => {
              ev.preventDefault()
              const { veto_orders: _orders, ...snapshot } = event
              const url = URL.createObjectURL(new Blob([JSON.stringify(snapshot, null, 2)], { type: 'application/json' }))
              const link = document.createElement('a')
              link.href = url
              link.download = event.id + '.json'
              link.click()
              window.setTimeout(() => URL.revokeObjectURL(url), 1000)
            }}><Download size={15} /> Download example</a>
          </div>
          {message && <div role="status" className="positive">{message}</div>}
          {error && <ErrorBox message={error} />}
        </div>
      </section>
      <section className="panel">
        <header className="panel-heading"><div><h2><Layers3 size={19} /> Snapshot history</h2><p>Open a revision to replay its observed inputs.</p></div></header>
        <div className="section-pad revision-list">{revisionError && <ErrorBox message={revisionError} />}{revisions.map((revision) =>
          <button key={revision.id} className="revision-row" onClick={() => onRevision(revision.id)}>
            <span><strong>{revision.id}</strong><small>{dateLabel(revision.observed_on, { year: 'numeric' })}</small></span>
            {revision.id === event.id ? <Pill tone="mint">Open</Pill> : <ChevronRight size={16} />}
          </button>
        )}</div>
      </section>
    </div>
  </>
}
