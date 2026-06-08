import { ShieldCheck } from 'lucide-react'
import type { ApprovalRequest, BookingRecord, BookingSimulationRequest } from '../types/approval'
import { buildBookingCheckRequest } from '../utils/bookingPayload'
import { cleanDisplayText, formatDateTime, formatMoney } from '../utils/format'

interface BookingSimulationPanelProps {
  approvals: ApprovalRequest[]
  booking?: BookingRecord | null
  isSimulating: boolean
  onSimulate: (payload: BookingSimulationRequest) => void
}

function findValidApproval(approvals: ApprovalRequest[]): ApprovalRequest | undefined {
  const now = Date.now()
  return approvals.find(
    (approval) => approval.status === 'approved' && new Date(approval.expires_at).getTime() > now,
  )
}

export function BookingSimulationPanel({
  approvals,
  booking,
  isSimulating,
  onSimulate,
}: BookingSimulationPanelProps) {
  const approval = findValidApproval(approvals)

  return (
    <section className="card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">예약 상태</p>
          <h2>예약 전 확인</h2>
        </div>
      </div>
      <p className="fine-print">
        승인된 예약 전 확인 요청이 있을 때만 실행할 수 있습니다.
      </p>
      <button
        type="button"
        className="primary-button"
        disabled={!approval || isSimulating}
        onClick={() => approval && onSimulate(buildBookingCheckRequest(approval.approval_id))}
      >
        <ShieldCheck aria-hidden="true" />
        {isSimulating ? '확인 중...' : '예약 가능 여부 확인'}
      </button>
      {!approval && (
        <p className="warning-text">
          승인된 예약 전 확인 요청이 필요합니다. 먼저 승인 요청을 만들고 승인하세요.
        </p>
      )}
      {booking && (
        <article className="booking-result">
          <h3>확인 결과</h3>
          <p>확인 번호: {cleanDisplayText(booking.provider_reference) || '-'}</p>
          <p>상태: {booking.status === 'simulated_confirmed' ? '확인 완료' : booking.status}</p>
          <p>가격: {formatMoney(booking.price)}</p>
          <p>확인 시각: {formatDateTime(booking.created_at)}</p>
        </article>
      )}
    </section>
  )
}
