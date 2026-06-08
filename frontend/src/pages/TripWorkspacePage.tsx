import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { approveApproval, createApproval, rejectApproval } from '../api/approvals'
import { addAgentRunMessage, continueAgentRun, getAgentRun } from '../api/agent'
import { simulateBooking } from '../api/bookings'
import { getProviderStatus } from '../api/providers'
import { AccommodationOptionsCard } from '../components/AccommodationOptionsCard'
import { AccommodationSourcePanel } from '../components/AccommodationSourcePanel'
import { AgentEventLog } from '../components/AgentEventLog'
import { AgentRunTimeline } from '../components/AgentRunTimeline'
import { ApprovalRequestsPanel } from '../components/ApprovalRequestsPanel'
import { AssumptionsPanel } from '../components/AssumptionsPanel'
import { BookingSimulationPanel } from '../components/BookingSimulationPanel'
import { BudgetBreakdownCard } from '../components/BudgetBreakdownCard'
import { CriticFindingsPanel } from '../components/CriticFindingsPanel'
import { ErrorState } from '../components/ErrorState'
import { EvidencePanel } from '../components/EvidencePanel'
import { ItineraryTimeline } from '../components/ItineraryTimeline'
import { LoadingState } from '../components/LoadingState'
import { MissingInfoForm } from '../components/MissingInfoForm'
import { ProgressStepper } from '../components/ProgressStepper'
import { FindingList, RiskFindingsPanel } from '../components/RiskFindingsPanel'
import { SourceRefsPanel } from '../components/SourceRefsPanel'
import { TransportOptionsCard } from '../components/TransportOptionsCard'
import type { BookingRecord } from '../types/approval'
import { errorMessage } from '../utils/errors'
import { cleanDisplayText, formatNumber, travelPurposeLabel } from '../utils/format'
import { tripStatusLabel } from '../utils/status'

