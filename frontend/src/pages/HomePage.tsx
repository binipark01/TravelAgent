import { useMutation, useQuery } from '@tanstack/react-query'
import { Bot, CheckCircle2, Circle, Clock3, Plane, Plus } from 'lucide-react'
import { Fragment, useEffect, useRef, useState } from 'react'
import {
  addAgentRunMessage,
  cancelAgentRun,
  createAgentRun,
  getAgentRun,
  listAgentRuns,
  updateItinerary,
} from '../api/agent'
import type { Itinerary } from '../types/itinerary'
import { AgentCommandBox } from '../components/AgentCommandBox'
import { ErrorState } from '../components/ErrorState'
import { PlanCards } from '../components/PlanCards'
import { TripSummaryHeader } from '../components/TripSummaryHeader'
import type {
  AgentRunDetailResponse,
  AgentRunResponse,
  AgentRunStatus,
  AgentStep,
} from '../types/agent'
import type { LLMAnswerRequest } from '../types/llm'
import type { TripPlanState } from '../types/trip'
import {
  RUN_STATUS_LABELS,
  buildAgentRunAnswer,
  coreSelectedAgents,
} from '../utils/agentRunDisplay'
import { errorMessage } from '../utils/errors'

// 새로고침해도 현재 계획을 유지하려고 활성 run_id를 보관한다(로컬 사용 전제).
const ACTIVE_RUN_KEY = 'travelAgent.activeRunId'

const SCOPE_ITEMS = [
  { key: 'flight', label: '항공권' },
  { key: 'accommodation', label: '숙소' },
  { key: 'restaurant', label: '식당' },
  { key: 'route', label: '일정' },
  { key: 'budget', label: '예산' },
] as const

interface ChatTurn {
  id: string
  message: string
  response?: AgentRunResponse
  error?: string
}

function nextTurnId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `turn_${Date.now()}_${Math.round(Math.random() * 1e6)}`
}

/** '이전 요청' 목록의 날짜 라벨(예: 6/21). date_range가 없을 때 created_at으로 대체. */
function formatRunDate(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleDateString('ko-KR', { month: 'numeric', day: 'numeric' })
}

/** 캔버스에 렌더할 실제(non-mock) 카드가 하나라도 있는지. PlanCards의 표시 조건과 맞춘다. */
function planHasContent(plan?: TripPlanState | null): boolean {
  if (!plan) return false
  const flights = (plan.transport_options ?? []).filter((o) => !o.metadata.is_mock)
  const hotels = (plan.accommodation_options ?? []).filter((o) => !o.metadata.source_ref.is_mock)
  const pois = (plan.poi_candidates ?? []).filter((o) => !o.metadata.source_ref.is_mock)
  const activities = (plan.activity_options ?? []).filter((o) => !o.metadata.source_ref.is_mock)
  return (
    flights.length > 0 ||
    hotels.length > 0 ||
    pois.length > 0 ||
    activities.length > 0 ||
    (plan.optimized_itinerary?.days?.length ?? 0) > 0 ||
    plan.budget != null ||
    plan.fx_info != null ||
    plan.transport_tickets != null ||
    plan.local_transport != null ||
    plan.nearby_guide != null ||
    plan.visa_result != null ||
    plan.safety_info != null
  )
}

/** 이어가기 응답(detail)을 첫 응답(AgentRunResponse)과 같은 형태로 맞춘다. */
function adaptDetail(detail: AgentRunDetailResponse): AgentRunResponse {
  return {
    trip_id: detail.run.trip_id,
    run_id: detail.run.run_id,
    status: detail.run.status,
    current_step: detail.run.current_step,
    steps: detail.steps,
    missing_fields: detail.state_summary.missing_fields,
    questions: [],
    state_summary: detail.state_summary,
    partial_plan: detail.state,
    events: detail.events,
  }
}

