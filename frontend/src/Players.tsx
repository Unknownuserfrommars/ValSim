import { useEffect, useState } from 'react'
import {
  Activity, ArrowDownRight, ArrowLeft, ArrowRight, ArrowUpRight, BadgeCheck, Crosshair, Database, Gauge,
  History, ScanSearch, Shield, Swords, Users2,
} from 'lucide-react'
import { errorText, request } from './api'
import { PageTitle } from './Dashboard'
import type { Envelope, Meta, PlayerFacet, PlayerHistory, PlayerMeta, PlayerProfile, PlayerSummary, Snapshot } from './types'
import { dateLabel, Empty, ErrorBox, Notice, number, Pill, signed, TeamMark } from './ui'

const roleStyle: Record<string, string> = {
  Duelist: 'duelist', Initiator: 'initiator', Controller: 'controller', Sentinel: 'sentinel', Flex: 'flex',
}

function RoleBadge({ role }: { role: string | null }) {
  return role ? <span className={'role-chip ' + (roleStyle[role] ?? '')}>{role}</span> : <span className="text-muted">Unknown</span>
}

const displayNumber = (value: number | null) => value === null ? '—' : value.toFixed(2)
const displayForm = (value: number | null) => value === null ? '—' : signed(value)

export function PlayersView({ event, selected, onSelect, team, onTeam }: {
  event: Snapshot; selected: string; onSelect: (id: string) => void; team: string; onTeam: (team: string) => void
}) {
  const [directory, setDirectory] = useState<Envelope<PlayerSummary[]> | null>(null)
  const [profile, setProfile] = useState<Envelope<PlayerProfile> | null>(null)
  const [listError, setListError] = useState('')
  const [profileError, setProfileError] = useState('')
  const [filter, setFilter] = useState('')
  const [role, setRole] = useState('')
  const [order, setOrder] = useState('current')
  const base = '/v1/events/' + event.event_id + '/players'
  const params = '?snapshot_id=' + event.id

  useEffect(() => {
    let active = true
    request<PlayerSummary[]>(base + params).then((response) => {
      if (active) setDirectory(response)
    }).catch((failure) => { if (active) setListError(errorText(failure)) })
    return () => { active = false }
  }, [base, params])

  useEffect(() => {
    if (!selected) return
    let active = true
    setProfileError('')
    request<PlayerProfile>(base + '/' + encodeURIComponent(selected) + params).then((response) => {
      if (active) setProfile(response)
    }).catch((failure) => { if (active) setProfileError(errorText(failure)) })
    return () => { active = false }
  }, [base, params, selected])

  if (selected) {
    return <>
      <button className="breadcrumb back-link" onClick={() => onSelect('')}><ArrowLeft size={13} /> All players</button>
      {profileError && <ErrorBox message={profileError} />}
      {!profileError && profile?.data.id !== selected && <div role="status" className="loading"><span /> Loading player…</div>}
      {!profileError && profile?.data.id === selected && <PlayerDetail player={profile.data} meta={profile.meta} event={event} />}
    </>
  }

  const players = directory?.data ?? []
  const metadata = directory?.meta as (Meta & Partial<PlayerMeta>) | undefined
  const phrase = filter.trim().toLowerCase()
  const metrics: Record<string, (player: PlayerSummary) => number | null> = {
    current: (player) => player.rating.current,
    overall: (player) => player.rating.ovr,
    form: (player) => player.rating.form,
    kd: (player) => player.stats.kd,
  }
  const metric = metrics[order]
  const visible = players.filter((player) => (!team || player.team === team)
    && (!role || (role === 'Flex' ? player.primary_role === role : player.roles.includes(role)))
    && [player.handle, ...player.aliases, player.team].some((name) => name.toLowerCase().includes(phrase)))
    .sort((a, b) => (metric(b) ?? -Infinity) - (metric(a) ?? -Infinity) || a.handle.localeCompare(b.handle))

  return <>
    <div className="players-title">
      <PageTitle title="Players" subtitle={event.title + ' · ' + event.stage} />
      {metadata?.as_of && <Pill tone="blue"><History size={13} /> Through {dateLabel(metadata.as_of, { year: 'numeric' })}</Pill>}
    </div>
    {listError && <ErrorBox message={listError} />}
    {!directory && !listError && <div className="loading" role="status"><span /> Loading rosters…</div>}
    {directory && !players.length && <section className="panel"><Empty title="No player dataset">This event snapshot has no roster or player box scores.</Empty></section>}
    {players.length > 0 && <>
      <div className="player-strip">
        <div><Users2 size={18} /><strong>{players.length}</strong><span>Rostered players</span></div>
        <div><BadgeCheck size={18} /><strong>{players.filter((player) => player.rating.ovr !== null).length}</strong><span>Provisional ratings</span></div>
        <div><History size={18} /><strong>{metadata?.group_series_covered}</strong><span>Group series covered</span></div>
      </div>
      <div className="toolbar roster-filters">
        <label>Search<div className="search-input"><ScanSearch size={16} /><input value={filter} placeholder="Player handle or alias" onChange={(ev) => setFilter(ev.target.value)} /></div></label>
        <label>Team<select aria-label="Team" value={team} onChange={(ev) => onTeam(ev.target.value)}><option value="">All teams</option>
          {event.teams.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}
        </select></label>
        <label>Role<select aria-label="Role" value={role} onChange={(ev) => setRole(ev.target.value)}><option value="">All roles</option>
          {Object.keys(roleStyle).map((name) => <option key={name}>{name}</option>)}
        </select></label>
        <label>Sort by<select aria-label="Sort by" value={order} onChange={(ev) => setOrder(ev.target.value)}>
          <option value="current">Current rating</option><option value="overall">Overall rating</option>
          <option value="form">Recent form</option><option value="kd">K/D</option>
        </select></label>
      </div>
      <section className="panel">
        <header className="panel-heading"><div><h2><Users2 size={19} /> Player directory</h2><p>{visible.length} {visible.length === 1 ? 'player' : 'players'}</p></div><Pill tone="amber">{event.stage} ratings</Pill></header>
        {visible.length === 0
          ? <Empty title="No matching players">Change the team, role or search term.</Empty>
          : <div className="table-scroll"><table className="player-table">
            <thead><tr><th scope="col">Player</th><th scope="col">Team</th><th scope="col">Primary role</th><th scope="col">OVR</th><th scope="col">Form</th><th scope="col">Current</th><th className="desktop-player-stat" scope="col">K/D</th><th className="desktop-player-stat" scope="col">Maps</th><th className="desktop-player-stat" scope="col"><span className="sr-only">Profile</span></th></tr></thead>
            <tbody>{visible.map((player) => <tr key={player.id}>
              <th scope="row"><button className="profile-link" onClick={() => onSelect(player.id)}>{player.handle}</button>
                {player.listed_as === 'substitute' && <small className="roster-sub">Substitute</small>}
              </th>
              <td><span className="row-team" title={event.teams.find((item) => item.id === player.team)?.name}><TeamMark code={player.team} size="small" /><span className="sr-only">{player.team}</span></span></td>
              <td><RoleBadge role={player.primary_role} /></td>
              <td className="record-cell">{player.rating.ovr ?? '—'}</td>
              <td className={formTone(player.rating.form)}>{displayForm(player.rating.form)}</td>
              <td className="record-cell">{player.rating.current ?? '—'}</td>
              <td className="desktop-player-stat">{displayNumber(player.stats.kd)}</td><td className="desktop-player-stat">{player.stats.maps}</td>
              <td className="desktop-player-stat"><button className="open-profile" onClick={() => onSelect(player.id)} aria-label={'Open ' + player.handle + ' profile'}><ArrowRight size={15} /></button></td>
            </tr>)}</tbody>
          </table></div>}
        <div className="panel-footer">OVR reflects earlier {event.stage} matches. Form adds or subtracts points based on the latest covered series.</div>
      </section>
    </>}
  </>
}

