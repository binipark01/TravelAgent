import {
  DndContext,
  PointerSensor,
  closestCenter,
  type DragEndEvent,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import {
  SortableContext,
  arrayMove,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import type {
  DayPlan,
  FreeTimeBlock,
  ItineraryItem,
  MealSuggestion,
  TransferSegment,
} from '../types/itinerary'
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

/** "10:00:00" → "10:00" (초 제거 / <input type=time>용). */
function hhmm(value?: string | null): string {
  if (!value) return ''
  const match = value.match(/(\d{1,2}):(\d{2})/)
  return match ? `${match[1].padStart(2, '0')}:${match[2]}` : value
}

function mealTypeLabel(mealType: string): string {
  if (mealType === 'lunch') return '점심'
  if (mealType === 'dinner') return '저녁'
  if (mealType === 'breakfast') return '아침'
  return '식사'
}

// ── 편집용 평면 엔트리 ────────────────────────────────────────────────
type DayEntry =
  | { id: string; kind: 'item'; start: string; end: string; data: ItineraryItem }
  | { id: string; kind: 'meal'; start: string; end: string; data: MealSuggestion }
  | { id: string; kind: 'transfer'; start: string; end: string; data: TransferSegment }
  | { id: string; kind: 'free'; start: string; end: string; data: FreeTimeBlock }

/** 그 날의 관광·식사·이동·자유시간을 한 목록으로 합쳐 시간순 정렬한다. */
function dayEntries(day: DayPlan): DayEntry[] {
  const list: DayEntry[] = [
    ...day.items.map(
      (data): DayEntry => ({ id: data.item_id, kind: 'item', start: data.start_time, end: data.end_time, data }),
    ),
    ...day.meals.map(
      (data): DayEntry => ({ id: data.item_id, kind: 'meal', start: data.start_time, end: data.end_time, data }),
    ),
    ...day.transfers.map(
      (data): DayEntry => ({
        id: data.item_id,
        kind: 'transfer',
        start: data.start_time,
        end: data.end_time,
        data,
      }),
    ),
    ...day.free_time.map(
      (data): DayEntry => ({ id: data.item_id, kind: 'free', start: data.start_time, end: data.end_time, data }),
    ),
  ]
  return list.sort((a, b) => (a.start || '').localeCompare(b.start || ''))
}

/** 편집된 엔트리들을 다시 DayPlan 구조(시간 반영)로 되돌린다. */
function entriesToDay(day: DayPlan, entries: DayEntry[]): DayPlan {
  const withTime = <T,>(entry: DayEntry) =>
    ({ ...(entry.data as T), start_time: entry.start, end_time: entry.end }) as T
  return {
    ...day,
    items: entries.filter((e) => e.kind === 'item').map((e) => withTime<ItineraryItem>(e)),
    meals: entries.filter((e) => e.kind === 'meal').map((e) => withTime<MealSuggestion>(e)),
    transfers: entries.filter((e) => e.kind === 'transfer').map((e) => withTime<TransferSegment>(e)),
    free_time: entries.filter((e) => e.kind === 'free').map((e) => withTime<FreeTimeBlock>(e)),
  }
}

/** 드래그로 순서를 바꾸면, 시간 슬롯(정렬된 시간들)을 새 순서대로 재배정한다. */
function reassignTimes(entries: DayEntry[]): DayEntry[] {
  const slots = entries
    .map((e) => ({ start: e.start, end: e.end }))
    .sort((a, b) => (a.start || '').localeCompare(b.start || ''))
  return entries.map((entry, index) => ({ ...entry, start: slots[index].start, end: slots[index].end }))
}

function entryTitle(entry: DayEntry): string {
  if (entry.kind === 'transfer') {
    return `🚶 ${transportModeLabel(entry.data.mode)} ${entry.data.travel_minutes}분`
  }
  return cleanDisplayText(entry.data.title)
}

function entrySubtitle(entry: DayEntry): string {
  if (entry.kind === 'item') {
    return `${cleanDisplayText(entry.data.location.area ?? entry.data.location.name)} · ${activityTypeLabel(entry.data.type)}`
  }
  if (entry.kind === 'meal') {
    return `${mealTypeLabel(entry.data.meal_type)}${entry.data.area ? ` · ${cleanDisplayText(entry.data.area)}` : ''}`
  }
  if (entry.kind === 'transfer') {
    return '이동'
  }
  return '휴식 또는 일정 조정 시간'
}

/** 장소별 💡 코멘트(관광지·식당)를 모아 일정 아래 '메모' 박스로 정리한다. */
export function collectTips(day: DayPlan): { place: string; text: string }[] {
  const tips: { place: string; text: string }[] = []
  const pull = (title: string, notes: string[]) => {
    const tip = notes.find((note) => note.startsWith('💡'))
    if (tip) {
      tips.push({
        place: cleanDisplayText(title),
        text: cleanDisplayText(tip.replace(/^💡\s*/, '')),
      })
    }
  }
  day.items.forEach((item) => pull(item.title, item.notes))
  day.meals.forEach((meal) => pull(meal.title, meal.notes))
  return tips
}

export function DayPlanCard({
  day,
  poiInfo = {},
  editing = false,
  onDayChange,
}: {
  day: DayPlan
  poiInfo?: PoiInfoMap
  editing?: boolean
  onDayChange?: (day: DayPlan) => void
}) {
  const focus = useMapFocus()
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }))
  const entries = dayEntries(day)

  // 그 날 방문지(관광+식사)를 시간순으로 묶어 동선(경로)으로 쓴다.
  const stops = entries
    .filter((entry) => entry.kind === 'item' || entry.kind === 'meal')
    .map((entry) =>
      entry.kind === 'item'
        ? {
            label: cleanDisplayText(entry.data.title),
            area: entry.data.location.area ?? entry.data.location.name,
            lat: entry.data.location.latitude,
            lng: entry.data.location.longitude,
          }
        : { label: cleanDisplayText(entry.data.title), area: cleanDisplayText(entry.data.area) },
    )

  const commit = (next: DayEntry[]) => onDayChange?.(entriesToDay(day, next))
  const handleDelete = (id: string) => commit(entries.filter((entry) => entry.id !== id))
  const handleTimeChange = (id: string, which: 'start' | 'end', value: string) =>
    commit(entries.map((entry) => (entry.id === id ? { ...entry, [which]: value } : entry)))
  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    if (!over || active.id === over.id) return
    const oldIndex = entries.findIndex((entry) => entry.id === active.id)
    const newIndex = entries.findIndex((entry) => entry.id === over.id)
    if (oldIndex < 0 || newIndex < 0) return
    commit(reassignTimes(arrayMove(entries, oldIndex, newIndex)))
  }

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
          {!editing && focus && stops.length >= 2 && (
            <button
              type="button"
              className="day-route-btn"
              onClick={() =>
                focus.selectRoute({ label: `${day.day}일차 동선`, stops, region: day.area })
              }
            >
              🗺️ 동선 보기
            </button>
          )}
          {day.weather && <span className="day-weather">{cleanDisplayText(day.weather)}</span>}
        </div>
      </header>

      {editing ? (
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <SortableContext
            items={entries.map((entry) => entry.id)}
            strategy={verticalListSortingStrategy}
          >
            <div className="timeline timeline--edit">
              {entries.map((entry) => (
                <SortableEntryRow
                  entry={entry}
                  onDelete={handleDelete}
                  onTimeChange={handleTimeChange}
                  key={entry.id}
                />
              ))}
            </div>
          </SortableContext>
        </DndContext>
      ) : (
        <div className="timeline">
          {entries.map((entry) => {
            if (entry.kind === 'item') {
              return (
                <ItineraryItemRow
                  item={entry.data}
                  info={poiInfo[cleanDisplayText(entry.data.title)]}
                  key={entry.id}
                />
              )
            }
            if (entry.kind === 'meal') {
              const meal = entry.data
              const trig = placeTriggerProps(focus, {
                label: cleanDisplayText(meal.title),
                area: cleanDisplayText(meal.area),
              })
              return (
                <div
                  className={`timeline-row ${trig.className}`.trim()}
                  key={entry.id}
                  {...trig.interactive}
                >
                  <time>
                    {hhmm(meal.start_time)} - {hhmm(meal.end_time)}
                  </time>
                  <div>
                    <strong>{cleanDisplayText(meal.title)}</strong>
                    <span className="meal-tag">{mealTypeLabel(meal.meal_type)}</span>
                  </div>
                </div>
              )
            }
            if (entry.kind === 'transfer') {
              const transfer = entry.data
              return (
                <div className="timeline-row transfer-row" key={entry.id}>
                  <time>
                    {hhmm(transfer.start_time)} - {hhmm(transfer.end_time)}
                  </time>
                  <div>
                    <strong className="transfer-label">
                      🚶 {transportModeLabel(transfer.mode)} {transfer.travel_minutes}분
                    </strong>
                  </div>
                </div>
              )
            }
            const block = entry.data
            return (
              <div className="timeline-row muted" key={entry.id}>
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
      )}

    </article>
  )
}

function SortableEntryRow({
  entry,
  onDelete,
  onTimeChange,
}: {
  entry: DayEntry
  onDelete: (id: string) => void
  onTimeChange: (id: string, which: 'start' | 'end', value: string) => void
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: entry.id,
  })
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  }
  return (
    <div ref={setNodeRef} style={style} className="edit-row">
      <button
        type="button"
        className="drag-handle"
        aria-label="드래그로 순서 변경"
        {...attributes}
        {...listeners}
      >
        ⠿
      </button>
      <div className="edit-times">
        <input
          type="time"
          value={hhmm(entry.start)}
          aria-label="시작 시간"
          onChange={(event) => onTimeChange(entry.id, 'start', event.target.value)}
        />
        <input
          type="time"
          value={hhmm(entry.end)}
          aria-label="종료 시간"
          onChange={(event) => onTimeChange(entry.id, 'end', event.target.value)}
        />
      </div>
      <div className="edit-row__main">
        <strong>{entryTitle(entry)}</strong>
        <p>{entrySubtitle(entry)}</p>
      </div>
      <button
        type="button"
        className="edit-delete"
        aria-label="삭제"
        onClick={() => onDelete(entry.id)}
      >
        ✕
      </button>
    </div>
  )
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
