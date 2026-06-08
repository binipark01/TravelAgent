import type { Money } from './common'

export type ApprovalStatus = 'pending' | 'approved' | 'rejected' | 'expired'

export interface ApprovalRequest {
  approval_id: string
  trip_id: string
  action_type: string
  summary: string
  exact_payload_hash: string
  price_ceiling?: Money | null
  expires_at: string
  status: ApprovalStatus
  approved_at?: string | null
  rejected_at?: string | null
}

export interface ApprovalCreateRequest {
  action_type: string
  summary: string
  payload: Record<string, unknown>
  price_ceiling?: Money | null
  expires_in_hours?: number
}

export interface BookingSimulationRequest {
  action_type: string
  payload: Record<string, unknown>
  approval_id?: string | null
  price: Money
  cancellation_policy_acknowledged: boolean
}

export interface BookingRecord {
  booking_id: string
  trip_id: string
  approval_id: string
  action_type: string
  provider_reference: string
  simulated: boolean
  status: string
  price: Money
  created_at: string
  notes: string[]
}
