import type { TripStatus } from '../types/common'
import { tripStatusLabel } from '../utils/status'

export function TripStatusBadge({ status }: { status: TripStatus }) {
  return <span className={`status-badge status-${status}`}>{tripStatusLabel(status)}</span>
}
