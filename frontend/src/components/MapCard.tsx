import { importLibrary, setOptions } from '@googlemaps/js-api-loader'
import { useEffect, useRef, useState } from 'react'
import type { MapFocus } from './MapFocusContext'

// 같은 키를 JS API에도 사용(프로젝트에 Maps JavaScript API + 결제가 켜져 있어야 함).
const GMAPS_KEY = import.meta.env.VITE_GOOGLE_MAPS_EMBED_KEY as string | undefined

let loadPromise: Promise<void> | null = null
function ensureMaps(key: string): Promise<void> {
  if (!loadPromise) {
    loadPromise = (async () => {
      setOptions({ key })
      await importLibrary('maps')
      await importLibrary('marker')
      await importLibrary('routes')
      await importLibrary('geocoding')
    })()
  }
  return loadPromise
}

// JS API 인증 실패(결제·활성화 안 됨)면 한 번 켜지면 계속 임베드로 폴백한다.
let authFailed = false

/** 임베드(iframe) src — JS API를 못 쓸 때 폴백. 장소/동선/OSM 처리. */
function buildEmbedSrc(
  hub: string,
  hubLat: number | null | undefined,
  hubLng: number | null | undefined,
  focus?: MapFocus | null,
): { src: string | null; kind: string } {
  const focusCoords = focus?.lat != null && focus?.lng != null
  if (GMAPS_KEY && focus?.route) {
    const { origin, destination, waypoints, mode } = focus.route
    const wp = waypoints.length ? `&waypoints=${waypoints.map(encodeURIComponent).join('|')}` : ''
    return {
      src:
        `https://www.google.com/maps/embed/v1/directions?key=${GMAPS_KEY}` +
        `&origin=${encodeURIComponent(origin)}&destination=${encodeURIComponent(destination)}` +
        `${wp}&mode=${mode}`,
      kind: 'Google 지도 · 동선',
    }
  }
  if (GMAPS_KEY) {
    const q = focus ? (focusCoords ? `${focus.lat},${focus.lng}` : focus.query) : hub
    if (q) {
      return {
        src: `https://www.google.com/maps/embed/v1/place?key=${GMAPS_KEY}&q=${encodeURIComponent(q)}&zoom=${focus ? 16 : 12}`,
        kind: 'Google 지도',
      }
    }
  }
  const lat = focusCoords ? (focus?.lat as number) : hubLat
  const lng = focusCoords ? (focus?.lng as number) : hubLng
  if (lat != null && lng != null) {
    const d = focus ? 0.03 : 0.12
    const bbox = `${lng - d},${lat - d * 0.7},${lng + d},${lat + d * 0.7}`
    return {
      src: `https://www.openstreetmap.org/export/embed.html?bbox=${bbox}&layer=mapnik&marker=${lat},${lng}`,
      kind: 'OpenStreetMap',
    }
  }
  return { src: null, kind: '' }
}

/**
 * 목적지 지도 카드. 목적지(hub)만 정해지면 바로 띄운다(교통권 등 나머지 완성 전에도).
 * 기본은 Google Maps JavaScript API(스크롤만으로 확대/축소). 키가 없거나 JS API 인증이
 * 실패하면 자동으로 임베드 iframe으로 폴백한다.
 */
