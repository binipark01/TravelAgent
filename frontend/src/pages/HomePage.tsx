import { useMutation } from '@tanstack/react-query'
import { Bot, CheckCircle2, Circle, Clock3, Plane, Plus } from 'lucide-react'
import { Fragment, useEffect, useState } from 'react'
import { addAgentRunMessage, createAgentRun } from '../api/agent'
import { AgentCommandBox } from '../components/AgentCommandBox'
import { ErrorState } from '../components/ErrorState'
import { PlanCards } from '../components/PlanCards'
import { TripSummaryHeader } from '../components/TripSummaryHeader'
import type { AgentRunDetailResponse, AgentRunResponse } from '../types/agent'
import type { LLMAnswerRequest } from '../types/llm'
import {
  RUN_STATUS_LABELS,
  buildAgentRunAnswer,
  coreSelectedAgents,
} from '../utils/agentRunDisplay'
import { errorMessage } from '../utils/errors'

const EXAMPLE_PROMPTS = [
  '삿포로 3박4일 여행 계획 짜줘',
  '도쿄 7월 초중순 항공권 찾아줘',
  '오사카 4박5일 숙소 추천해줘',
  '다낭 가족여행 일정이랑 예산 짜줘',
  '삿포로 스스키노 근처 4성급 호텔',
  '방콕 맛집이랑 관광지 알려줘',
] as const

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

  const mutation = useMutation({
    mutationFn: async (vars: {
      payload: LLMAnswerRequest
      turnId: string
    }): Promise<AgentRunResponse> => {
      if (runId) {
        // 이어가기 턴: 같은 run에 메시지 추가 → 백엔드가 기존 상태에 델타만 반영.
        const detail = await addAgentRunMessage(runId, { message: vars.payload.message })
        return adaptDetail(detail)
      }
      // 첫 턴: 새 run 시작.
      const history = turns.map((turn) => turn.message)
      return createAgentRun({ ...vars.payload, history })
    },
    onSuccess: (data, vars) => {
      if (data.run_id) setRunId(data.run_id)
      setTurns((prev) =>
        prev.map((turn) => (turn.id === vars.turnId ? { ...turn, response: data } : turn)),
      )
    },
    onError: (error, vars) =>
      setTurns((prev) =>
        prev.map((turn) =>
          turn.id === vars.turnId ? { ...turn, error: errorMessage(error) } : turn,
        ),
      ),
  })

  function handleSubmit(payload: LLMAnswerRequest) {
    const turnId = nextTurnId()
    setTurns((prev) => [...prev, { id: turnId, message: payload.message }])
    mutation.mutate({ payload, turnId })
  }

  // 중앙 캔버스/좌측 패널은 가장 최근에 '완료된' 응답을 기준으로 보여준다.
  const lastResolved = [...turns].reverse().find((turn) => turn.response)?.response
  const plan = lastResolved?.partial_plan
  const summary = lastResolved?.state_summary
  const firstWeather = plan?.optimized_itinerary?.days?.[0]?.weather ?? null
  const selectedAgents = lastResolved ? coreSelectedAgents(lastResolved) : []
  const latestMessage = turns.length > 0 ? turns[turns.length - 1].message : null
  const statusBadge = mutation.isPending
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
        <button className="new-chat-button" type="button" onClick={() => window.location.assign('/')}>
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
      </aside>

      <section className="trip-canvas" aria-label="여행 계획">
        {plan ? (
          <>
            <TripSummaryHeader summary={summary} weather={firstWeather} />
            <PlanCards plan={plan} />
          </>
        ) : mutation.isPending ? (
          <div className="canvas-empty">
            <RunProgress />
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
                    한 번에 정리해 드려요. 아래 예시를 눌러 바로 시작해도 좋아요.
                  </p>
                </div>
              </div>
              <div className="chat-empty__examples">
                {EXAMPLE_PROMPTS.map((example) => (
                  <button
                    key={example}
                    type="button"
                    className="example-chip"
                    disabled={mutation.isPending}
                    onClick={() =>
                      handleSubmit({
                        message: example,
                        locale: 'ko-KR',
                        currency: 'KRW',
                        timezone: 'Asia/Seoul',
                      })
                    }
                  >
                    {example}
                  </button>
                ))}
              </div>
            </div>
          )}
          {turns.map((turn, index) => {
            const pending =
              index === turns.length - 1 && mutation.isPending && !turn.response && !turn.error
            return (
              <Fragment key={turn.id}>
                <div className="user-message">
                  <p>{turn.message}</p>
                </div>
                {pending && (
                  <div className="assistant-message">
                    <Clock3 aria-hidden="true" />
                    <RunProgress />
                  </div>
                )}
                {turn.error && <ErrorState message={turn.error} />}
                {turn.response && <AssistantAnswer data={turn.response} />}
              </Fragment>
            )
          })}
        </div>

        <div className="chat-composer-bar">
          <AgentCommandBox isSubmitting={mutation.isPending} onSubmit={handleSubmit} />
        </div>
      </section>
    </div>
  )
}

const RUN_STAGES = [
  '요청을 분석하고 있어요',
  '✈️ 항공권을 검색하고 있어요 (네이버·구글)',
  '🏨 숙소를 찾고 있어요',
  '🍴 맛집·관광지를 모으고 있어요',
  '🗓 일정·예산을 정리하고 있어요',
]

function RunProgress() {
  const [index, setIndex] = useState(0)
  useEffect(() => {
    const timer = setInterval(() => {
      setIndex((prev) => Math.min(prev + 1, RUN_STAGES.length - 1))
    }, 8000)
    return () => clearInterval(timer)
  }, [])
  return (
    <div className="run-progress">
      {RUN_STAGES.map((stage, idx) => {
        const status = idx < index ? 'done' : idx === index ? 'active' : 'todo'
        return (
          <div className={`run-progress-step ${status}`} key={stage}>
            <span className="run-progress-dot" aria-hidden="true" />
            <span>{stage}</span>
          </div>
        )
      })}
    </div>
  )
}

function AssistantAnswer({ data }: { data: AgentRunResponse }) {
  return (
    <section className="assistant-answer-message" aria-label="agent 답변">
      <div className="llm-answer-text" style={{ whiteSpace: 'pre-line' }}>
        {buildAgentRunAnswer(data)}
      </div>
    </section>
  )
}
