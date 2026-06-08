import { apiRequest } from './client'
import type {
  FinalPlanResponse,
  TripCreateRequest,
  TripMessageRequest,
  TripSummaryResponse,
} from '../types/trip'
import type { CriticFinding } from '../types/common'

export function createTrip(payload: TripCreateRequest): Promise<TripSummaryResponse> {
  return apiRequest<TripSummaryResponse>('/trips', { method: 'POST', body: payload })
}

export function getTrip(tripId: string): Promise<TripSummaryResponse> {
  return apiRequest<TripSummaryResponse>(`/trips/${tripId}`)
}

export function addTripMessage(
  tripId: string,
  payload: TripMessageRequest,
): Promise<TripSummaryResponse> {
  return apiRequest<TripSummaryResponse>(`/trips/${tripId}/messages`, {
    method: 'POST',
    body: payload,
  })
}

export function planTrip(tripId: string): Promise<FinalPlanResponse> {
  return apiRequest<FinalPlanResponse>(`/trips/${tripId}/plan`, { method: 'POST' })
}

export function validateTrip(tripId: string): Promise<CriticFinding[]> {
  return apiRequest<CriticFinding[]>(`/trips/${tripId}/validate`, { method: 'POST' })
}