function formTone(value: number | null) {
  return value === null || value === 0 ? 'text-muted' : value > 0 ? 'positive' : 'negative'
}

function PlayerDetail({ player, meta, event }: { player: PlayerProfile; meta: Meta; event: Snapshot }) {
  const details = meta as Meta & PlayerMeta
  const currentTeam = event.teams.find((item) => item.id === player.team)
  const stage = event.stage
  const stats = player.stats
  const rating = player.rating
  const heading = rating.status === 'unrated' ? 'Unrated' : rating.status === 'limited' ? 'Provisional rating' : stage + ' rating'
  const latest = player.history[0]

  return <>
    <section className="hero player-hero">
      <div className="hero-contours" aria-hidden="true"><i /><i /><i /><i /><b /><b /><b /></div>
      <div className="player-identity">
        <TeamMark code={player.team} size="large" />
        <div>
          <div className="identity-label">{currentTeam?.name ?? player.team} <span>·</span> {player.represented_region}</div>
          <h1>{player.handle}</h1>
          <div className="identity-tags">
            <RoleBadge role={player.primary_role} />
            {player.team_role && <Pill>{player.team_role}</Pill>}
            {player.listed_as === 'substitute' && <Pill>Listed substitute</Pill>}
          </div>
          {player.aliases.length > 0 && <p className="player-alias">Also known as {player.aliases.join(', ')}</p>}
        </div>
      </div>
      <div className="hero-reference"><History size={15} /><div><span>Profile snapshot</span><strong>{dateLabel(details.as_of, { year: 'numeric' })}</strong></div></div>
    </section>
    <div className="player-detail-grid">
      <section className="panel rating-panel">
        <header className="panel-heading">
          <div><h2><Activity size={19} /> Performance rating</h2>
            <p>{rating.ovr === null ? 'Minimum basis is two earlier series and 60 rounds.' : rating.baseline_series + ' earlier series · ' + rating.baseline_rounds + ' baseline rounds'}</p></div>
          <Pill tone={rating.status === 'limited' ? 'amber' : 'blue'}>{heading}</Pill>
        </header>
        {rating.ovr !== null ? <>
          <div className="rating-grid">
            <div><span>Overall</span><strong>{rating.ovr}</strong><small>Earlier {stage} matches</small></div>
            <div><span>Form</span><strong className={formTone(rating.form)}>{rating.form !== null && rating.form !== 0 && (
              rating.form > 0 ? <ArrowUpRight size={20} /> : <ArrowDownRight size={20} />
            )}{displayForm(rating.form)}</strong><small>{rating.latest_played_on ? 'Latest · ' + dateLabel(rating.latest_played_on) : 'Latest series'}</small></div>
            <div className="current-rating"><span>Current</span><strong>{rating.current ?? '—'}</strong><small>Overall adjusted for form</small></div>
          </div>
        </> : <div className="section-pad"><Notice>{stats.series === 0 ? 'No ' + stage + ' maps recorded for this player in the covered series.' : 'Insufficient ' + stage + ' match evidence for an overall rating.'}</Notice></div>}
      </section>
      <section className="panel">
        <header className="panel-heading"><div><h2><Crosshair size={19} /> {stage} stats</h2><p>{stats.series} series · {stats.maps} {stats.maps === 1 ? 'map' : 'maps'} · {number(stats.rounds)} rounds</p></div></header>
        <div className="player-stats">
          <div><span>K / D / A</span><strong>{stats.rounds ? [stats.kills, stats.deaths, stats.assists].join(' / ') : '—'}</strong></div>
          <div><span>K/D</span><strong>{displayNumber(stats.kd)}</strong></div>
          <div><span>Kills / round</span><strong>{displayNumber(stats.kpr)}</strong></div>
          <div><span>Assists / round</span><strong>{displayNumber(stats.apr)}</strong></div>
        </div>
      </section>
    </div>
    {player.facets && <SkillBreakdown facets={player.facets} stage={stage} />}
    <div className="player-detail-grid player-lower">
      <div className="player-main">
        <MatchHistory title={stage + ' match history'} rows={player.history} latest={latest?.id} />
        {player.earlier_history.length > 0 && <MatchHistory title="Earlier tournament matches" rows={player.earlier_history} />}
      </div>
      <div className="player-main">
        <section className="panel">
          <header className="panel-heading"><div><h2><Swords size={19} /> Roles and agents</h2><p>{player.role_evidence ? 'Observed in ' + player.role_evidence : 'Agent picks unavailable'}</p></div></header>
          {player.agents.length > 0 && <div className="section-pad">
            <div className="identity-tags">{player.roles.map((item) => <RoleBadge key={item} role={item} />)}</div>
            <ul className="agent-picks">{player.agents.map((agent) => <li key={agent.name}>
              <span><strong>{agent.name}</strong><small>{agent.role ?? 'Role unknown'}</small></span>
              <span>{agent.series} series</span>
            </li>)}</ul>
          </div>}
        </section>
        <section className="panel">
          <header className="panel-heading"><div><h2><Database size={19} /> Sources</h2><p>{details.player_model_version}</p></div></header>
          <div className="section-pad profile-sources">
            {details.player_sources.filter((item) => item.id !== 'vlr-box').map((item) =>
              <a href={item.url} key={item.id} target="_blank" rel="noreferrer">{item.label} <ArrowUpRight size={14} /></a>
            )}
            {player.profile_url && <a href={player.profile_url} target="_blank" rel="noreferrer">Player reference <ArrowUpRight size={14} /></a>}
          </div>
        </section>
      </div>
    </div>
    <details className="panel details rating-method">
      <summary>How ratings are calculated</summary>
      <div className="section-pad secondary-text">
        <p>{player.model.description}</p>
        <p>{player.model.form}</p>
        <p>{player.model.coverage}</p>
        <p>{player.model.facets}</p>
        <p>{player.model.roles}</p>
      </div>
    </details>
  </>
}

