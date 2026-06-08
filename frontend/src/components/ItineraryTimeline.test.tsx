import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ItineraryTimeline } from './ItineraryTimeline'
import type { Itinerary } from '../types/itinerary'

const itinerary: Itinerary = {
  summary: '오사카 2일 일정',
  feasibility_flags: [],
  days: [
    {
      day: 1,
      date: '2026-10-03',
      area: 'Namba',
      notes: ['도착일 버퍼 포함'],
      items: [
        {
          item_id: 'item_1',
          title: 'Dotonbori Food Walk',
          type: 'food',
          location: { name: 'Dotonbori', area: 'Namba', country: 'Japan' },
          start_time: '10:00:00',
          end_time: '12:00:00',
          estimated_cost: { amount: 30000, currency: 'KRW' },
          booking_required: false,
          source_refs: [],
          notes: [],
          feasibility_flags: [],
        },
      ],
      meals: [],
      transfers: [],
      free_time: [],
    },
  ],
}

describe('ItineraryTimeline', () => {
  it('renders day plans', () => {
    render(<ItineraryTimeline itinerary={itinerary} />)

    expect(screen.getByText('1일차')).toBeInTheDocument()
    expect(screen.getByText('Dotonbori Food Walk')).toBeInTheDocument()
  })
})
