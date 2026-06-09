import type { TripPlanState } from '../types/trip'
import { AccommodationOptionsCard } from './AccommodationOptionsCard'
import { BudgetBreakdownCard } from './BudgetBreakdownCard'
import { ItineraryTimeline } from './ItineraryTimeline'
import { PlanComparisonCard } from './PlanComparisonCard'
import { RestaurantOptionsCard } from './RestaurantOptionsCard'
import { TransportOptionsCard } from './TransportOptionsCard'
import { VisaCard } from './VisaCard'

/** TripPlanState에서 실시간(non-mock) 결과 카드를 렌더한다. 채팅·저장 뷰 공용. */
export function PlanCards({ plan }: { plan?: TripPlanState | null }) {
  if (!plan) return null
  const flights = (plan.transport_options ?? []).filter((o) => !o.metadata.is_mock)
  const hotels = (plan.accommodation_options ?? []).filter((o) => !o.metadata.source_ref.is_mock)
  const pois = (plan.poi_candidates ?? []).filter((o) => !o.metadata.source_ref.is_mock)
  const activities = (plan.activity_options ?? []).filter((o) => !o.metadata.source_ref.is_mock)
  const budget = plan.budget ?? null
  const itinerary = plan.optimized_itinerary ?? null
  const hasItinerary = (itinerary?.days?.length ?? 0) > 0
  const visa = plan.visa_result ?? null

  const hasAny =
    flights.length > 0 ||
    hotels.length > 0 ||
    pois.length > 0 ||
    activities.length > 0 ||
    budget != null ||
    hasItinerary ||
    visa != null
  if (!hasAny) return null

  return (
    <div className="assistant-detail-cards" style={{ display: 'grid', gap: 12 }}>
      {flights.length >= 2 && hotels.length >= 2 && (
        <PlanComparisonCard flights={flights} hotels={hotels} />
      )}
      {flights.length > 0 && <TransportOptionsCard options={flights} />}
      {hotels.length > 0 && <AccommodationOptionsCard options={hotels} />}
      {activities.length > 0 && (
        <RestaurantOptionsCard options={activities} eyebrow="관광" title="관광지 후보" />
      )}
      {pois.length > 0 && <RestaurantOptionsCard options={pois} />}
      {hasItinerary && <ItineraryTimeline itinerary={itinerary} />}
      {budget != null && <BudgetBreakdownCard budget={budget} />}
      {visa != null && <VisaCard visa={visa} />}
    </div>
  )
}
