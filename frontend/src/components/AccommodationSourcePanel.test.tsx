import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { AccommodationSourcePanel } from './AccommodationSourcePanel'
import type { SourceRef } from '../types/common'
import type { ProviderStatus } from '../types/provider'

const providerStatuses: ProviderStatus[] = [
  {
    domain: 'accommodations',
    name: 'booking_demand',
    source_type: 'partner_api',
    connector: 'BookingDemandAccommodationConnector',
    configured: true,
    enabled: false,
    missing_credentials: false,
    fallback_to_mock: true,
    status: 'disabled',
    reason: 'live providers disabled',
  },
  {
    domain: 'accommodations',
    name: 'airbnb_public_page',
    source_type: 'public_page',
    connector: 'AirbnbPublicPageAccommodationConnector',
    configured: true,
    enabled: false,
    missing_credentials: true,
    fallback_to_mock: true,
    status: 'disabled',
    reason: 'source requires explicit authorization',
  },
  {
    domain: 'accommodations',
    name: 'mock',
    source_type: 'mock',
    connector: 'MockAccommodationConnector',
    configured: true,
    enabled: true,
    missing_credentials: false,
    fallback_to_mock: true,
    status: 'enabled',
    reason: 'mock allowed only for dev/test/fallback',
  },
]

const sourceRefs: SourceRef[] = [
  {
    source_id: 'src_1',
    provider: 'mock_accommodation',
    title: 'mock accommodation search',
    reference: 'mock-hotel',
    retrieved_at: '2026-06-05T00:00:00Z',
    is_live: false,
    is_mock: true,
    source_type: 'mock',
    confidence: 0.4,
    freshness_note: 'Simulated mock data; verify before booking.',
  },
]

describe('AccommodationSourcePanel', () => {
  it('renders accommodation source policy and mock fallback state', () => {
    render(
      <AccommodationSourcePanel
        providerStatuses={providerStatuses}
        sourceRefs={sourceRefs}
        isLoading={false}
      />,
    )

    expect(screen.getByText('숙소 source 상태')).toBeInTheDocument()
    expect(screen.getByText('live 차단')).toBeInTheDocument()
    expect(screen.getByText('Booking Demand')).toBeInTheDocument()
    expect(screen.getByText('live provider 비활성화')).toBeInTheDocument()
    expect(screen.getByText('Airbnb')).toBeInTheDocument()
    expect(screen.getByText('명시 승인 전 차단')).toBeInTheDocument()
    expect(screen.getByText('Mock fallback')).toBeInTheDocument()
    expect(screen.getByText('mock fallback')).toBeInTheDocument()
  })

  it('counts every registered accommodation source ref when live refs are present', () => {
    render(
      <AccommodationSourcePanel
        providerStatuses={providerStatuses}
        sourceRefs={[
          {
            source_id: 'src_2',
            provider: 'expedia_rapid',
            title: 'Expedia Rapid hotel search',
            reference: 'expedia-hotel',
            retrieved_at: '2026-06-05T00:00:00Z',
            is_live: true,
            is_mock: false,
            source_type: 'partner_api',
            confidence: 0.8,
            freshness_note: 'Live partner API result.',
          },
        ]}
        isLoading={false}
      />,
    )

    expect(screen.getByText('1개 ref')).toBeInTheDocument()
  })
})
