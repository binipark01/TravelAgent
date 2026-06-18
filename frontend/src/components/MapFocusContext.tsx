import { createContext, useContext, type HTMLAttributes } from 'react'

/** 목록/일정 항목에서 "지도로 보기"로 넘기는 장소 정보. */
export interface MapPlacePick {
  label: string
  area?: string | null
  lat?: number | null
  lng?: number | null
}

/** MapCard가 실제로 띄우는 포커스(지오코딩 쿼리 + 선택적 좌표). */
export interface MapFocus {
  label: string
  query: string
  lat?: number | null
  lng?: number | null
}

export interface MapFocusValue {
  selectPlace: (place: MapPlacePick) => void
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