export function HomePage() {
  const [turns, setTurns] = useState<ChatTurn[]>([])
  // 같은 세션의 run을 이어가 일정·후보가 턴 사이에 유지되게 한다(상태 영속).
  const [runId, setRunId] = useState<string | null>(null)
  // 현재 실행 중인 run을 폴링한다 → '되는 것부터' 카드가 순서대로 채워진다.
  const [pollingRunId, setPollingRunId] = useState<string | null>(null)
  const [activeTurnId, setActiveTurnId] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: async (vars: {
      payload: LLMAnswerRequest
      turnId: string
    }): Promise<AgentRunResponse> => {
      if (runId) {
        // 이어가기 턴: 같은 run에 메시지 추가 → 백엔드가 즉시 run_id 반환, 실행은 백그라운드.
        const detail = await addAgentRunMessage(runId, { message: vars.payload.message })
        return adaptDetail(detail)
      }
      // 첫 턴: 새 run 시작(즉시 run_id 반환).
      const history = turns.map((turn) => turn.message)
      return createAgentRun({ ...vars.payload, history })
    },
    onSuccess: (data, vars) => {
      if (data.run_id) {
        setRunId(data.run_id)
        // 새로고침 복원을 위해 활성 run을 저장.
        localStorage.setItem(ACTIVE_RUN_KEY, data.run_id)
        // 아직 끝나지 않았으면 폴링을 시작한다.
        if (!isTerminalStatus(data.status)) setPollingRunId(data.run_id)
        else setActiveTurnId(null)
      }
      setTurns((prev) =>
        prev.map((turn) => (turn.id === vars.turnId ? { ...turn, response: data } : turn)),
      )
    },
    onError: (error, vars) => {
      setActiveTurnId(null)
      setPollingRunId(null)
      setTurns((prev) =>
        prev.map((turn) =>
          turn.id === vars.turnId ? { ...turn, error: errorMessage(error) } : turn,
        ),
      )
    },
  })

  // 실행 중인 run을 ~1.2초마다 폴링해 부분 결과를 가져온다.
  // 종료되면 아래 useEffect가 pollingRunId를 비워 폴링을 멈춘다(버전 무관한 값 형태).
  const pollQuery = useQuery({
    queryKey: ['agentRun', pollingRunId],
    enabled: pollingRunId != null,
    queryFn: () => getAgentRun(pollingRunId as string),
    refetchInterval: pollingRunId != null ? 1200 : false,
    // 탭이 백그라운드여도 폴링을 멈추지 않는다(실행 중 다른 탭을 봐도 갱신).
    refetchIntervalInBackground: true,
    refetchOnWindowFocus: false,
    gcTime: 0,
  })

  // 좌측 사이드바: 지난 요청 기록(클릭하면 그 계획을 이어서 본다).
  const runsQuery = useQuery({
    queryKey: ['agentRunsList'],
    queryFn: () => listAgentRuns(20),
    staleTime: 30_000,
  })

  useEffect(() => {
    const detail = pollQuery.data
    if (!detail || !activeTurnId) return
    const response = adaptDetail(detail)
    setTurns((prev) =>
      prev.map((turn) => (turn.id === activeTurnId ? { ...turn, response } : turn)),
    )
    if (isTerminalStatus(detail.run.status)) {
      setPollingRunId(null)
      setActiveTurnId(null)
      // 방금 끝난 요청이 '이전 요청' 목록에 바로 보이도록 새로고침.
      void runsQuery.refetch()
    }
  }, [pollQuery.data, activeTurnId, runsQuery])

  // 마운트 시: '최근 여행'에서 온 ?run=<id>이 있으면 그걸, 없으면 저장된 활성 run을
  // 서버에서 불러와 대화·캔버스를 복원하고 이어서 대화할 수 있게 한다.
  const restoredRef = useRef(false)
  useEffect(() => {
    if (restoredRef.current) return
    restoredRef.current = true
    const runParam = new URLSearchParams(window.location.search).get('run')
    const savedRunId = runParam || localStorage.getItem(ACTIVE_RUN_KEY)
    if (!savedRunId) return
    getAgentRun(savedRunId)
      .then((detail) => {
        const response = adaptDetail(detail)
        const messages = detail.events
          .filter((event) => event.type === 'user_message')
          .map((event) => String((event.payload.message as string | undefined) ?? ''))
          .filter(Boolean)
        const lastMessage =
          messages[messages.length - 1] || detail.state.raw_user_message || '이전 요청'
        // 한 run에 여러 턴이 쌓여 답변을 턴별로 복원할 수 없으므로, 마지막 대화 1개만
        // 깔끔히 복원한다(과거 메시지 무더기·엉뚱한 답변 매칭 방지). 계획은 캔버스로 복원.
        const restored: ChatTurn = { id: 'restored', message: lastMessage, response }
        setTurns([restored])
        setRunId(savedRunId)
        // 이어가기·새로고침을 위해 활성 run으로 저장하고, URL의 ?run=은 정리한다.
        localStorage.setItem(ACTIVE_RUN_KEY, savedRunId)
        if (runParam) window.history.replaceState({}, '', '/')
        if (!isTerminalStatus(detail.run.status)) {
          setActiveTurnId('restored')
          setPollingRunId(savedRunId)
        }
      })
      .catch(() => {
        if (!runParam) localStorage.removeItem(ACTIVE_RUN_KEY)
      })
  }, [])

  // 사용자가 화면에서 직접 편집한 일정을 즉시 반영(낙관적) + 서버에 저장.
  function handleItineraryChange(itinerary: Itinerary) {
    if (!runId) return
    setTurns((prev) => {
      let lastIdx = -1
      prev.forEach((turn, i) => {
        if (turn.response) lastIdx = i
      })
      if (lastIdx < 0 || !prev[lastIdx].response?.partial_plan) return prev
      const resp = prev[lastIdx].response as AgentRunResponse
      const updated: AgentRunResponse = {
        ...resp,
        partial_plan: { ...resp.partial_plan!, optimized_itinerary: itinerary },
      }
      return prev.map((turn, i) => (i === lastIdx ? { ...turn, response: updated } : turn))
    })
    updateItinerary(runId, itinerary).catch((error) => console.error('일정 저장 실패', error))
  }

  function handleSubmit(payload: LLMAnswerRequest) {
    const turnId = nextTurnId()
    setActiveTurnId(turnId)
    setTurns((prev) => [...prev, { id: turnId, message: payload.message }])
    mutation.mutate({ payload, turnId })
  }

  // 실행 중지: 백그라운드 실행에 취소 신호를 보내고(다음 단계 경계에서 멈춤) 화면은 즉시
  // 멈춘 것으로 전환한다. 그때까지 모인 부분 결과(카드)는 그대로 둔다.
  async function handleCancel() {
    const id = pollingRunId ?? runId
    const turnId = activeTurnId
    setPollingRunId(null)
    setActiveTurnId(null)
    if (!id) return
    try {
      const detail = await cancelAgentRun(id)
      const response = adaptDetail(detail)
      setTurns((prev) =>
        prev.map((turn) => (turn.id === turnId ? { ...turn, response } : turn)),
      )
      void runsQuery.refetch()
    } catch (error) {
      console.error('중지 실패', error)
    }
  }

  // 실행이 진행 중인지(POST 대기 또는 폴링 중) — 진행 표시·로딩 상태에 쓴다.
  const isRunning = activeTurnId != null
  // 중앙 캔버스/좌측 패널은 가장 최근에 응답이 있는 턴을 기준으로 보여준다(폴링 중 실시간 갱신).
  const lastResolved = [...turns].reverse().find((turn) => turn.response)?.response
  const plan = lastResolved?.partial_plan
  // 캔버스에 보여줄 실제 카드가 하나라도 생겼는지(없으면 세로 진행 표시 유지).
  const hasContent = planHasContent(plan)
  const summary = lastResolved?.state_summary
  const firstWeather = plan?.optimized_itinerary?.days?.[0]?.weather ?? null
  const selectedAgents = lastResolved ? coreSelectedAgents(lastResolved) : []
  const latestMessage = turns.length > 0 ? turns[turns.length - 1].message : null
  const statusBadge = isRunning
    ? 'agent 실행 중'
    : lastResolved
      ? (RUN_STATUS_LABELS[lastResolved.status] ?? lastResolved.status)
      : '대기 중'

  return (
    <div className="agent-console-shell">
      <aside className="agent-session-panel" aria-label="여행 작업">
        <div className="session-brand-block">
          <Bot aria-hidden="true" />
          <div>
            <strong>TravelAgent</strong>
            <span>여행 agent workspace</span>
          </div>
        </div>
        <button
          className="new-chat-button"
          type="button"
          onClick={() => {
            localStorage.removeItem(ACTIVE_RUN_KEY)
            window.location.assign('/')
          }}
        >
          <Plus aria-hidden="true" />
          새 요청
        </button>
        <section className="side-section">
          <h2>최근 요청</h2>
          {latestMessage ? (
            <p className="recent-request-text">{latestMessage}</p>
          ) : (
            <p className="empty-panel-text">아직 보낸 요청이 없습니다.</p>
          )}
        </section>
        <section className="side-section">
          <h2>작업 범위</h2>
          <ul className="workspace-scope-list">
            {SCOPE_ITEMS.map((item) => {
              const active = selectedAgents.includes(item.key)
              return (
                <li
                  key={item.key}
                  style={active ? { color: '#0f766e', fontWeight: 600 } : undefined}
                >
                  {active ? <CheckCircle2 aria-hidden="true" /> : <Circle aria-hidden="true" />}
                  {item.label}
                </li>
              )
            })}
          </ul>
        </section>
        <section className="side-section side-section--history">
          <h2>이전 요청</h2>
          {runsQuery.isLoading ? (
            <p className="empty-panel-text">불러오는 중…</p>
          ) : runsQuery.data && runsQuery.data.length > 0 ? (
            <ul className="history-list">
              {runsQuery.data.map((run) => {
                const title = run.destination?.trim() || run.message.trim()
                const sub = run.date_range || formatRunDate(run.created_at)
                const isActive = run.run_id === runId
                return (
                  <li key={run.run_id}>
                    <button
                      type="button"
                      className={`history-item${isActive ? ' history-item--active' : ''}`}
                      onClick={() => window.location.assign(`/?run=${run.run_id}`)}
                      title={run.message}
                    >
                      <span className="history-title">{title}</span>
                      {sub && <span className="history-sub">{sub}</span>}
                    </button>
                  </li>
                )
              })}
            </ul>
          ) : (
            <p className="empty-panel-text">아직 지난 요청이 없습니다.</p>
          )}
        </section>
      </aside>

      <section className="trip-canvas" aria-label="여행 계획">
        {hasContent ? (
          <>
            <TripSummaryHeader summary={summary} weather={firstWeather} />
            <PlanCards
              plan={plan}
              onItineraryChange={runId ? handleItineraryChange : undefined}
            />
          </>
        ) : isRunning ? (
          // 카드가 아직 없으면 가운데 세로 진행 표시(가로 배너 대신).
          <div className="canvas-empty">
            <LiveProgress response={lastResolved} />
          </div>
        ) : (
          <div className="canvas-empty">
            <Plane aria-hidden="true" />
            <p>오른쪽에서 여행을 요청하면 여기에 지도·일정·예산이 정리돼 나타납니다.</p>
          </div>
        )}
      </section>

      <section className="chat-dock" aria-label="여행 agent 대화">
        <div className="chat-panel-header">
          <div>
            <p className="eyebrow">여행 agent</p>
            <h1>여행 요청</h1>
          </div>
          <span className="status-badge">{statusBadge}</span>
        </div>

        <div className="chat-thread">
          {turns.length === 0 && !mutation.error && (
            <div className="chat-empty">
              <div className="chat-empty__intro">
                <Bot aria-hidden="true" />
                <div>
                  <h2>어디로 떠나볼까요?</h2>
                  <p>
                    여행 요청을 입력하면 항공·숙소·일정·예산부터 비자·환율·교통권까지
                    한 번에 정리해 드려요.
                  </p>
                </div>
              </div>
            </div>
          )}
          {turns.map((turn) => {
            const active = turn.id === activeTurnId
            return (
              <Fragment key={turn.id}>
                <div className="user-message">
                  <p>{turn.message}</p>
                </div>
                {active && (
                  <div className="assistant-message">
                    <Clock3 aria-hidden="true" />
                    <div className="assistant-progress">
                      <LiveProgress response={turn.response} />
                      <button
                        type="button"
                        className="stop-run-button"
                        onClick={handleCancel}
                      >
                        ⏹ 중지
                      </button>
                    </div>
                  </div>
                )}
                {turn.error && <ErrorState message={turn.error} />}
                {!active && turn.response && <AssistantAnswer data={turn.response} />}
              </Fragment>
            )
          })}
        </div>

        <div className="chat-composer-bar">
          <AgentCommandBox isSubmitting={isRunning} onSubmit={handleSubmit} />
        </div>
      </section>
    </div>
  )
}

