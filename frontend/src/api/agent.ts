import { apiRequest } from './client'
import type {
  AgentEvent,
  AgentRunCreateRequest,
  AgentRunDetailResponse,
  AgentRunMessageRequest,
  AgentRunResponse,
  AgentRunSummary,
} from '../types/agent'
import type { Itinerary } from '../types/itinerary'

export function updateItinerary(
  runId: string,
  itinerary: Itinerary,
): Promise<AgentRunDetailResponse> {
  return apiRequest<AgentRunDetailResponse>(`/agent/runs/${runId}/itinerary`, {
    method: 'POST',
    body: itinerary,
  })
}

export function createAgentRun(payload: AgentRunCreateRequest): Promise<AgentRunResponse> {
  return apiRequest<AgentRunResponse>('/agent/runs', { method: 'POST', body: payload })
}

export function listAgentRuns(limit = 30): Promise<AgentRunSummary[]> {
  return apiRequest<AgentRunSummary[]>(`/agent/runs?limit=${limit}`)
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
