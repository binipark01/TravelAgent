import type { Money } from '../types/common'

export function formatMoney(value?: Money | null): string {
  if (!value) return '-'
  return new Intl.NumberFormat('ko-KR', {
    style: 'currency',
    currency: value.currency,
    maximumFractionDigits: 0,
  }).format(value.amount)
}

export function formatNumber(value?: number | null, currency = 'KRW'): string {
  if (value === undefined || value === null) return '-'
  return formatMoney({ amount: value, currency })
}

export function formatDateTime(value?: string | null): string {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('ko-KR', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

export function formatFloatingDateTime(value?: string | null): string {
  if (!value) return '-'
  const date = new Date(value.replace(/Z$/, ''))
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('ko-KR', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

export function formatDate(value?: string | null): string {
  if (!value) return '-'
  const date = new Date(`${value}T00:00:00`)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium' }).format(date)
}

export function fieldLabel(field: string): string {
  const labels: Record<string, string> = {
    origin: '출발지',
    destinations: '목적지',
    start_date: '출발일',
    end_date: '귀국일',
    travelers: '여행 인원',
    passport_country: '여권 국적',
  }
  return labels[field] ?? field
}

export function cleanDisplayText(value?: string | null): string {
  if (!value) return ''

  return value
    .replace(
      /계획 생성에 필요한 필수 정보가 없습니다:\s*origin,\s*destinations,\s*start_date,\s*end_date,\s*travelers/gi,
      '계획 생성에 필요한 필수 정보가 없습니다: 출발지, 목적지, 출발일, 귀국일, 여행 인원',
    )
    .replace(/\borigin\b/g, '출발지')
    .replace(/\bdestinations\b/g, '목적지')
    .replace(/\bstart_date\b/g, '출발일')
    .replace(/\bend_date\b/g, '귀국일')
    .replace(/\btravelers\b/g, '여행 인원')
    .replace(/\bJapan\b/g, '일본')
    .replace(/\bSapporo\b/g, '삿포로')
    .replace(/\bOsaka\b/g, '오사카')
    .replace(/\bTokyo\b/g, '도쿄')
    .replace(/\bFukuoka\b/g, '후쿠오카')
    .replace(/\bround-trip\b/gi, '왕복')
    .replace(/\bflights?\s+source\b/gi, '항공 정보 출처')
    .replace(/\baccommodations?\s+source\b/gi, '숙소 정보 출처')
    .replace(/\bplaces?\s+source\b/gi, '현지 장소 출처')
    .replace(/\broutes?\s+source\b/gi, '동선 정보 출처')
    .replace(/\bactivities?\s+source\b/gi, '체험 정보 출처')
    .replace(/\bvisa\s+source\b/gi, '입국 정보 출처')
    .replace(/\bsafety\s+source\b/gi, '안전 정보 출처')
    .replace(/\bsource\b/gi, '출처')
    .replace(/\broute matrix\b/gi, '동선 이동시간 자료')
    .replace(/\baccommodation search\b/gi, '숙소 후보 자료')
    .replace(/\bplaces search\b/gi, '현지 장소 후보 자료')
    .replace(/\bflight search\b/gi, '항공 후보 자료')
    .replace(/\bvisa risk check\b/gi, '입국 리스크 자료')
    .replace(/\bevidence packet\b/gi, '근거 자료')
    .replace(/\bevidence\b/gi, '근거')
    .replace(/\bfreshness\b/gi, '최신성')
    .replace(/\btravel plan run\b/gi, '여행 계획 실행')
    .replace(/\brun\b/gi, '실행')
    .replace(/Live LLM disabled; deterministic fallback used\./gi, '')
    .replace(/LLM extraction failed; deterministic fallback used:/gi, '요청 문장을 규칙 기반으로 정리했습니다:')
    .replace(/mock\/simulated/gi, '')
    .replace(/mock placeholder:\s*/gi, '')
    .replace(/\bmock\b/gi, '')
    .replace(/\bsimulated\b/gi, '')
    .replace(/예약 시뮬레이션 전/g, '예약 전')
    .replace(/source ref/gi, '출처')
    .replace(/provider/gi, '제공처')
    .replace(/passport_country/g, '여권 국적')
    .replace(/여권 국가/g, '여권 국적')
    .replace(/entry requirements must be verified with official sources before booking\.?/gi, '입국 요건은 예약 전 공식 출처 확인이 필요합니다.')
    .replace(/입국 요건은\s*요약이며 공식 확인이 필요합니다\./g, '입국 요건은 공식 확인이 필요합니다.')
    .replace(/모든 가격은\s*추정치입니다\./g, '모든 가격은 추정치입니다.')
    .replace(/\s{2,}/g, ' ')
    .trim()
}

export function travelPurposeLabel(value?: string | null): string {
  if (!value) return ''
  const labels: Record<string, string> = {
    activity: '액티비티',
    culture: '역사/문화',
    food: '맛집',
    nature: '자연',
    rest: '휴양',
    shopping: '쇼핑',
  }
  return value
    .split(',')
    .map((item) => labels[item.trim()] ?? cleanDisplayText(item.trim()))
    .filter(Boolean)
    .join(', ')
}

export function itinerarySummaryLabel(summary?: string | null): string {
  const cleaned = cleanDisplayText(summary).replace(/\bitinerary\b/gi, '일정')
  return cleaned || '일정'
}

export function activityTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    activity: '체험',
    culture: '역사/문화',
    entertainment: '체험',
    food: '식사/맛집',
    shopping: '쇼핑',
    view: '전망',
    transit: '이동',
  }
  return labels[type] ?? cleanDisplayText(type)
}

export function transportModeLabel(mode: string): string {
  const labels: Record<string, string> = {
    transit: '대중교통',
    taxi: '택시',
    walk: '도보',
    bus: '버스',
    subway: '지하철',
    train: '열차',
  }
  return labels[mode] ?? cleanDisplayText(mode)
}
