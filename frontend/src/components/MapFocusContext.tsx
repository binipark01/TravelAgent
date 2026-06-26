import { createContext, useContext, type HTMLAttributes } from 'react'

/** 목록/일정 항목에서 "지도로 보기"로 넘기는 장소 정보. */
export interface MapPlacePick {
  label: string
  area?: string | null
  // 그날 지역(예: '교토 동남부·히가시야마'). 좌표 없는 장소를 도시(hub)가 아니라 이 지역으로
  // 지오코딩 anchor 해서, 교토 같은 근교 날의 장소가 hub(오사카)로 잘못 찍히는 걸 막는다.
  region?: string | null
  lat?: number | null
  lng?: number | null
}

/** 하루 일정의 방문지들을 순서대로 묶은 동선(경로) 선택. */
export interface MapRoutePick {
  label: string
  stops: MapPlacePick[]
  // 그날 지역(예: '린쿠타운·간사이공항'). 좌표 없는 장소를 도시 전체가 아니라 이 지역으로
  // 지오코딩 anchor 해서, 같은 이름이 시내 다른 곳으로 잘못 찍히는 우회를 막는다.
  region?: string | null
}

/** MapCard가 실제로 띄우는 포커스: 단일 장소(query/좌표) 또는 동선(route). */
export interface MapFocus {
  label: string
  query?: string
  lat?: number | null
  lng?: number | null
  // 이름 지오코딩을 이 좌표 주변으로 bias(bounds). 같은-도시 날의 흔한 이름(예: '古町商店街')이
  // 다른 현(후쿠오카)으로 잘못 찍히는 걸 막는다. 도시 좌표(hub_lat/lng, Open-Meteo)를 쓴다.
  biasLat?: number | null
  biasLng?: number | null
  route?: { origin: string; destination: string; waypoints: string[]; mode: string } | null
}

export interface MapFocusValue {
  selectPlace: (place: MapPlacePick) => void
  selectRoute: (route: MapRoutePick) => void
  activeLabel: string | null
}

// Provider가 없으면(다른 페이지) null → 항목이 클릭 불가가 된다.
export const MapFocusContext = createContext<MapFocusValue | null>(null)

export function useMapFocus(): MapFocusValue | null {
  return useContext(MapFocusContext)
}

/** 클릭 가능한 장소 요소에 붙일 className/핸들러를 만든다(provider 없으면 빈 값). */
export function placeTriggerProps(
  focus: MapFocusValue | null,
  place: MapPlacePick,
): { className: string; interactive: HTMLAttributes<HTMLElement> } {
  if (!focus || !place.label) return { className: '', interactive: {} }
  const active = focus.activeLabel === place.label
  return {
    className: `place-clickable${active ? ' place-active' : ''}`,
    interactive: {
      role: 'button',
      tabIndex: 0,
      title: '지도에서 보기',
      onClick: () => focus.selectPlace(place),
      onKeyDown: (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          focus.selectPlace(place)
        }
      },
    },
  }
}
