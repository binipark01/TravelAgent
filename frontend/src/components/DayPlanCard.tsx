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

export function DayPlanCard({ day }: { day: DayPlan }) {
  const focus = useMapFocus()
  return (
    <article className="day-card">
      <header className="day-card-header">
        <div>
          <h3>{day.day}일차</h3>
          <p>
            {formatDate(day.date)} {day.area ? `· ${day.area}` : ''}
          </p>
        </div>
        {day.weather && <span className="day-weather">{cleanDisplayText(day.weather)}</span>}
      </header>
      <div className="timeline">
        {day.items.map((item) => (
          <ItineraryItemRow item={item} key={item.item_id} />
        ))}
        {day.meals.map((meal) => {
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
                {meal.start_time} - {meal.end_time}
              </time>
              <div>
                <strong>{cleanDisplayText(meal.title)}</strong>
                <p>
                  {mealTypeLabel(meal.meal_type)}
                  {meal.area ? ` · ${cleanDisplayText(meal.area)}` : ''}
                </p>
                {meal.notes[0] && <p className="fine-print">{cleanDisplayText(meal.notes[0])}</p>}
              </div>
            </div>
          )
        })}
        {day.transfers.map((transfer) => (
          <div className="timeline-row transfer-row" key={transfer.item_id}>
            <time>
              {transfer.start_time} - {transfer.end_time}
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
        ))}
        {day.free_time.map((block) => (
          <div className="timeline-row muted" key={block.item_id}>
            <time>
              {block.start_time} - {block.end_time}
            </time>
            <div>
              <strong>{cleanDisplayText(block.title)}</strong>
              <p>휴식 또는 일정 조정 시간</p>
            </div>
          </div>
        ))}
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

export function ItineraryItemRow({ item }: { item: ItineraryItem }) {
  const focus = useMapFocus()
  const trig = placeTriggerProps(focus, {
    label: cleanDisplayText(item.title),
    area: item.location.area ?? item.location.name,
    lat: item.location.latitude,
    lng: item.location.longitude,
  })
  return (
    <div className={`timeline-row ${trig.className}`.trim()} {...trig.interactive}>
      <time>
        {item.start_time} - {item.end_time}
      </time>
      <div>
        <strong>{cleanDisplayText(item.title)}</strong>
        <p>
          {cleanDisplayText(item.location.area ?? item.location.name)} ·{' '}
          {activityTypeLabel(item.type)}
          {item.estimated_cost.amount > 0 ? ` · ${formatMoney(item.estimated_cost)}` : ''}
        </p>
        {item.booking_required && <span className="small-badge">예약 확인 필요</span>}
      </div>
    </div>
  )
}
