import type { ItineraryItem } from '../types/itinerary'
import type { DayPlan } from '../types/itinerary'
import {
  activityTypeLabel,
  cleanDisplayText,
  formatDate,
  formatMoney,
  transportModeLabel,
} from '../utils/format'
import { placeTriggerProps, useMapFocus } from './MapFocusContext'

export interface PoiInfo {
  rating: number | null
  minutes: number | null
}
export type PoiInfoMap = Record<string, PoiInfo>

function durationLabel(minutes: number): string {
  if (minutes >= 60) {
    const hours = minutes / 60
    return `추천 ~${Number.isInteger(hours) ? hours : hours.toFixed(1)}시간`
  }
  return `추천 ~${minutes}분`
}

/** "10:00:00" → "10:00" (초 제거). */
function hhmm(value?: string | null): string {
  if (!value) return ''
  const match = value.match(/(\d{1,2}):(\d{2})/)
  return match ? `${match[1].padStart(2, '0')}:${match[2]}` : value
}

export function DayPlanCard({ day, poiInfo = {} }: { day: DayPlan; poiInfo?: PoiInfoMap }) {
  const focus = useMapFocus()
  // 그 날 방문지(관광+식사)를 시간순으로 묶어 동선(경로)으로 쓴다.
  const stops = [
    ...day.items.map((item) => ({
      t: item.start_time,
      place: {
        label: cleanDisplayText(item.title),
        area: item.location.area ?? item.location.name,
        lat: item.location.latitude,
        lng: item.location.longitude,
      },
    })),
    ...day.meals.map((meal) => ({
      t: meal.start_time,
      place: { label: cleanDisplayText(meal.title), area: cleanDisplayText(meal.area) },
    })),
  ]
    .sort((a, b) => (a.t || '').localeCompare(b.t || ''))
    .map((entry) => entry.place)

  return (
    <article className="day-card">
      <header className="day-card-header">
        <div>
          <h3>{day.day}일차</h3>
          <p>
            {formatDate(day.date)} {day.area ? `· ${day.area}` : ''}
          </p>
        </div>
        <div className="day-card-header__right">
          {focus && stops.length >= 2 && (
            <button
              type="button"
              className="day-route-btn"
              onClick={() => focus.selectRoute({ label: `${day.day}일차 동선`, stops })}
            >
              🗺️ 동선 보기
            </button>
          )}
          {day.weather && <span className="day-weather">{cleanDisplayText(day.weather)}</span>}
        </div>
      </header>
      <div className="timeline">
        {[
          ...day.items.map((item) => ({ t: item.start_time, kind: 'item' as const, item })),
          ...day.meals.map((meal) => ({ t: meal.start_time, kind: 'meal' as const, meal })),
          ...day.transfers.map((transfer) => ({
            t: transfer.start_time,
            kind: 'transfer' as const,
            transfer,
          })),
          ...day.free_time.map((block) => ({ t: block.start_time, kind: 'free' as const, block })),
        ]
          .sort((a, b) => (a.t || '').localeCompare(b.t || ''))
          .map((entry) => {
            if (entry.kind === 'item') {
              return (
                <ItineraryItemRow
                  item={entry.item}
                  info={poiInfo[cleanDisplayText(entry.item.title)]}
                  key={entry.item.item_id}
                />
              )
            }
            if (entry.kind === 'meal') {
              const meal = entry.meal
              const trig = placeTriggerProps(focus, {
                label: cleanDisplayText(meal.title),
                area: cleanDisplayText(meal.area),
              })
              return (
                <div
                  className={`timeline-row muted ${trig.className}`.trim()}
                  key={meal.item_id}
                  {...trig.interactive}
                >
                  <time>
                    {hhmm(meal.start_time)} - {hhmm(meal.end_time)}
                  </time>
                  <div>
                    <strong>{cleanDisplayText(meal.title)}</strong>
                    <p>
                      {mealTypeLabel(meal.meal_type)}
                      {meal.area ? ` · ${cleanDisplayText(meal.area)}` : ''}
                    </p>
                    {meal.notes[0] && (
                      <p className="fine-print">{cleanDisplayText(meal.notes[0])}</p>
                    )}
                  </div>
                </div>
              )
            }
            if (entry.kind === 'transfer') {
              const transfer = entry.transfer
              return (
                <div className="timeline-row transfer-row" key={transfer.item_id}>
                  <time>
                    {hhmm(transfer.start_time)} - {hhmm(transfer.end_time)}
                  </time>
                  <div>
                    <strong>
                      {cleanDisplayText(transfer.origin)} → {cleanDisplayText(transfer.destination)}
                    </strong>
                    <p>
                      {transportModeLabel(transfer.mode)} · 이동 {transfer.travel_minutes}분
                    </p>
                  </div>
                </div>
              )
            }
            const block = entry.block
            return (
              <div className="timeline-row muted" key={block.item_id}>
                <time>
                  {hhmm(block.start_time)} - {hhmm(block.end_time)}
                </time>
                <div>
                  <strong>{cleanDisplayText(block.title)}</strong>
                  <p>휴식 또는 일정 조정 시간</p>
                </div>
              </div>
            )
          })}
      </div>
      {day.notes.length > 0 && (
        <ul className="text-list compact">
          {day.notes.map((note) => (
            <li key={note}>{cleanDisplayText(note)}</li>
          ))}
        </ul>
      )}
    </article>
  )
}

function mealTypeLabel(mealType: string): string {
  if (mealType === 'lunch') return '점심'
  if (mealType === 'dinner') return '저녁'
  if (mealType === 'breakfast') return '아침'
  return '식사'
}

export function ItineraryItemRow({ item, info }: { item: ItineraryItem; info?: PoiInfo }) {
  const focus = useMapFocus()
  const trig = placeTriggerProps(focus, {
    label: cleanDisplayText(item.title),
    area: item.location.area ?? item.location.name,
    lat: item.location.latitude,
    lng: item.location.longitude,
  })
  const cost = item.estimated_cost.amount > 0 ? formatMoney(item.estimated_cost) : null
  const hasMeta = info?.rating != null || (info?.minutes ?? 0) > 0 || cost != null
  return (
    <div className={`timeline-row ${trig.className}`.trim()} {...trig.interactive}>
      <time>
        {hhmm(item.start_time)} - {hhmm(item.end_time)}
      </time>
      <div>
        <strong>{cleanDisplayText(item.title)}</strong>
        <p>
          {cleanDisplayText(item.location.area ?? item.location.name)} ·{' '}
          {activityTypeLabel(item.type)}
        </p>
        {item.booking_required && <span className="small-badge">예약 확인 필요</span>}
      </div>
      {hasMeta && (
        <div className="timeline-row__meta">
          {info?.rating != null && <span className="timeline-rating">★ {info.rating.toFixed(1)}</span>}
          {(info?.minutes ?? 0) > 0 && (
            <span className="timeline-sub">{durationLabel(info?.minutes as number)}</span>
          )}
          {cost != null && <span className="timeline-sub">{cost}</span>}
        </div>
      )}
    </div>
  )
}
