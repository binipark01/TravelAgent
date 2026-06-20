import { useState } from 'react'
import type { DayPlan, Itinerary } from '../types/itinerary'
import { itinerarySummaryLabel } from '../utils/format'
import { buildItineraryIcs, downloadText } from '../utils/ics'
import { DayPlanCard, type PoiInfoMap } from './DayPlanCard'
import { EmptyState } from './EmptyState'

export function ItineraryTimeline({
  itinerary,
  poiInfo,
  onChange,
}: {
  itinerary?: Itinerary | null
  poiInfo?: PoiInfoMap
  onChange?: (itinerary: Itinerary) => void
}) {
  const [editing, setEditing] = useState(false)
  const editable = typeof onChange === 'function'

  const handleDayChange = (dayIndex: number, nextDay: DayPlan) => {
    if (!itinerary || !onChange) return
    onChange({ ...itinerary, days: itinerary.days.map((d, i) => (i === dayIndex ? nextDay : d)) })
  }

  const hasDays = (itinerary?.days?.length ?? 0) > 0
  const handleExport = () => {
    if (!itinerary) return
    const name = itinerarySummaryLabel(itinerary.summary) || '여행 일정'
    downloadText(`${name}.ics`, buildItineraryIcs(itinerary, name), 'text/calendar;charset=utf-8')
  }

  return (
    <section className="card wide-card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">일차별 플랜</p>
          <h2>일정</h2>
        </div>
        {hasDays && (
          <div className="itinerary-actions">
            <button type="button" className="itinerary-edit-btn" onClick={handleExport}>
              📅 캘린더
            </button>
            {editable && (
              <button
                type="button"
                className="itinerary-edit-btn"
                onClick={() => setEditing((value) => !value)}
              >
                {editing ? '✓ 편집 완료' : '✎ 편집'}
              </button>
            )}
          </div>
        )}
      </div>
      {!itinerary || itinerary.days.length === 0 ? (
        <EmptyState message="아직 생성된 일정이 없습니다. 필요한 정보를 보완한 뒤 일정을 생성하세요." />
      ) : (
        <>
          <p className="section-summary">
            {editing
              ? '드래그로 순서 변경 · 시간 수정 · ✕로 삭제 — 변경은 자동 저장됩니다.'
              : itinerarySummaryLabel(itinerary.summary)}
          </p>
          <div className="day-list">
            {itinerary.days.map((day, index) => (
              <DayPlanCard
                day={day}
                poiInfo={poiInfo}
                editing={editing}
                onDayChange={editing ? (next) => handleDayChange(index, next) : undefined}
                key={`${day.day}-${day.date ?? 'no-date'}`}
              />
            ))}
          </div>
        </>
      )}
    </section>
  )
}