const facetStatus: Record<PlayerFacet['status'], string> = {
  proxy: 'Proxy',
  provisional: 'Provisional',
  insufficient: 'Insufficient sample',
  unavailable: 'Data unavailable',
}

function SkillBreakdown({ facets, stage }: { facets: PlayerFacet[]; stage: string }) {
  const graded = facets.filter((facet) => facet.score !== null).length
  return <section className="panel skill-panel">
    <header className="panel-heading">
      <div><h2><Gauge size={19} /> Skill breakdown</h2>
        <p>Provisional scores on a 1–99 scale using {stage} match evidence.</p></div>
      <Pill tone="blue">{graded} of {facets.length} scored</Pill>
    </header>
    <ul className="skill-grid">
      {facets.map((facet) => <li key={facet.id} className={'skill-card ' + (facet.score === null ? 'skill-unrated' : 'skill-graded')}>
        <div className="skill-name"><h3>{facet.id}</h3><span>{facet.label}</span></div>
        <div className="skill-reading">
          <strong aria-label={facet.score === null ? 'Unrated' : String(facet.score)}>{facet.score ?? '—'}</strong>
          <Pill tone={facet.status === 'proxy' ? 'amber' : facet.status === 'provisional' ? 'blue' : 'muted'}>{facetStatus[facet.status]}</Pill>
        </div>
        <p>{facet.evidence}</p>
        {facet.role_weight !== null && <small>{facet.role_weight.toLocaleString('en', { maximumFractionDigits: 1 })}% role prior weight</small>}
      </li>)}
    </ul>
    <footer className="panel-footer">
      Role prior weights come from the specification. Overall uses the separate group performance model.
    </footer>
  </section>
}

