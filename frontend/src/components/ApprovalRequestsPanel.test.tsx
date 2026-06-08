import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ApprovalRequestsPanel } from './ApprovalRequestsPanel'
import type { ApprovalRequest } from '../types/approval'

const approvals: ApprovalRequest[] = [
  {
    approval_id: 'approval_pending',
    trip_id: 'trip_1',
    action_type: 'booking',
    summary: '대기 승인',
    exact_payload_hash: 'hash1',
    price_ceiling: { amount: 200000, currency: 'KRW' },
    expires_at: '2026-10-01T00:00:00Z',
    status: 'pending',
  },
  {
    approval_id: 'approval_approved',
    trip_id: 'trip_1',
    action_type: 'booking',
    summary: '승인 완료',
    exact_payload_hash: 'hash2',
    price_ceiling: { amount: 200000, currency: 'KRW' },
    expires_at: '2026-10-01T00:00:00Z',
    status: 'approved',
  },
  {
    approval_id: 'approval_rejected',
    trip_id: 'trip_1',
    action_type: 'booking',
    summary: '거절 완료',
    exact_payload_hash: 'hash3',
    price_ceiling: { amount: 200000, currency: 'KRW' },
    expires_at: '2026-10-01T00:00:00Z',
    status: 'rejected',
  },
]

describe('ApprovalRequestsPanel', () => {
  it('renders pending, approved, and rejected states', () => {
    render(
      <ApprovalRequestsPanel
        approvals={approvals}
        isWorking={false}
        onCreate={vi.fn()}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />,
    )

    expect(screen.getByText('대기')).toBeInTheDocument()
    expect(screen.getAllByText('승인').length).toBeGreaterThan(0)
    expect(screen.getAllByText('거절').length).toBeGreaterThan(0)
  })
})
