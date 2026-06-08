import { Check, Plus, X } from 'lucide-react'
import type { ApprovalCreateRequest, ApprovalRequest } from '../types/approval'
import { buildBookingApprovalRequest } from '../utils/bookingPayload'
import { formatDateTime, formatMoney } from '../utils/format'
import { EmptyState } from './EmptyState'

interface ApprovalRequestsPanelProps {
  approvals: ApprovalRequest[]
  isWorking: boolean
  onCreate: (payload: ApprovalCreateRequest) => void
  onApprove: (approvalId: string) => void
  onReject: (approvalId: string) => void
}

const statusLabels: Record<ApprovalRequest['status'], string> = {
  pending: '대기',
  approved: '승인',
  rejected: '거절',
  expired: '만료',
}

export function ApprovalRequestsPanel({
  approvals,
  isWorking,
  onCreate,
  onApprove,
  onReject,
}: ApprovalRequestsPanelProps) {
  return (
    <section className="card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">예약 전 확인</p>
          <h2>승인 요청</h2>
        </div>
      </div>
      <button
        type="button"
        className="secondary-button"
        onClick={() => onCreate(buildBookingApprovalRequest())}
        disabled={isWorking}
      >
        <Plus aria-hidden="true" />
        예약 전 확인 요청 생성
      </button>
      {approvals.length === 0 ? (
        <EmptyState message="예약 가능 여부 확인을 실행하려면 먼저 승인 요청이 필요합니다." />
      ) : (
        <div className="approval-list">
          {approvals.map((approval) => (
            <article className="approval-card" key={approval.approval_id}>
              <header>
                <strong>{approval.summary}</strong>
                <span className={`small-badge approval-${approval.status}`}>
                  {statusLabels[approval.status]}
                </span>
              </header>
              <p>만료: {formatDateTime(approval.expires_at)}</p>
              <p>가격 상한: {formatMoney(approval.price_ceiling)}</p>
              <div className="inline-actions">
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => onApprove(approval.approval_id)}
                  disabled={isWorking || approval.status !== 'pending'}
                >
                  <Check aria-hidden="true" />
                  승인
                </button>
                <button
                  type="button"
                  className="ghost-button"
                  onClick={() => onReject(approval.approval_id)}
                  disabled={isWorking || approval.status !== 'pending'}
                >
                  <X aria-hidden="true" />
                  거절
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}