const TERMINAL_STATUSES: AgentRunStatus[] = [
  'completed',
  'failed',
  'waiting_for_user',
  'cancelled',
]
function isTerminalStatus(status: AgentRunStatus): boolean {
  return TERMINAL_STATUSES.includes(status)
}

// 진행 단계 → 실제 에이전트 매핑. steps/current_step으로 done/active/skipped/todo를 판정한다.
const PROGRESS_STAGES: { label: string; agents: string[] }[] = [
  { label: '요청 분석', agents: ['IntakeAgent', 'DestinationDiscoveryAgent'] },
  { label: '✈️ 항공권 검색', agents: ['FlightAgent'] },
  { label: '🏨 숙소 검색', agents: ['AccommodationAgent'] },
  { label: '🍴 맛집·관광지', agents: ['RestaurantAgent'] },
  { label: '🗓 일정·예산 정리', agents: ['RouteAgent', 'BudgetAgent'] },
  { label: '📋 마무리', agents: ['PresentationAgent'] },
]

type StageStatus = 'done' | 'active' | 'skipped' | 'todo'

function stageStatus(
  steps: AgentStep[],
  currentStep: string | null | undefined,
  agents: string[],
): StageStatus {
  const relevant = steps.filter((step) => agents.includes(step.agent_name))
  if (agents.includes(currentStep ?? '') || relevant.some((step) => step.status === 'running')) {
    return 'active'
  }
  if (relevant.some((step) => step.status === 'completed')) return 'done'
  if (relevant.length > 0 && relevant.every((step) => step.status === 'skipped')) return 'skipped'
  return 'todo'
}

