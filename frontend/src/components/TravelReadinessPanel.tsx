import { Bed, CheckCircle2, CircleAlert, CircleDashed, Landmark, Plane, Wallet } from 'lucide-react'
import type { ReactNode } from 'react'
import type { TripPlanState } from '../types/trip'

interface ReadinessItem {
  key: string
  label: string
  description: string
  done: boolean
  warning?: boolean
  icon: ReactNode
}

export function TravelReadinessPanel({ state }: { state: TripPlanState }) {
  const hasBlocking = state.critic_findings.some((finding) => finding.severity === 'blocking')
  const hasRisk = state.risk_findings.length > 0
  const approved = state.approval_requests.some((approval) => approval.status === 'approved')
  const items: ReadinessItem[] = [
    {
      key: 'brief',
      label: '기본 정보',
      description: state.missing_fields.length
        ? `${state.missing_fields.length}개 정보가 더 필요합니다.`
        : '출발지, 날짜, 인원이 정리됐습니다.',
      done: state.missing_fields.length === 0,
      icon: <CheckCircle2 aria-hidden="true" />,
    },
    {
      key: 'flight',
      label: '항공',
      description: state.transport_options.length
        ? `${state.transport_options.length}개 항공 후보`
        : '항공 후보를 아직 찾지 않았습니다.',
      done: state.transport_options.length > 0,
      icon: <Plane aria-hidden="true" />,
    },
    {
      key: 'stay',
      label: '숙소',
      description: state.accommodation_options.length
        ? `${state.accommodation_options.length}개 숙소 후보`
        : '숙소 후보를 아직 찾지 않았습니다.',
      done: state.accommodation_options.length > 0,
      icon: <Bed aria-hidden="true" />,
    },
    {
      key: 'budget',
      label: '예산',
      description: state.budget
        ? `총 ${state.budget.total_estimated_cost.toLocaleString('ko-KR')} ${state.currency}`
        : '예산 추정이 아직 없습니다.',
      done: Boolean(state.budget),
      warning: state.critic_findings.some((finding) => finding.category === 'budget'),
      icon: <Wallet aria-hidden="true" />,
    },
    {
      key: 'entry',
      label: '입국/리스크',
      description: hasRisk ? '공식 확인이 필요한 리스크가 있습니다.' : '리스크 확인 대기 중입니다.',
      done: state.risk_findings.length > 0,
      warning: hasRisk,
      icon: <Landmark aria-hidden="true" />,
    },
    {
      key: 'approval',
      label: '승인/예약',
      description: approved ? '승인된 요청이 있습니다.' : '예약 전 승인 요청이 필요합니다.',
      done: approved,
      icon: <CircleDashed aria-hidden="true" />,
    },
  ]

  return (
    <section className="card readiness-card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">출발 전 체크</p>
          <h2>여행 준비 상태</h2>
        </div>
        {hasBlocking && <span className="small-badge danger-badge">차단 이슈</span>}
      </div>
      <div className="readiness-grid">
        {items.map((item) => (
          <article
            className={`readiness-item ${item.done ? 'is-done' : ''} ${
              item.warning ? 'has-warning' : ''
            }`}
            key={item.key}
          >
            <div className="readiness-icon">
              {item.warning ? <CircleAlert aria-hidden="true" /> : item.icon}
            </div>
            <div>
              <strong>{item.label}</strong>
              <p>{item.description}</p>
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}
