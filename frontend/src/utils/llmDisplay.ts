const SOURCE_STATUS_LABELS: Record<string, string> = {
  failed: '확인 실패',
  invalid_source_url: '검색 URL 확인 필요',
  not_configured: '설정 꺼짐',
  not_run: '확인 안 함',
  requires_browser_network: '브라우저 확인 필요',
  restricted: '제한 화면',
  simulated_result: '시뮬레이션 결과',
  candidate_found: '후보 확인',
  completed: '완료',
  needs_user_input: '추가 정보 필요',
} as const

const SOURCE_DOMAIN_LABELS: Record<string, string> = {
  accommodations: '숙소',
  flights: '항공',
} as const

export function sourceStatusLabel(status: string): string {
  return SOURCE_STATUS_LABELS[status] ?? '확인 필요'
}

export function sourceDomainLabel(domain: string | undefined): string {
  if (!domain) return '출처'
  return SOURCE_DOMAIN_LABELS[domain] ?? '출처'
}