export function TripWorkspacePage() {
  const { runId: routeRunId } = useParams<{ tripId?: string; runId?: string }>()
  const [searchParams] = useSearchParams()
  const runId = routeRunId ?? searchParams.get('runId') ?? ''
  const queryClient = useQueryClient()
  const queryKey = useMemo(() => ['agent-run', runId], [runId])

  const runQuery = useQuery({
    queryKey,
    queryFn: () => getAgentRun(runId),
    enabled: Boolean(runId),
  })
  const providerStatusQuery = useQuery({
    queryKey: ['provider-status'],
    queryFn: getProviderStatus,
  })

  const refreshRun = () => queryClient.invalidateQueries({ queryKey })

  const followUpMutation = useMutation({
    mutationFn: (message: string) => addAgentRunMessage(runId, { message }),
    onSuccess: refreshRun,
  })
  const continueMutation = useMutation({
    mutationFn: () => continueAgentRun(runId),
    onSuccess: refreshRun,
  })

  const data = runQuery.data
  const state = data?.state
  const tripId = data?.run.trip_id

  const createApprovalMutation = useMutation({
    mutationFn: (payload: Parameters<typeof createApproval>[1]) =>
      createApproval(tripId ?? '', payload),
    onSuccess: refreshRun,
  })
  const approveMutation = useMutation({
    mutationFn: (approvalId: string) => approveApproval(tripId ?? '', approvalId),
    onSuccess: refreshRun,
  })
  const rejectMutation = useMutation({
    mutationFn: (approvalId: string) => rejectApproval(tripId ?? '', approvalId),
    onSuccess: refreshRun,
  })
  const bookingMutation = useMutation({
    mutationFn: (payload: Parameters<typeof simulateBooking>[1]) =>
      simulateBooking(tripId ?? '', payload),
    onSuccess: refreshRun,
  })

  const currentError =
    runQuery.error ??
    followUpMutation.error ??
    continueMutation.error ??
    createApprovalMutation.error ??
    approveMutation.error ??
    rejectMutation.error ??
    bookingMutation.error

  if (!runId) return <ErrorState message="여행 계획 실행 정보를 찾을 수 없습니다." />
  if (runQuery.isLoading) return <LoadingState label="여행 계획을 불러오는 중입니다." />
  if (runQuery.error || !data || !state) return <ErrorState message={errorMessage(runQuery.error)} />

  const approvals = state.approval_requests
  const blockingFindings = state.critic_findings.filter((finding) => finding.severity === 'blocking')
  const booking = state.booking_records.at(-1) as BookingRecord | undefined
  const isApprovalWorking =
    createApprovalMutation.isPending || approveMutation.isPending || rejectMutation.isPending
  const hasMissingInfo = state.missing_fields.length > 0
  const canRecalculate = !hasMissingInfo && data.run.status !== 'running' && !continueMutation.isPending
  const summaryTitle = data.state_summary.destination ?? state.selected_destination ?? '목적지 미정'
  const budgetLabel = data.state_summary.budget_per_person
    ? `1인 ${formatNumber(data.state_summary.budget_per_person, state.currency)}`
    : data.state_summary.budget_total
      ? `총 ${formatNumber(data.state_summary.budget_total, state.currency)}`
      : '미정'
  const purposeLabel =
    travelPurposeLabel(state.brief?.travel_style) ||
    travelPurposeLabel(state.brief?.must_include.filter(Boolean).join(', ')) ||
    '미정'
  const isFlightSearch = state.brief?.transport_preference?.includes('flight_search') ?? false
  const isAccommodationSearch =
    state.accommodation_options.length > 0 &&
    state.transport_options.length === 0 &&
    state.optimized_itinerary === null
  const nextAction = hasMissingInfo
    ? '에이전트가 계획을 이어가기 위해 몇 가지를 묻고 있습니다.'
    : blockingFindings.length > 0
      ? '차단 이슈를 해결해야 예약 전 확인 단계로 넘어갈 수 있습니다.'
      : isFlightSearch
        ? '항공 후보와 예약 전 재확인 조건을 검토할 수 있습니다.'
        : isAccommodationSearch
          ? '숙소 후보와 source 정책을 검토할 수 있습니다.'
          : '일정, 비용, 이동, 숙소, 입국 리스크를 검토할 수 있습니다.'

  return (
    <div className="workspace travel-workspace">
      <section className="trip-summary-card">
        <div className="trip-summary-top">
          <div>
            <p className="eyebrow">여행 계획</p>
            <h1>{cleanDisplayText(summaryTitle)}</h1>
            <p className="summary-subtitle">{nextAction}</p>
          </div>
          <span className={`status-badge status-${state.status}`}>{tripStatusLabel(state.status)}</span>
        </div>
        <div className="trip-facts">
          <SummaryFact label="목적지" value={summaryTitle} />
          <SummaryFact label="기간" value={data.state_summary.date_range ?? '미정'} />
          <SummaryFact label="출발지" value={data.state_summary.origin ?? '미정'} />
          <SummaryFact
            label="인원"
            value={data.state_summary.travelers ? `${data.state_summary.travelers}명` : '미정'}
          />
          <SummaryFact label="예산" value={budgetLabel} />
          <SummaryFact label="여행 목적" value={purposeLabel || '미정'} />
          <SummaryFact label="상태" value={tripStatusLabel(state.status)} />
        </div>
        <ProgressStepper state={state} />
      </section>

      {currentError && <ErrorState message={errorMessage(currentError)} />}

      <div className="travel-dashboard-grid">
        <aside className="dashboard-left">
          <MissingInfoForm
            fields={state.missing_fields}
            isSubmitting={followUpMutation.isPending}
            onSubmit={followUpMutation.mutate}
            state={state}
          />
          <AssumptionsPanel assumptions={state.assumptions} />
          <AgentRunTimeline steps={data.steps} />
          <AgentEventLog events={data.events} />
          {blockingFindings.length > 0 && (
            <section className="card">
              <h2>차단 이슈</h2>
              <FindingList findings={blockingFindings} />
            </section>
          )}
          <section className="card action-card">
            <h2>다음 작업</h2>
            <button
              className="primary-button"
              disabled={!canRecalculate}
              type="button"
              onClick={() => continueMutation.mutate()}
            >
              {continueMutation.isPending ? '진행 중' : '계획 이어서 생성'}
            </button>
            {hasMissingInfo && (
              <p className="fine-print">에이전트 질문에 답하면 후보 조사와 일정 생성을 이어갑니다.</p>
            )}
          </section>
        </aside>

        <main className="dashboard-center">
          {isFlightSearch ? (
            <TransportOptionsCard options={state.transport_options} />
          ) : isAccommodationSearch ? (
            <AccommodationOptionsCard options={state.accommodation_options} />
          ) : (
            <ItineraryTimeline itinerary={state.optimized_itinerary} />
          )}
          <div className="plan-result-grid compact-results">
            <CriticFindingsPanel findings={state.critic_findings} />
            <SourceRefsPanel sourceRefs={state.source_refs} />
          </div>
        </main>

        <aside className="dashboard-right">
          {!isFlightSearch && !isAccommodationSearch && <BudgetBreakdownCard budget={state.budget} />}
          {isAccommodationSearch && (
            <AccommodationSourcePanel
              providerStatuses={providerStatusQuery.data ?? []}
              sourceRefs={state.source_refs}
              isLoading={providerStatusQuery.isLoading}
            />
          )}
          <EvidencePanel state={state} />
          {!isFlightSearch && <TransportOptionsCard options={state.transport_options} />}
          {!isFlightSearch && !isAccommodationSearch && (
            <AccommodationOptionsCard options={state.accommodation_options} />
          )}
          {!isFlightSearch && !isAccommodationSearch && <RiskFindingsPanel findings={state.risk_findings} />}
          <ApprovalRequestsPanel
            approvals={approvals}
            isWorking={isApprovalWorking}
            onCreate={createApprovalMutation.mutate}
            onApprove={approveMutation.mutate}
            onReject={rejectMutation.mutate}
          />
          <BookingSimulationPanel
            approvals={approvals}
            booking={booking}
            isSimulating={bookingMutation.isPending}
            onSimulate={bookingMutation.mutate}
          />
        </aside>
      </div>

      <p className="mvp-footnote">
        현재 MVP에서는 일부 결과가 시뮬레이션으로 표시됩니다. 실제 결제·발권·예약은 수행되지 않습니다.
      </p>
    </div>
  )
}

function SummaryFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="summary-fact">
      <span>{label}</span>
      <strong>{cleanDisplayText(value) || '미정'}</strong>
    </div>
  )
}