function MatchHistory({ title, rows, latest }: { title: string; rows: PlayerHistory[]; latest?: string }) {
  const earlier = !latest && rows.length > 0
  const showAcs = rows.some((row) => row.acs !== null)
  const showProviderRating = rows.some((row) => row.provider_rating !== null)
  return <section className="panel match-history">
    <header className="panel-heading"><div><h2><History size={19} /> {title}</h2>{earlier && <p>Selected archived matches</p>}</div></header>
    {!rows.length ? <div className="section-pad text-muted">No appearances in the covered group series.</div>
      : <div className="table-scroll"><table>
        <thead><tr><th scope="col">Series</th><th scope="col">Result</th><th scope="col">K / D / A</th>
          {showAcs && <th scope="col">ACS</th>}{showProviderRating && <th scope="col">Source rating</th>}
          <th scope="col" title="(Kills − deaths + 0.45 × assists) / rounds">Impact/R</th><th scope="col">Agents</th>
        </tr></thead>
        <tbody>{rows.map((row) => <tr key={row.id}>
          <th scope="row"><a className="history-source" href={row.source_url} target="_blank" rel="noreferrer">
            {earlier ? row.played_for + ' vs ' : 'vs '}{row.opponent} <ArrowUpRight size={12} /></a>
            <small>{dateLabel(row.played_on)}{earlier ? ' · ' + row.event : row.id === latest ? ' · Latest' : ''}</small>
          </th>
          <td className={row.score[0] > row.score[1] ? 'positive' : 'negative'}>{row.score.join('–')}</td>
          <td>{row.kills} / {row.deaths} / {row.assists}</td>
          {showAcs && <td>{row.acs ?? '—'}</td>}{showProviderRating && <td>{displayNumber(row.provider_rating)}</td>}
          <td className={formTone(row.impact)}>{row.impact > 0 ? '+' : ''}{row.impact.toFixed(2)}</td>
          <td className="history-agents">{row.agents.join(', ')}</td>
        </tr>)}</tbody>
      </table></div>}
  </section>
}
