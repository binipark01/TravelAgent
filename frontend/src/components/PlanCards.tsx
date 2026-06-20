import { Suspense, lazy, useMemo, useState } from 'react'
import type { Itinerary } from '../types/itinerary'
import type { TripPlanState } from '../types/trip'
import { cleanDisplayText } from '../utils/format'
import type { PoiInfoMap } from './DayPlanCard'
import {
  MapFocusContext,
  type MapFocus,
  type MapFocusValue,
  type MapPlacePick,
  type MapRoutePick,
} from './MapFocusContext'
import { AccommodationOptionsCard } from './AccommodationOptionsCard'
import { BudgetBreakdownCard } from './BudgetBreakdownCard'
import { FxCard } from './FxCard'
import { ItineraryTimeline } from './ItineraryTimeline'
import { LocalTransportCard } from './LocalTransportCard'
import { ChecklistCard } from './ChecklistCard'
import { MultiCityCard } from './MultiCityCard'
import { NearbyCard } from './NearbyCard'
import { StayAreaCard } from './StayAreaCard'
import { PlanComparisonCard } from './PlanComparisonCard'
import { RestaurantOptionsCard } from './RestaurantOptionsCard'
import { SafetyCard } from './SafetyCard'
import { TransportTicketsCard } from './TransportTicketsCard'
import { TransportOptionsCard } from './TransportOptionsCard'
import { VisaCard } from './VisaCard'

// 지도(@googlemaps/js-api-loader 포함)는 무거우니 지도가 있을 때만 로드한다.
const MapCard = lazy(() => import('./MapCard').then((m) => ({ default: m.MapCard })))

