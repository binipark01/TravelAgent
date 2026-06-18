import type { Itinerary } from '../types/itinerary'
import { itinerarySummaryLabel } from '../utils/format'
import { DayPlanCard, type PoiInfoMap } from './DayPlanCard'
import { EmptyState } from './EmptyState'

export function ItineraryTimeline({
  itinerary,
  poiInfo,
}: {
  itinerary?: Itinerary | null
  poiInfo?: PoiInfoMap
}) {
  return (
    <section className="card wide-card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">일차별 플랜</p>
          <h2>일정</h2>
        </div>
      </div>
      {!itinerary || itinerary.days.length === 0 ? (
        <EmptyState message="아직 생성된 일정이 없습니다. 필요한 정보를 보완한 뒤 일정을 생성하세요." />
      ) : (
        <>
          <p className="section-summary">{itinerarySummaryLabel(itinerary.summary)}</p>
          <div className="day-list">
            {itinerary.days.map((day) => (
              <DayPlanCard
                day={day}
                poiInfo={poiInfo}
                key={`${day.day}-${day.date ?? 'no-date'}`}
              />
            ))}
          </div>
        </>
      )}
    </section>
  )
}
