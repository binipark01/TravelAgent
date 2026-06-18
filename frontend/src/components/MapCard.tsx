import type { TransportTicketGuide } from '../types/trip'
import type { MapFocus } from './MapFocusContext'

// 무료 Google Maps Embed 키가 있으면 진짜 구글맵을, 없으면 키 없는 OpenStreetMap을 박는다.
const GMAPS_KEY = import.meta.env.VITE_GOOGLE_MAPS_EMBED_KEY as string | undefined

/**
 * 목적지 지도 카드. focus가 있으면 그 장소로 이동(핀), 없으면 허브(도시) 전체를 보여준다.
 * 키 있으면 구글맵 Embed, 없으면 OSM(좌표 필요)로 폴백.
 */
export function MapCard({
  guide,
  focus,
  onReset,
}: {
  guide?: TransportTicketGuide | null
  focus?: MapFocus | null
  onReset?: () => void
}) {
  if (!guide) return null
  const hub = guide.hub || guide.destination_country
  const focusCoords = focus?.lat != null && focus?.lng != null

  let src: string | null = null
  let kind = ''
  if (GMAPS_KEY) {
    const q = focus ? (focusCoords ? `${focus.lat},${focus.lng}` : focus.query) : hub
    if (q) {
      const zoom = focus ? 16 : 12
      src = `https://www.google.com/maps/embed/v1/place?key=${GMAPS_KEY}&q=${encodeURIComponent(q)}&zoom=${zoom}`
      kind = 'Google 지도'
    }
  }
  if (!src) {
    // 키 없음 → OSM 폴백(좌표가 있어야 핀 가능, 없으면 허브)
    const lat = focusCoords ? (focus?.lat as number) : guide.hub_lat
    const lng = focusCoords ? (focus?.lng as number) : guide.hub_lng
    if (lat != null && lng != null) {
      const d = focus ? 0.03 : 0.12
      const bbox = `${lng - d},${lat - d * 0.7},${lng + d},${lat + d * 0.7}`
      src = `https://www.openstreetmap.org/export/embed.html?bbox=${bbox}&layer=mapnik&marker=${lat},${lng}`
      kind = 'OpenStreetMap'
    }
  }
  if (!src) return null

  const heading = focus ? focus.label : `${hub} 지도`
  return (
    <section className="card map-card" id="trip-map-card">
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
        {kind} · 항목을 누르면 지도가 그 장소로 이동합니다.
      </p>
    </section>
  )
}
