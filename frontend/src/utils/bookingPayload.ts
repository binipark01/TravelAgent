import type { ApprovalCreateRequest, BookingSimulationRequest } from '../types/approval'

export const bookingCheckPayload = {
  hotel_option_id: 'acc_1',
  passport_country: 'KR',
  traveler_identity_confirmed: true,
}

export function buildBookingApprovalRequest(): ApprovalCreateRequest {
  return {
    action_type: 'booking',
    summary: '숙소 예약 전 확인',
    payload: bookingCheckPayload,
    price_ceiling: { amount: 200000, currency: 'KRW' },
    expires_in_hours: 24,
  }
}

export function buildBookingCheckRequest(approvalId: string): BookingSimulationRequest {
  return {
    action_type: 'booking',
    approval_id: approvalId,
    payload: bookingCheckPayload,
    price: { amount: 150000, currency: 'KRW' },
    cancellation_policy_acknowledged: true,
  }
}