/** TripPlanState에서 실시간(non-mock) 결과 카드를 렌더한다. 채팅·저장 뷰 공용. */
export function PlanCards({
  plan,
  onItineraryChange,
}: {
  plan?: TripPlanState | null
  onItineraryChange?: (itinerary: Itinerary) => void
}) {
  // 항목 클릭 시 지도가 그 장소로 이동하도록 포커스 상태를 둔다.
  const [focus, setFocus] = useState<MapFocus | null>(null)
  if (!plan) return null
  const flights = (plan.transport_options ?? []).filter((o) => !o.metadata.is_mock)
  const hotels = (plan.accommodation_options ?? []).filter((o) => !o.metadata.source_ref.is_mock)
  const pois = (plan.poi_candidates ?? []).filter((o) => !o.metadata.source_ref.is_mock)
  const activities = (plan.activity_options ?? []).filter((o) => !o.metadata.source_ref.is_mock)
  const budget = plan.budget ?? null
  const itinerary = plan.optimized_itinerary ?? null
  const hasItinerary = (itinerary?.days?.length ?? 0) > 0
  const visa = plan.visa_result ?? null
  const localTransport = plan.local_transport ?? null
  const fx = plan.fx_info ?? null
  const safety = plan.safety_info ?? null
  const nearby = plan.nearby_guide ?? null
  const stayAreas = plan.stay_area_guide ?? null
  const checklist = plan.prep_checklist ?? null
  const multicity = plan.multicity_plan ?? null
  const tickets = plan.transport_tickets ?? null

  // 일정 항목에 평점·추천체류시간을 채우기 위해 후보(맛집·관광지)에서 정보를 끌어온다.
  // 폴링마다(1.2초) 재계산하지 않도록 후보가 바뀔 때만 다시 만든다.
  const poiInfo: PoiInfoMap = useMemo(() => {
    const map: PoiInfoMap = {}
    for (const option of [...pois, ...activities]) {
      map[cleanDisplayText(option.title)] = {
        rating: option.rating ?? null,
        minutes: option.recommended_duration_minutes || null,
      }
    }
    return map
  }, [pois, activities])

  const hasAny =
    flights.length > 0 ||
    hotels.length > 0 ||
    pois.length > 0 ||
    activities.length > 0 ||
    budget != null ||
    hasItinerary ||
    visa != null ||
    localTransport != null ||
    fx != null ||
    safety != null ||
    nearby != null ||
    tickets != null
  if (!hasAny) return null

  const hub = tickets?.hub || plan.selected_destination || ''
  // 지도를 위로 스크롤해 바뀐 위치를 바로 보이게 한다.
  const scrollToMap = () =>
    requestAnimationFrame(() =>
      document
        .getElementById('trip-map-card')
        ?.scrollIntoView({ behavior: 'smooth', block: 'start' }),
    )
  // 한 지점의 지오코딩 쿼리(좌표 있으면 좌표, 없으면 '이름, 도시').
  // 도시(hub)로 고정한다. 식사 항목의 area엔 위치가 아닌 '음식 종류'가 들어가서,
  // 그걸 붙이면 'Le Vent d'Armor, 브르타뉴식' → 브르타뉴로 잘못 지오코딩되기 때문.
  const placeQuery = (place: MapPlacePick) =>
    place.lat != null && place.lng != null
      ? `${place.lat},${place.lng}`
      : [place.label, hub].filter(Boolean).join(', ')

  const selectPlace = (place: MapPlacePick) => {
    setFocus({
      label: place.label,
      query: placeQuery(place),
      lat: place.lat ?? null,
      lng: place.lng ?? null,
      route: null,
    })
    scrollToMap()
  }
  const selectRoute = (route: MapRoutePick) => {
    const stops = route.stops.filter((stop) => stop.label)
    if (stops.length < 2) {
      if (stops[0]) selectPlace(stops[0])
      return
    }
    const queries = stops.map(placeQuery)
    setFocus({
      label: route.label,
      route: {
        origin: queries[0],
        destination: queries[queries.length - 1],
        waypoints: queries.slice(1, -1).slice(0, 8),
        mode: 'transit',
      },
    })
    scrollToMap()
  }
  const focusValue: MapFocusValue = { selectPlace, selectRoute, activeLabel: focus?.label ?? null }

  return (
    <MapFocusContext.Provider value={focusValue}>
      <div className="assistant-detail-cards plan-cards">
        {tickets != null && (
          <Suspense fallback={<div className="card map-loading">지도 불러오는 중…</div>}>
            <MapCard
              key={tickets.hub ?? 'map'}
              guide={tickets}
              focus={focus}
              onReset={() => setFocus(null)}
            />
          </Suspense>
        )}
      {multicity != null && <MultiCityCard plan={multicity} />}
      {hasItinerary && (
        <ItineraryTimeline
          itinerary={itinerary}
          poiInfo={poiInfo}
          onChange={onItineraryChange}
        />
      )}
      {budget != null && <BudgetBreakdownCard budget={budget} />}
      {flights.length >= 2 && hotels.length >= 2 && (
        <PlanComparisonCard flights={flights} hotels={hotels} />
      )}
      {flights.length > 0 && <TransportOptionsCard options={flights} />}
      {hotels.length > 0 && <AccommodationOptionsCard options={hotels} />}
      {stayAreas != null && <StayAreaCard guide={stayAreas} />}
      {activities.length > 0 && (
        <RestaurantOptionsCard options={activities} eyebrow="관광" title="관광지 후보" />
      )}
      {pois.length > 0 && <RestaurantOptionsCard options={pois} />}
      {fx != null && <FxCard fx={fx} />}
      {tickets != null && <TransportTicketsCard guide={tickets} />}
      {localTransport != null && <LocalTransportCard plan={localTransport} />}
      {nearby != null && <NearbyCard guide={nearby} />}
      {visa != null && <VisaCard visa={visa} />}
      {safety != null && <SafetyCard safety={safety} />}
      {checklist != null && <ChecklistCard checklist={checklist} />}
      </div>
    </MapFocusContext.Provider>
  )
}
