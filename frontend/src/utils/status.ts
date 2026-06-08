import type { TripStatus } from '../types/common'

const tripStatusLabels: Record<TripStatus, string> = {
  intake: '기본 정보 정리 중',
  needs_user_input: '추가 정보 필요',
  researching: '후보 탐색 중',
  drafting: '일정 생성 중',
  validating: '검증 중',
  needs_approval: '승인 필요',
  ready: '계획 준비 완료',
  booking_in_progress: '예약 확인 중',
  completed: '완료',
  failed: '실패',
}

export function tripStatusLabel(status: TripStatus): string {
  return tripStatusLabels[status]
}
