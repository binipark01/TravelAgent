import { apiRequest } from './client'
import type {
  AgentEvent,
  AgentRunCreateRequest,
  AgentRunDetailResponse,
  AgentRunMessageRequest,
  AgentRunResponse,
} from '../types/agent'

export function createAgentRun(payload: AgentRunCreateRequest): Promise<AgentRunResponse> {
  return apiRequest<AgentRunResponse>('/agent/runs', { method: 'POST', body: payload })
}

export function getAgentRun(runId: string): Promise<AgentRunDetailResponse> {
  return apiRequest<AgentRunDetailResponse>(`/agent/runs/${runId}`)
}

export function addAgentRunMessage(
  runId: string,
  payload: AgentRunMessageRequest,
): Promise<AgentRunDetailResponse> {
  return apiRequest<AgentRunDetailResponse>(`/agent/runs/${runId}/messages`, {
    method: 'POST',
    body: payload,
  })
}

export function continueAgentRun(runId: string): Promise<AgentRunDetailResponse> {
  return apiRequest<AgentRunDetailResponse>(`/agent/runs/${runId}/continue`, { method: 'POST' })
}

export function getAgentRunEvents(runId: string): Promise<AgentEvent[]> {
  return apiRequest<AgentEvent[]>(`/agent/runs/${runId}/events`)
}