export function MapCard({
  hub,
  hubLat,
  hubLng,
  focus,
  onReset,
}: {
  hub: string
  hubLat?: number | null
  hubLng?: number | null
  focus?: MapFocus | null
  onReset?: () => void
}) {
  const mapDivRef = useRef<HTMLDivElement>(null)
  const objs = useRef<{
    map?: google.maps.Map
    marker?: google.maps.Marker
    geocoder?: google.maps.Geocoder
    directions?: google.maps.DirectionsService
    renderer?: google.maps.DirectionsRenderer
  }>({})
  const [ready, setReady] = useState(false)
  const [jsFailed, setJsFailed] = useState(authFailed)

  const useJs = !!GMAPS_KEY && !jsFailed

  // 지도 생성(1회) + JS 인증 실패 시 임베드로 폴백.
  useEffect(() => {
    if (!useJs || !mapDivRef.current || !hub) return
    let cancelled = false
    ;(window as unknown as { gm_authFailure?: () => void }).gm_authFailure = () => {
      authFailed = true
      setJsFailed(true)
    }
    ensureMaps(GMAPS_KEY as string)
      .then(() => {
        if (cancelled || !mapDivRef.current) return
        const o = objs.current
        if (!o.map) {
          const center =
            hubLat != null && hubLng != null
              ? { lat: hubLat, lng: hubLng }
              : { lat: 35.681, lng: 139.767 }
          o.map = new google.maps.Map(mapDivRef.current, {
            center,
            zoom: 12,
            gestureHandling: 'greedy',
            mapTypeControl: false,
            streetViewControl: false,
            fullscreenControl: true,
          })
          o.geocoder = new google.maps.Geocoder()
          o.directions = new google.maps.DirectionsService()
          o.renderer = new google.maps.DirectionsRenderer()
          o.marker = new google.maps.Marker({ map: o.map, position: center })
          if (hubLat == null && hub) {
            o.geocoder.geocode({ address: hub }, (res, status) => {
              if (status === 'OK' && res && res[0] && o.map && o.marker) {
                o.map.setCenter(res[0].geometry.location)
                o.marker.setPosition(res[0].geometry.location)
              }
            })
          }
        }
        setReady(true)
      })
      .catch(() => setJsFailed(true))
    return () => {
      cancelled = true
    }
  }, [useJs, hub, hubLat, hubLng])

  // focus 적용: 동선이면 경로, 장소면 핀+이동, 없으면 허브.
  useEffect(() => {
    if (!ready || typeof google === 'undefined') return
    const o = objs.current
    if (!o.map) return
    if (focus?.route) {
      const route = focus.route
      o.marker?.setMap(null)
      o.renderer?.setMap(o.map)
      const request = (travelMode: google.maps.TravelMode) => ({
        origin: route.origin,
        destination: route.destination,
        waypoints: route.waypoints.map((w) => ({ location: w, stopover: true })),
        travelMode,
      })
      // 동선은 DRIVING으로 그린다. TRANSIT은 경유지(waypoints)를 지원하지 않아 3곳 이상이면
      // INVALID_REQUEST로 실패하고, WALKING으로 떨어지면 간사이공항 같은 인공섬을 도보로
      // 못 가 도심까지 100km 우회한다. DRIVING은 경유지·다리를 모두 처리해 지리적으로
      // 정상인 선을 만든다. (실제 이동수단/소요시간은 일정 카드의 'JR n분·도보 n분'에 있음)
      const modes = [google.maps.TravelMode.DRIVING, google.maps.TravelMode.WALKING]
      const tryMode = (i: number) => {
        if (i >= modes.length) return
        o.directions?.route(request(modes[i]), (res, status) => {
          if (status === 'OK' && res) o.renderer?.setDirections(res)
          else tryMode(i + 1)
        })
      }
      tryMode(0)
      return
    }
    o.renderer?.setMap(null)
    if (o.map) o.marker?.setMap(o.map)
    const centerOn = (loc: google.maps.LatLng | google.maps.LatLngLiteral) => {
      o.map?.setCenter(loc)
      o.map?.setZoom(focus ? 15 : 12)
      o.marker?.setPosition(loc)
    }
    if (focus?.lat != null && focus?.lng != null) {
      centerOn({ lat: focus.lat, lng: focus.lng })
    } else {
      o.geocoder?.geocode({ address: focus?.query || hub }, (res, status) => {
        if (status === 'OK' && res && res[0]) centerOn(res[0].geometry.location)
      })
    }
  }, [focus, ready, hub])

  if (!hub) return null
  const heading = focus ? focus.label : `${hub} 지도`

  const headerRow = (
    <div className="section-heading">
      <div>
        <p className="eyebrow">지도</p>
        <h2>{heading}</h2>
      </div>
      {focus && onReset && (
        <button type="button" className="map-reset" onClick={onReset}>
          ← 전체 지도
        </button>
      )}
    </div>
  )

  if (!useJs) {
    const { src, kind } = buildEmbedSrc(hub, hubLat, hubLng, focus)
    if (!src) return null
    return (
      <section className="card map-card" id="trip-map-card">
        {headerRow}
        <div className="map-embed">
          <iframe
            key={src}
            title={heading}
            src={src}
            loading="lazy"
            referrerPolicy="no-referrer-when-downgrade"
            allowFullScreen
          />
        </div>
        <p className="visa-disclaimer">
          {focus ? `${focus.label} · ` : ''}
          {kind} · 확대/축소는 Ctrl+스크롤
        </p>
      </section>
    )
  }

  return (
    <section className="card map-card" id="trip-map-card">
      {headerRow}
      <div className="map-embed">
        <div ref={mapDivRef} className="map-js" />
      </div>
      <p className="visa-disclaimer">
        {focus ? `${focus.label} · ` : ''}Google 지도 · 스크롤로 확대/축소, 드래그로 이동
      </p>
    </section>
  )
}
