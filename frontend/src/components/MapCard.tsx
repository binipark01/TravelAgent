import type { TransportTicketGuide } from '../types/trip'

// 무료 Google Maps Embed 키가 있으면 진짜 구글맵을, 없으면 키 없는 OpenStreetMap을 박는다.
const GMAPS_KEY = import.meta.env.VITE_GOOGLE_MAPS_EMBED_KEY as string | undefined

/** 목적지 지도 카드: 키 있으면 구글맵 Embed, 없으면 OSM(키 불필요)로 폴백. */
export function MapCard({ guide }: { guide?: TransportTicketGuide | null }) {
  if (!guide) return null
  const hub = guide.hub || guide.destination_country

  let src: string | null = null
  let kind = ''
  if (GMAPS_KEY && hub) {
    const q = encodeURIComponent(hub)
    src = `https://www.google.com/maps/embed/v1/place?key=${GMAPS_KEY}&q=${q}&zoom=12`
    kind = 'Google 지도'
  } else if (guide.hub_lat != null && guide.hub_lng != null) {
    const { hub_lat: lat, hub_lng: lng } = guide
    const bbox = `${lng - 0.12},${lat - 0.09},${lng + 0.12},${lat + 0.09}`
    src = `https://www.openstreetmap.org/export/embed.html?bbox=${bbox}&layer=mapnik&marker=${lat},${lng}`
    kind = 'OpenStreetMap'
  }
  if (!src) return null

  return (
    <section className="card map-card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">지도</p>
          <h2>{hub} 지도</h2>
        </div>
      </div>
      <div className="map-embed">
        <iframe
          title={`${hub} 지도`}
          src={src}
          loading="lazy"
          referrerPolicy="no-referrer-when-downgrade"
          allowFullScreen
        />
      </div>
      <p className="visa-disclaimer">
        {kind} · 구간별 길찾기는 위 교통권 카드의 🗺️ 경로 링크를 이용하세요.
      </p>
    </section>
  )
}
