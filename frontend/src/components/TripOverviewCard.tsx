import { CalendarDays, CircleDollarSign, Flag, MapPin, Plane, Users } from 'lucide-react'
import type { ReactNode } from 'react'
import type { TripPlanState } from '../types/trip'
import { formatDate, formatNumber } from '../utils/format'
import { tripStatusLabel } from '../utils/status'
import { ProgressStepper } from './ProgressStepper'
import { TripStatusBadge } from './TripStatusBadge'

const purposeLabels: Record<string, string> = {
  food: '맛집',
  shopping: '쇼핑',
  culture: '역사/문화',
  onsen: '휴양',
}

export function TripOverviewCard({ state }: { state: TripPlanState }) {
  const brief = state.brief
  const destination = state.selected_destination ?? brief?.destinations?.join(', ') ?? '목적지 미정'
  const origin = brief?.origin ?? '출발지 미정'
  const dateRange =
    brief?.start_date && brief?.end_date
      ? `${formatDate(brief.start_date)} - ${formatDate(brief.end_date)}`
      : '기간 미정'
  const travelers = brief?.travelers ? `${brief.travelers}명` : '인원 미정'
  const budget =
    brief?.budget_total || brief?.budget_per_person
      ? [
          brief.budget_per_person && `1인 ${formatNumber(brief.budget_per_person, state.currency)}`,
          brief.budget_total && `총 ${formatNumber(brief.budget_total, state.currency)}`,
        ]
          .filter(Boolean)
          .join(' / ')
      : '예산 미정'
  const purposes = describePurposes(brief?.travel_style, brief?.must_include)

  return (
    <section className="trip-summary-card">
      <div className="trip-summary-top">
        <div>
          <p className="eyebrow">여행 요약</p>
          <h1>{destination}</h1>
          <div className="trip-route">
            <Plane aria-hidden="true" />
            <span>{origin}</span>
            <strong>→</strong>
            <span>{destination}</span>
          </div>
        </div>
        <TripStatusBadge status={state.status} />
      </div>
      <div className="trip-facts" aria-label="여행 핵심 정보">
        <Fact icon={<MapPin aria-hidden="true" />} label="목적지" value={destination} />
        <Fact icon={<CalendarDays aria-hidden="true" />} label="기간" value={dateRange} />
        <Fact icon={<Plane aria-hidden="true" />} label="출발지" value={origin} />
        <Fact icon={<Users aria-hidden="true" />} label="인원" value={travelers} />
        <Fact icon={<CircleDollarSign aria-hidden="true" />} label="예산" value={budget} />
        <Fact icon={<Flag aria-hidden="true" />} label="여행 목적" value={purposes} />
        <Fact icon={<Flag aria-hidden="true" />} label="상태" value={tripStatusLabel(state.status)} />
      </div>
      <ProgressStepper state={state} />
    </section>
  )
}

function describePurposes(style?: string | null, includes?: string[]): string {
  const tokens = [...(style?.split(',') ?? []), ...(includes ?? [])]
    .map((token) => token.trim())
    .filter(Boolean)
  const labels = tokens.map((token) => purposeLabels[token] ?? token)
  return Array.from(new Set(labels)).join(', ') || '목적 미정'
}

function Fact({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="trip-fact">
      {icon}
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
    </div>
  )
}
