import { describe, expect, it } from 'vitest'
import type { Itinerary } from '../types/itinerary'
import { buildItineraryIcs } from './ics'

const itinerary: Itinerary = {
  summary: '시즈오카 2일 추천 일정',
  feasibility_flags: [],
  days: [
    {
      day: 1,
      date: '2026-08-03',
      area: '시미즈',
      weather: null,
      items: [
        {
          item_id: 'i1',
          title: '니혼다이라 유메테라스',
          type: '전망대',
          location: { name: '시즈오카', country: null, area: '니혼다이라', latitude: null, longitude: null },
          start_time: '10:00:00',
          end_time: '11:15:00',
          estimated_cost: { amount: 0, currency: 'KRW' },
          booking_required: false,
          source_refs: [],
          notes: [],
          feasibility_flags: [],
        },
      ],
      meals: [
        {
          item_id: 'm1',
          meal_type: 'lunch',
          title: '清水港みなみ',
          area: '시미즈',
          start_time: '12:30',
          end_time: '13:30',
          estimated_cost: { amount: 0, currency: 'KRW' },
          source_refs: [],
          notes: [],
        },
      ],
      transfers: [],
      free_time: [],
      notes: [],
    },
  ],
}

describe('buildItineraryIcs', () => {
  it('emits VEVENTs for items and meals with date+time', () => {
    const ics = buildItineraryIcs(itinerary, '시즈오카 일정')
    expect(ics).toContain('BEGIN:VCALENDAR')
    expect(ics).toContain('END:VCALENDAR')
    expect(ics).toContain('X-WR-CALNAME:시즈오카 일정')
    // 관광 항목
    expect(ics).toContain('SUMMARY:니혼다이라 유메테라스')
    expect(ics).toContain('DTSTART:20260803T100000')
    expect(ics).toContain('DTEND:20260803T111500')
    expect(ics).toContain('LOCATION:시즈오카')
    // 식사 항목(점심 라벨)
    expect(ics).toContain('점심 · 清水港みなみ')
    expect(ics).toContain('DTSTART:20260803T123000')
    // VEVENT 2개(관광1 + 식사1)
    expect(ics.match(/BEGIN:VEVENT/g)?.length).toBe(2)
  })

  it('skips days without a date', () => {
    const noDate: Itinerary = {
      ...itinerary,
      days: [{ ...itinerary.days[0], date: null }],
    }
    const ics = buildItineraryIcs(noDate, 'x')
    expect(ics).not.toContain('BEGIN:VEVENT')
  })
})
