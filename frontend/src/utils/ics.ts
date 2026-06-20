import type { Itinerary } from '../types/itinerary'

/** 일정을 iCalendar(.ics) 문자열로 변환한다. 구글/애플 캘린더에 import 가능(floating local time). */

function pad(n: number): string {
  return String(n).padStart(2, '0')
}

function escapeText(value: string): string {
  return value.replace(/[\\;,]/g, (m) => `\\${m}`).replace(/\r?\n/g, '\\n')
}

function hms(time?: string | null): string {
  const m = (time || '').match(/(\d{1,2}):(\d{2})(?::(\d{2}))?/)
  if (!m) return '090000'
  return pad(Number(m[1])) + pad(Number(m[2])) + pad(Number(m[3] || '0'))
}

function ymd(date: string): string {
  return date.replace(/-/g, '')
}

function mealLabel(type: string): string {
  if (type === 'lunch') return '점심'
  if (type === 'dinner') return '저녁'
  if (type === 'breakfast') return '아침'
  return '식사'
}

function stamp(): string {
  return new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d+Z$/, 'Z')
}

export function buildItineraryIcs(itinerary: Itinerary, calendarName: string): string {
  const now = stamp()
  const lines: string[] = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//TravelAgent//KO//',
    'CALSCALE:GREGORIAN',
    `X-WR-CALNAME:${escapeText(calendarName)}`,
  ]
  let seq = 0
  const push = (
    date: string,
    title: string,
    start?: string | null,
    end?: string | null,
    location?: string | null,
  ): void => {
    seq += 1
    const d = ymd(date)
    lines.push(
      'BEGIN:VEVENT',
      `UID:travelagent-${d}-${seq}@local`,
      `DTSTAMP:${now}`,
      `DTSTART:${d}T${hms(start)}`,
      `DTEND:${d}T${hms(end || start)}`,
      `SUMMARY:${escapeText(title)}`,
    )
    if (location) lines.push(`LOCATION:${escapeText(location)}`)
    lines.push('END:VEVENT')
  }

  for (const day of itinerary.days) {
    if (!day.date) continue
    for (const item of day.items) {
      push(day.date, item.title, item.start_time, item.end_time, item.location?.name || day.area)
    }
    for (const meal of day.meals) {
      push(
        day.date,
        `🍽 ${mealLabel(meal.meal_type)} · ${meal.title}`,
        meal.start_time,
        meal.end_time,
        meal.area || day.area,
      )
    }
  }
  lines.push('END:VCALENDAR')
  return lines.join('\r\n')
}

export function downloadText(filename: string, content: string, mime: string): void {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}
