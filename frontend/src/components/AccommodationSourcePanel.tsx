import { Database, ShieldCheck } from 'lucide-react'
import type { ProviderStatus } from '../types/provider'
import type { SourceRef } from '../types/common'
import { cleanDisplayText } from '../utils/format'
import { EmptyState } from './EmptyState'

const sourceLabels: Record<string, string> = {
  booking_demand: 'Booking Demand',
  agoda_partner: 'Agoda Partner',
  google_hotels_partner: 'Google Hotels',
  airbnb_public_page: 'Airbnb',
  expedia_rapid: 'Expedia Rapid',
  hotelbeds: 'Hotelbeds',
  mock: 'Mock fallback',
}

const accommodationSourceProviders: ReadonlySet<string> = new Set([
  'expedia_rapid',
  'hotelbeds',
  'booking_demand',
  'agoda_partner',
  'google_hotels_partner',
  'airbnb_public_page',
  'mock_accommodation',
])

export function AccommodationSourcePanel({
  providerStatuses,
  sourceRefs,
  isLoading,
}: {
  readonly providerStatuses: readonly ProviderStatus[]
  readonly sourceRefs: readonly SourceRef[]
  readonly isLoading: boolean
}) {
  const accommodationStatuses = providerStatuses.filter((status) => status.domain === 'accommodations')
  const accommodationRefs = sourceRefs.filter((ref) => accommodationSourceProviders.has(ref.provider))
  const externalStatuses = accommodationStatuses.filter((status) => status.source_type !== 'mock')
  const liveReadyCount = externalStatuses.filter((status) => status.enabled).length
  const mockRefs = accommodationRefs.filter((ref) => ref.is_mock)

  return (
    <section className="card accommodation-source-panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Source policy</p>
          <h2>숙소 source 상태</h2>
        </div>
        <span className="small-badge">{isLoading ? '확인 중' : `${liveReadyCount}개 허용`}</span>
      </div>

      <div className="source-policy-summary">
        <div>
          <ShieldCheck aria-hidden="true" />
          <span>외부 숙소 source</span>
          <strong>{liveReadyCount > 0 ? `${liveReadyCount}개 사용 가능` : 'live 차단'}</strong>
        </div>
        <div>
          <Database aria-hidden="true" />
          <span>현재 결과</span>
          <strong>{mockRefs.length > 0 ? 'mock fallback' : `${accommodationRefs.length}개 ref`}</strong>
        </div>
      </div>

      {accommodationStatuses.length === 0 ? (
        <EmptyState message="숙소 source 정책 정보를 불러오지 못했습니다." />
      ) : (
        <ul className="provider-status-list">
          {accommodationStatuses.map((status) => (
            <li key={status.name} className={status.enabled ? 'provider-enabled' : 'provider-disabled'}>
              <div>
                <strong>{sourceLabels[status.name] ?? cleanDisplayText(status.name)}</strong>
                <span>{sourceTypeLabel(status.source_type)}</span>
              </div>
              <small>{sourceReasonLabel(status)}</small>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function sourceTypeLabel(sourceType: string): string {
  const labels: Record<string, string> = {
    official_api: 'official API',
    partner_api: 'partner API',
    public_page: 'public page',
    mock: 'mock',
  }

  return labels[sourceType] ?? cleanDisplayText(sourceType)
}

function sourceReasonLabel(status: ProviderStatus): string {
  if (status.enabled && status.source_type === 'mock') return '개발/테스트 fallback으로 허용'
  if (status.enabled) return '정책상 사용 가능'
  if (status.reason === 'live providers disabled') return 'live provider 비활성화'
  if (status.reason === 'missing credentials') return 'credential 필요'
  if (status.reason === 'source requires explicit authorization') return '명시 승인 전 차단'
  return cleanDisplayText(status.reason)
}
