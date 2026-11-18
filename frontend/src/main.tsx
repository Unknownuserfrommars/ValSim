import { StrictMode, useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { CalendarDays, Database, FlaskConical, Globe2, LayoutDashboard, PanelTop, Users2, Zap } from 'lucide-react'
import { errorText, request } from './api'
import { Dashboard, Events, Schedule, SourceView } from './Dashboard'
import { PlayersView } from './Players'
import { Studio } from './Studio'
import type { Envelope, EventCard, Scope, Snapshot, Standing, View } from './types'
import { ErrorBox, Pill } from './ui'
import './style.css'

const defaultEventId = 'valsim-demo-group-a'

const navigation = [
  { id: 'overview', label: 'Overview', compact: 'Overview', icon: LayoutDashboard },
  { id: 'events', label: 'Events', compact: 'Events', icon: Globe2 },
  { id: 'matches', label: 'Matches', compact: 'Matches', icon: CalendarDays },
  { id: 'players', label: 'Players', compact: 'Players', icon: Users2 },
  { id: 'simulations', label: 'Simulation lab', compact: 'Lab', icon: FlaskConical },
  { id: 'source', label: 'Data sources', compact: 'Sources', icon: Database },
] as const

function App() {
  const initialQuery = useRef(new URLSearchParams(window.location.search)).current
  const [view, setView] = useState<View>(() => initialQuery.get('view') === 'players' ? 'players' : 'overview')
  const [playerId, setPlayerId] = useState(() => initialQuery.get('player') ?? '')
  const [playerTeam, setPlayerTeam] = useState('')
  const [events, setEvents] = useState<Envelope<EventCard>[]>([])
  const [envelope, setEnvelope] = useState<Envelope<Snapshot> | null>(null)
  const [standings, setStandings] = useState<Standing[]>([])
  const [scope, setScope] = useState<Scope>('remaining_group')
  const [fixture, setFixture] = useState('')
  const [studioRevision, setStudioRevision] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const loadSequence = useRef(0)
  const event = envelope?.data
  const activeEventId = event?.event_id
  const groupTabs = event && event.stage.startsWith('Group ') ? events.map(({ data }) => data)
    .filter((item) => item.title === event.title && item.region === event.region && item.stage.startsWith('Group '))
    .sort((a, b) => a.stage.localeCompare(b.stage)) : []

  async function refreshEvents() {
    const list: Envelope<EventCard>[] = []
    for (let offset = 0;; offset += 100) {
      const response = await request<{ items: Envelope<EventCard>[]; total: number }>('/v1/events?limit=100&offset=' + offset)
      list.push(...response.data.items)
      if (list.length >= response.data.total || response.data.items.length === 0) break
    }
    setEvents(list)
    return list
  }

  async function loadEvent(eventId: string, snapshotId?: string) {
    const sequence = ++loadSequence.current
    setError('')
    setLoading(true)
    try {
      const base = '/v1/events/' + eventId
      const snapshot = await request<Snapshot>(base + (snapshotId ? '?snapshot_id=' + snapshotId : ''))
      const ranks = await request<Standing[]>(base + '/standings?snapshot_id=' + snapshot.data.id)
      if (sequence !== loadSequence.current) return
      setEnvelope(snapshot)
      setStandings(ranks.data)
      setScope('remaining_group')
      setFixture('')
    } catch (failure) {
      if (sequence === loadSequence.current) setError(errorText(failure))
    } finally {
      if (sequence === loadSequence.current) setLoading(false)
    }
  }

  useEffect(() => {
    let active = true
    refreshEvents().then((items) => {
      if (!active) return
      const first = items.find(({ data }) => data.event_id === initialQuery.get('event'))
        || items.find(({ data }) => data.event_id === defaultEventId) || items[0]
      if (first) void loadEvent(first.data.event_id)
      else { setView('events'); setLoading(false) }
    }).catch((failure) => {
      if (!active) return
      setLoading(false)
      setError(errorText(failure))
    })
    return () => { active = false; loadSequence.current++ }
  }, [])

  useEffect(() => {
    const url = new URL(window.location.href)
    if (activeEventId === defaultEventId) url.searchParams.delete('event')
    else if (activeEventId) url.searchParams.set('event', activeEventId)
    if (view === 'players') {
      url.searchParams.set('view', 'players')
      if (playerId) url.searchParams.set('player', playerId)
      else url.searchParams.delete('player')
    } else {
      url.searchParams.delete('view')
      url.searchParams.delete('player')
    }
    if (url.href !== window.location.href) window.history.replaceState(null, '', url.href)
  }, [view, playerId, activeEventId])

  function selectEvent(id: string, next = view) {
    setPlayerId('')
    setPlayerTeam('')
    go(next)
    if (id !== activeEventId || view === 'events') void loadEvent(id)
  }

  function pickPlayer(id: string) {
    setPlayerId(id)
    window.scrollTo({ top: 0 })
  }

  function openRoster(team = '') {
    setPlayerTeam(team)
    setPlayerId('')
    go('players')
  }

  function go(next: View) {
    setView(next)
    window.scrollTo({ top: 0 })
  }

  function openSimulation(next: Scope, id = '') {
    setScope(next)
    setFixture(id)
    setStudioRevision((value) => value + 1)
    go('simulations')
  }

  const openMatch = (id: string) => openSimulation('match', id)
  const openGroup = () => openSimulation('remaining_group')

  return <div className="app-shell">
    <a className="skip-link" href="#main">Skip to content</a>
    <aside className="sidebar">
      <button className="brand" onClick={() => go('overview')} aria-label="ValSim overview"><span className="brand-icon"><Zap size={22} fill="currentColor" /></span>
        <span><strong>Val<span>Sim</span></strong><small>ESPORTS SIMULATOR</small></span>
      </button>
      <nav aria-label="Main navigation">
        {navigation.map(({ id, label, compact, icon: Icon }) => <button key={id} className={view === id ? 'nav-item active' : 'nav-item'}
          aria-label={label} aria-current={view === id ? 'page' : undefined} onClick={() => id === 'players' ? openRoster() : go(id)} disabled={id !== 'events' && !event}>
          <Icon size={19} strokeWidth={1.9} /><span className="nav-full">{label}</span><span className="nav-compact">{compact}</span>
        </button>)}
      </nav>
      <div className="sidebar-footer"><PanelTop size={16} /><span>Local workspace</span><a href="/disclaimer" target="_blank" rel="noreferrer">Disclaimer</a></div>
    </aside>
    <div className="main-shell">
      <header className="topbar">
        <div><span>Workspace</span><i>/</i><strong>{navigation.find((item) => item.id === view)?.label}</strong></div>
        {event && <Pill tone="blue"><span className="status-dot" /> {event.source.permission === 'fictional_demo' ? 'Fictional demo' : 'Snapshot mode'}</Pill>}
      </header>
      <main className="content" id="main">
        {error && <ErrorBox message={error} />}
        {loading && <div className="loading" role="status"><span /> Loading event…</div>}
        {view !== 'events' && groupTabs.length > 1 && <div className="group-switch" role="group" aria-label="Tournament group">
          {groupTabs.map((group) => <button key={group.event_id} aria-pressed={group.event_id === activeEventId}
            disabled={loading} onClick={() => selectEvent(group.event_id)}>{group.stage}</button>)}
        </div>}
        {!loading && view === 'events' && <Events events={events} onOpen={(id) => selectEvent(id, 'overview')} />}
        {!loading && event && envelope && <>
          {view === 'overview' && <Dashboard key={event.id} event={event} standings={standings} onMatch={openMatch} onGroup={openGroup}
            onRoster={openRoster} onBracket={() => openSimulation('bracket')} onMatches={() => go('matches')} onSource={() => go('source')} onEvents={() => go('events')} />}
          {view === 'matches' && <Schedule key={event.id} event={event} onMatch={openMatch} />}
          {view === 'players' && <PlayersView key={event.id} event={event} selected={playerId} onSelect={pickPlayer}
            team={playerTeam} onTeam={setPlayerTeam} />}
          <div hidden={view !== 'simulations'}>
            <Studio key={event.id + ':' + studioRevision} event={event} scope={scope} fixtureId={fixture} setScope={setScope} setFixture={setFixture} />
          </div>
        </>}
        {view === 'source' && event && envelope && <div aria-busy={loading} inert={loading}>
          <SourceView event={event} meta={envelope.meta} onPlayers={() => openRoster()} onRevision={(id) => void loadEvent(event.event_id, id)}
            onImport={(id, revision) => { void refreshEvents().catch((failure) => setError(errorText(failure))); void loadEvent(id, revision) }} />
        </div>}
      </main>
    </div>
  </div>
}

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>)
