import { createContext, useContext, type HTMLAttributes } from 'react'

/** 목록/일정 항목에서 "지도로 보기"로 넘기는 장소 정보. */
export interface MapPlacePick {
  label: string
  area?: string | null
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
