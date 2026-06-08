import type { TripPlanState } from '../types/trip'

const steps = [
  { key: 'basic', label: '기본 정보' },
  { key: 'options', label: '항공/숙소 후보' },
  { key: 'itinerary', label: '일정 생성' },
  { key: 'budget', label: '예산 검증' },
  { key: 'entry', label: '입국 리스크 확인' },
  { key: 'approval', label: '승인/예약 전 확인' },
] as const

const flightSteps = [
  { key: 'basic', label: '요청 조건' },
  { key: 'flight', label: '항공 후보' },
  { key: 'check', label: '조건 검증' },
  { key: 'approval', label: '예약 전 확인' },
] as const

export function ProgressStepper({ state }: { state: TripPlanState }) {
  const isFlightSearch = state.brief?.transport_preference?.includes('flight_search') ?? false
  const visibleSteps = isFlightSearch ? flightSteps : steps
  const activeIndex = isFlightSearch ? getFlightProgressIndex(state) : getProgressIndex(state)

  return (
    <ol className="progress-stepper" aria-label="여행 계획 진행 단계">
      {visibleSteps.map((step, index) => (
        <li
          className={`${index <= activeIndex ? 'is-active' : ''} ${
            index < activeIndex ? 'is-complete' : ''
          }`}
          key={step.key}
        >
          <span>{index + 1}</span>
          <strong>{step.label}</strong>
        </li>
      ))}
    </ol>
  )
}

function getFlightProgressIndex(state: TripPlanState): number {
  if (state.booking_records.length > 0 || state.approval_requests.length > 0) return 3
  if (state.status === 'ready' || state.status === 'validating' || state.status === 'completed') {
    return 2
  }
  if (state.transport_options.length > 0 || state.status === 'researching') return 1
  return 0
}

function getProgressIndex(state: TripPlanState): number {
  if (state.booking_records.length > 0 || state.status === 'completed') return 5
  if (state.approval_requests.length > 0 || state.status === 'needs_approval') return 5
  if (state.risk_findings.length > 0 || state.status === 'validating' || state.status === 'ready') {
    return 4
  }
  if (state.budget) return 3
  if (state.optimized_itinerary || state.status === 'drafting') return 2
  if (
    state.transport_options.length > 0 ||
    state.accommodation_options.length > 0 ||
    state.status === 'researching'
  ) {
    return 1
  }
  return 0
}
