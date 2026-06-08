import { apiRequest } from './client'
import type { BookingRecord, BookingSimulationRequest } from '../types/approval'

export function simulateBooking(
  tripId: string,
  payload: BookingSimulationRequest,
): Promise<BookingRecord> {
  return apiRequest<BookingRecord>(`/trips/${tripId}/bookings/simulate`, {
    method: 'POST',
    body: payload,
  })
}
