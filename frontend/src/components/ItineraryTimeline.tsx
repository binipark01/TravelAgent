import { useEffect, useMemo, useState } from 'react'
import type { DayPlan, Itinerary } from '../types/itinerary'
import { itinerarySummaryLabel } from '../utils/format'
import { buildItineraryIcs, downloadText } from '../utils/ics'
import { DayPlanCard, collectTips, type PoiInfoMap } from './DayPlanCard'
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

  // 좁은 화면에선 1열(순서대로), 넓은 화면에선 2열(번갈아 배치)로 카드를 깐다.
  const [twoCol, setTwoCol] = useState(
    () => typeof window !== 'undefined' && window.innerWidth >= 860,
  )
  useEffect(() => {
    const onResize = () => setTwoCol(window.innerWidth >= 860)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const handleDayChange = (dayIndex: number, nextDay: DayPlan) => {
    if (!itinerary || !onChange) return
    onChange({ ...itinerary, days: itinerary.days.map((d, i) => (i === dayIndex ? nextDay : d)) })
  }

  const hasDays = (itinerary?.days?.length ?? 0) > 0

  // 장소별 💡 메모를 일정 카드마다 흩뿌리지 않고, 일정 아래에 '메모' 박스 하나로 모아 정리한다.
  const memoByDay = useMemo(() => {
    if (!itinerary) return []
    return itinerary.days
      .map((day) => ({ day: day.day, area: day.area, tips: collectTips(day) }))
      .filter((group) => group.tips.length > 0)
  }, [itinerary])

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
          {!editing && (itinerary.feasibility_flags?.length ?? 0) > 0 && (
            <div className="itinerary-warnings" role="alert">
              {itinerary.feasibility_flags.map((flag) => (
                <p className="itinerary-warning" key={flag}>
                  ⚠ {flag.replace(/^\[검증\]\s*/, '')}
                </p>
              ))}
            </div>
          )}
          <div className="day-list">
            {(twoCol ? [0, 1] : [0]).map((col) => (
              <div className="day-col" key={col}>
                {itinerary.days
                  .map((day, index) => ({ day, index }))
                  .filter(({ index }) => !twoCol || index % 2 === col)
                  .map(({ day, index }) => (
                    <DayPlanCard
                      day={day}
                      poiInfo={poiInfo}
                      editing={editing}
                      onDayChange={editing ? (next) => handleDayChange(index, next) : undefined}
                      key={`${day.day}-${day.date ?? 'no-date'}`}
                    />
                  ))}
              </div>
            ))}
          </div>
          {!editing && memoByDay.length > 0 && (
            <div className="itinerary-memo">
              <p className="itinerary-memo__title">💡 장소별 메모</p>
              <div className="itinerary-memo__grid">
                {memoByDay.map((group) => (
                  <div className="itinerary-memo__day" key={group.day}>
                    <p className="itinerary-memo__day-label">
                      {group.day}일차{group.area ? ` · ${group.area}` : ''}
                    </p>
                    {group.tips.map((tip) => (
                      <p className="itinerary-memo__tip" key={`${tip.place}-${tip.text}`}>
                        <span className="itinerary-memo__place">{tip.place}</span> {tip.text}
                      </p>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </section>
  )
}
