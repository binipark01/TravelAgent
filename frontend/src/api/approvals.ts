import { apiRequest } from './client'
import type { ApprovalCreateRequest, ApprovalRequest } from '../types/approval'

export function createApproval(
  tripId: string,
  payload: ApprovalCreateRequest,
): Promise<ApprovalRequest> {
  return apiRequest<ApprovalRequest>(`/trips/${tripId}/approvals`, {
    method: 'POST',
    body: payload,
  })
}

export function listApprovals(tripId: string): Promise<ApprovalRequest[]> {
  return apiRequest<ApprovalRequest[]>(`/trips/${tripId}/approvals`)
}

export function approveApproval(tripId: string, approvalId: string): Promise<ApprovalRequest> {
  return apiRequest<ApprovalRequest>(`/trips/${tripId}/approvals/${approvalId}/approve`, {
    method: 'POST',
  })
}

export function rejectApproval(tripId: string, approvalId: string): Promise<ApprovalRequest> {
  return apiRequest<ApprovalRequest>(`/trips/${tripId}/approvals/${approvalId}/reject`, {
    method: 'POST',
  })
}
