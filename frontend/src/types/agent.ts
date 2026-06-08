import type { TripPlanState } from './trip'

export type AgentRunStatus = 'queued' | 'running' | 'waiting_for_user' | 'completed' | 'failed'
export type AgentStepStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped'
export type AgentEventType =
  | 'user_message'
  | 'agent_started'
  | 'agent_completed'
  | 'agent_failed'
  | 'agent_skipped'
  | 'tool_call_started'
  | 'tool_call_completed'
  | 'source_discovered'
  | 'source_rejected'
  | 'evidence_collected'
  | 'evidence_normalized'
  | 'evidence_ranked'
  | 'missing_info_detected'
  | 'critic_blocker_found'
  | 'approval_required'
  | 'plan_ready'
  | 'run_waiting_for_user'
  | 'run_completed'
  | 'error'

export interface AgentRunCreateRequest {
  message: string
  user_id?: string | null
  locale: string
  currency: string
  timezone: string
  /** 이전 사용자 메시지들(과거→최근 순, 현재 message 제외). 대화 문맥 연속용. */
  history?: string[]
}

export interface AgentRunMessageRequest {
  message: string
}

export interface AgentRun {
  run_id: string
  trip_id: string
  status: AgentRunStatus
  current_step?: string | null
  started_at: string
  completed_at?: string | null
  error_message?: string | null
}

export interface AgentStep {
  step_id: string
  run_id: string
  agent_name: string
  status: AgentStepStatus
  input_summary: string
  output_summary?: string | null
  started_at?: string | null
  completed_at?: string | null
  tool_calls: Array<Record<string, unknown>>
}

export interface AgentEvent {
  event_id: string
  run_id: string
  trip_id: string
  type: AgentEventType
  message: string
  payload: Record<string, unknown>
  created_at: string
}

export interface TripStateSummary {
  destination?: string | null
  origin?: string | null
  date_range?: string | null
  travelers?: number | null
  budget_total?: number | null
  budget_per_person?: number | null
  status: string
  missing_fields: string[]
  assumptions: string[]
}

export interface AgentRunResponse {
  trip_id: string
  run_id: string
  status: AgentRunStatus
  current_step?: string | null
  steps?: AgentStep[]
  missing_fields: string[]
  questions?: string[]
  state_summary?: TripStateSummary | null
  partial_plan?: TripPlanState | null
  events: AgentEvent[]
}

export interface AgentRunDetailResponse {
  run: AgentRun
  steps: AgentStep[]
  events: AgentEvent[]
  state_summary: TripStateSummary
  state: TripPlanState
}
