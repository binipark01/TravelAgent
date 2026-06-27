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
import { LocalEventsCard } from './LocalEventsCard'
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
  const events = plan.local_events ?? null
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

  const hub = tickets?.hub || plan.selected_destination || ''
  const hasAny =
    !!hub ||
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
  // 지도를 위로 스크롤해 바뀐 위치를 바로 보이게 한다.
  const scrollToMap = () =>
    requestAnimationFrame(() =>
      document
        .getElementById('trip-map-card')
        ?.scrollIntoView({ behavior: 'smooth', block: 'start' }),
    )
  // 그날 지역(교토·린쿠타운 등)을 지오코딩 anchor로 정제한다('근교:'·'·' 제거).
  const cleanRegion = (r?: string | null) =>
    (r || '').replace(/근교\s*:/g, '').replace(/·/g, ' ').trim()

  // 멀티지역 날(area가 '비슈케크·부라나·코치코르·송쿨'처럼 여러 구역을 ·로 이은 오버랜드 날)은
  // 그 연결문자열을 anchor로 쓰면 Google이 첫 토큰(비슈케크)만 잡아 모든 stop이 한 점으로
  // 붕괴한다(부라나·코치코르·송쿨이 전부 비슈케크로 찍힘). 이런 날은 국가(없으면 hub)를 단일
  // anchor로 써야 각 장소가 제 위치에 찍힌다 — 거리가 먼 거점 POI라 국가만으로도 정확히 잡힌다.
  const country = (tickets?.destination_country || '').trim()
  const isMultiRegion = (raw?: string | null) =>
    (raw || '').split('·').filter((s) => s.trim()).length > 1
  // 근교 날 anchor: 멀티지역이면 국가(폴백 hub), 단일 구역이면 그 구역.
  const excursionAnchor = (raw?: string | null) =>
    isMultiRegion(raw) ? country || hub : cleanRegion(raw)

  // 한 장소의 지오코딩 전략. 좌표 있으면 그대로. 없으면 이름 지오코딩인데, 두 경우로 갈린다:
  //  · 같은-도시 날(region이 hub를 포함하거나 region 없음): hub로 anchor + hub 좌표로 bias.
  //    '古町商店街'처럼 흔한 이름은 접미사('…, 니가타')만으론 안 눌려 다른 현(후쿠오카)으로
  //    가버린다. 도시 좌표(hub_lat/lng)로 bounds bias 해야 정확.
  //  · 근교 날(교토 등, region이 hub 미포함): region으로 anchor, bias 없음. hub로 bias하면
  //    교토의 약한 이름(후시미이나리·폰토초)이 오사카로 끌린다.
  const placeFocus = (
    place: MapPlacePick,
  ): { query: string; biasLat: number | null; biasLng: number | null } => {
    if (place.lat != null && place.lng != null) {
      return { query: `${place.lat},${place.lng}`, biasLat: null, biasLng: null }
    }
    const region = cleanRegion(place.region)
    const hubKey = (hub || '').split(/[\s·,]/)[0]
    const sameCity = !region || (!!hubKey && region.includes(hubKey))
    const anchor = sameCity ? hub : excursionAnchor(place.region)
    return {
      query: [place.label, anchor || hub].filter(Boolean).join(', '),
      biasLat: sameCity ? (tickets?.hub_lat ?? null) : null,
      biasLng: sameCity ? (tickets?.hub_lng ?? null) : null,
    }
  }

  const selectPlace = (place: MapPlacePick) => {
    const focusPlace = placeFocus(place)
    setFocus({
      label: place.label,
      query: focusPlace.query,
      lat: place.lat ?? null,
      lng: place.lng ?? null,
      biasLat: focusPlace.biasLat,
      biasLng: focusPlace.biasLng,
      route: null,
    })
    scrollToMap()
  }
  const selectRoute = (route: MapRoutePick) => {
    const stops = route.stops.filter((stop) => stop.label)
    if (stops.length < 1) return
    // 그날 지역(린쿠타운·간사이공항, 교토 등)으로 anchor. 도시 전체(hub)로 잡으면 '고디바 카페'
    // 같은 이름이 시내 다른 지점으로 찍혀 동선이 크게 우회한다. 좌표 있으면 좌표 우선.
    const region = cleanRegion(route.region)
    // 멀티지역 날은 연결문자열 대신 국가(폴백 hub)로 anchor — 안 그러면 모든 stop이 첫 구역으로
    // 붕괴해 동선이 한 점이 된다(부라나·코치코르·송쿨이 전부 비슈케크로). 단일 구역 날은 그대로.
    const routeAnchor = excursionAnchor(route.region) || hub
    const routeQuery = (place: MapPlacePick) =>
      place.lat != null && place.lng != null
        ? `${place.lat},${place.lng}`
        : [place.label, routeAnchor].filter(Boolean).join(', ')
    const queries = stops.map(routeQuery)
    // 동선은 '숙소(본거지)에서 출발'하는 흐름으로 보여준다. 그날 첫 장소가 본거지 권역이
    // 아니면(베르사유 같은 근교·먼 구역 가는 날) 본거지를 출발점으로 앞에 붙여, 숙소→목적지
    // 이동이 한눈에 보이게 한다. 단 첫 장소가 공항이면(도착일) 그대로 둔다(공항→숙소 순서).
    // 본거지는 그날 지역(region)이 아니라 도시(hub)로 지오코딩한다.
    // 본거지명은 '오페라·그랑불바르(Opéra / …)'처럼 ·/·괄호가 섞여 지오코딩이 흔들리므로
    // 괄호·구분자를 떼어 깔끔한 대표명만 쓴다.
    const baseClean = (stayAreas?.areas?.[0]?.name || '')
      .replace(/\(.*?\)/g, '')
      .replace(/[·/]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
    const baseKey = baseClean ? baseClean.split(' ')[0] : ''
    const startsAtBase =
      !!baseKey && (stops[0].label.includes(baseKey) || region.includes(baseKey))
    const firstIsAirport = /공항|空港|airport/i.test(stops[0].label)
    if (baseClean && !startsAtBase && !firstIsAirport) {
      queries.unshift([baseClean, hub].filter(Boolean).join(', '))
    }
    // 그리고 다시 숙소로 돌아오는 것까지 — 마지막 장소가 본거지/공항(출국)이 아니면 본거지를
    // 도착점으로 뒤에 붙여 동선을 숙소로 닫는다(왕복).
    const lastLabel = stops[stops.length - 1].label
    const endsAtBase = !!baseKey && (lastLabel.includes(baseKey) || region.includes(baseKey))
    const lastIsAirport = /공항|空港|airport/i.test(lastLabel)
    if (baseClean && !endsAtBase && !lastIsAirport) {
      queries.push([baseClean, hub].filter(Boolean).join(', '))
    }
    if (queries.length < 2) {
      selectPlace(stops[0])
      return
    }
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
        {hub && (
          <Suspense fallback={<div className="card map-loading">지도 불러오는 중…</div>}>
            <MapCard
              key={hub}
              hub={hub}
              hubLat={tickets?.hub_lat}
              hubLng={tickets?.hub_lng}
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
      {events != null && <LocalEventsCard guide={events} />}
      {visa != null && <VisaCard visa={visa} />}
      {safety != null && <SafetyCard safety={safety} />}
      {checklist != null && <ChecklistCard checklist={checklist} />}
      </div>
    </MapFocusContext.Provider>
  )
}
