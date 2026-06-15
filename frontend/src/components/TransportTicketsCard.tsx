import type { TransportTicketGuide } from '../types/trip'

/** 교통권 예매·경로 카드: 구간별 구글맵스 경로 + 지역 예매 플랫폼 + 교통패스 추천. */
export function TransportTicketsCard({ guide }: { guide?: TransportTicketGuide | null }) {
  if (!guide || (guide.platforms.length === 0 && guide.route_links.length === 0)) return null
  return (
    <section className="card tickets-card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">교통권 · 예매</p>
          <h2>이동·예매 — {guide.destination_country}</h2>
        </div>
      </div>

      <p className="visa-summary">{guide.summary}</p>

      {guide.pass_suggestion && (
        <a
          className="pass-banner"
          href={guide.pass_suggestion.url}
          target="_blank"
          rel="noreferrer"
        >
          <strong>🎫 {guide.pass_suggestion.name}</strong>
          <span>{guide.pass_suggestion.note}</span>
        </a>
      )}

      {guide.route_links.length > 0 && (
        <>
          <p className="transit-group-label">구간별 경로</p>
          <ul className="ticket-route-list">
            {guide.route_links.map((route) => (
              <li key={route.label} className="ticket-route">
                <span className="ticket-route__label">{route.label}</span>
                <span className="ticket-route__links">
                  <a href={route.maps_url} target="_blank" rel="noreferrer">
                    🗺️ 경로
                  </a>
                  {route.booking_url && (
                    <a href={route.booking_url} target="_blank" rel="noreferrer">
                      🔎 비교
                    </a>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}

      {guide.platforms.length > 0 && (
        <>
          <p className="transit-group-label">예매 플랫폼</p>
          <ul className="ticket-platform-list">
            {guide.platforms.map((platform) => (
              <li key={platform.name}>
                <a href={platform.url} target="_blank" rel="noreferrer">
                  <strong>{platform.name}</strong>
                </a>
                <span className="ticket-platform__covers">{platform.covers}</span>
                {platform.note && <span className="ticket-platform__note">{platform.note}</span>}
              </li>
            ))}
          </ul>
        </>
      )}

      <p className="visa-disclaimer">ⓘ {guide.source_note}</p>
    </section>
  )
}
