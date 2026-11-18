import type { ReactNode } from 'react'
import { ArrowUpRight, ChartNoAxesCombined, CircleHelp, FlaskConical, Info, Radar } from 'lucide-react'
import type { Fixture, Team } from './types'

const colors: Record<string, string> = {
  RLY: '#53e4c5', OBT: '#ed8a91', NOD: '#9da0fb', BRS: '#e9b871', VLT: '#78b8fb', PTH: '#d693e0',
  ARC: '#53e4c5', BND: '#78b8fb', DEP: '#e9b871', WAV: '#ed8a91', PLS: '#9da0fb', RFT: '#ec9b79',
}

export function TeamMark({ code, size = 'normal' }: { code: string; size?: 'normal' | 'small' | 'large' }) {
  return <span className={'team-mark ' + size} style={{ color: colors[code] ?? '#9fb9d5' }} aria-hidden="true">{code.slice(0, 3)}</span>
}

export function Pill({ children, tone = 'muted' }: { children: ReactNode; tone?: 'muted' | 'mint' | 'amber' | 'blue' }) {
  return <span className={'pill ' + tone}>{children}</span>
}

export function Notice({ children }: { children: ReactNode }) {
  return <div className="notice"><Info size={16} /><div>{children}</div></div>
}

export function Empty({ title, children }: { title: string; children: ReactNode }) {
  return <div className="empty"><ChartNoAxesCombined size={28} /><h3>{title}</h3><p>{children}</p></div>
}

export function ErrorBox({ message }: { message: string }) {
  return <div className="error" role="alert"><CircleHelp size={17} /><div>{message}</div></div>
}

export function TeamLabel({ code, name }: { code: string; name?: string }) {
  return <span className="team-label"><TeamMark code={code} /><span><strong>{code}</strong>{name && <small>{name}</small>}</span></span>
}

export function FixtureRow({ fixture, teams, onSelect }: {
  fixture: Fixture; teams: Team[]; onSelect: (match: string) => void
}) {
  const a = teams.find((team) => team.id === fixture.team_a)
  const b = teams.find((team) => team.id === fixture.team_b)
  const label = a?.name + ' vs ' + b?.name
  const children = <>
    <span className="fixture-team"><TeamMark code={fixture.team_a} size="small" /><strong>{fixture.team_a}</strong></span>
    <span className="fixture-vs">{fixture.score?.join(' : ') ?? 'VS'}</span>
    <span className="fixture-team"><TeamMark code={fixture.team_b} size="small" /><strong>{fixture.team_b}</strong></span>
    <span className="fixture-kind">{fixture.status === 'ongoing' ? 'In progress' : 'BO' + fixture.best_of}</span>
  </>
  return fixture.status === 'scheduled'
    ? <button className="fixture-row" aria-label={'Simulate ' + fixture.team_a + ' vs ' + fixture.team_b} title={label}
        onClick={() => onSelect(fixture.id)}>{children}<ArrowUpRight size={15} /></button>
    : <div className="fixture-row result-fixture" title={label}>{children}</div>
}

export function dateLabel(date: string, options?: Intl.DateTimeFormatOptions) {
  return new Intl.DateTimeFormat('en-SG', { timeZone: 'UTC', month: 'short', day: 'numeric', ...options })
    .format(new Date(date + 'T00:00:00Z'))
}

const percentFormat = new Intl.NumberFormat('en', { style: 'percent', maximumFractionDigits: 1 })
export const percent = (value: number) => {
  if (value > 0 && value < 0.001) return '<0.1%'
  if (value > 0.999 && value < 1) return '>99.9%'
  return percentFormat.format(value)
}
export const probabilityWidth = (value: number) => (value * 100) + '%'
export const number = (value: number) => new Intl.NumberFormat('en').format(value)
export const signed = (value: number) => value > 0 ? '+' + value : String(value)
export const range = (lower: number, upper: number) => {
  const low = percent(lower), high = percent(upper)
  return low === high ? low : low + '–' + high
}
export const signedPoints = (value: number) => (value > 0.00001 ? '+' : '') + (value * 100).toFixed(1) + ' pp'
export const Sandbox = () => <Pill tone="amber"><FlaskConical size={12} /> Sandbox rules</Pill>
export const SimulationBadge = () => <Pill tone="mint"><Radar size={13} /> Simulation · fictional outcomes</Pill>