/** 실제 에이전트 진행(steps/current_step/status)으로 단계별 상태를 표시한다. */
function LiveProgress({ response }: { response?: AgentRunResponse }) {
  const steps = response?.steps ?? []
  const current = response?.current_step
  const done = response?.status != null && isTerminalStatus(response.status)
  // 대화형 질문(직답)이면 계획 단계 대신 간단한 표시만.
  const isAdvisor =
    current === 'TravelAdvisorAgent' || steps.some((s) => s.agent_name === 'TravelAdvisorAgent')
  if (isAdvisor && !done) {
    return (
      <div className="run-progress">
        <div className="run-progress-step active">
          <span className="run-progress-dot" aria-hidden="true" />
          <span>💬 답변을 작성하고 있어요</span>
        </div>
      </div>
    )
  }
  const statuses = PROGRESS_STAGES.map((stage) => {
    const s = stageStatus(steps, current, stage.agents)
    return done && s !== 'skipped' ? 'done' : s
  })
  // 실행 중인데 active로 잡힌 단계가 없으면(시작 직후) 첫 미진행 단계를 active로.
  if (!done && !statuses.includes('active')) {
    const firstTodo = statuses.indexOf('todo')
    if (firstTodo >= 0) statuses[firstTodo] = 'active'
  }
  return (
    <div className="run-progress">
      {PROGRESS_STAGES.map((stage, idx) => (
        <div className={`run-progress-step ${statuses[idx]}`} key={stage.label}>
          <span className="run-progress-dot" aria-hidden="true" />
          <span>
            {stage.label}
            {statuses[idx] === 'skipped' ? ' · 해당 없음' : ''}
          </span>
        </div>
      ))}
    </div>
  )
}

function AssistantAnswer({ data }: { data: AgentRunResponse }) {
  // 대화형 질문이면 LLM이 바로 답한 텍스트를, 아니면 계획 요약을 보여준다.
  const answer = data.partial_plan?.assistant_message?.trim() || buildAgentRunAnswer(data)
  return (
    <section className="assistant-answer-message" aria-label="agent 답변">
      <div className="llm-answer-text" style={{ whiteSpace: 'pre-line' }}>
        {answer}
      </div>
    </section>
  )
}
