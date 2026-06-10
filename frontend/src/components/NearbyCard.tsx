import type { NearbyGuide } from '../types/trip'

/** 근교 당일치기 카드: 허브에서 닿는 근교 명소를 이동시간·교통·하이라이트로 정리. */
export function NearbyCard({ guide }: { guide?: NearbyGuide | null }) {
  if (!guide || guide.destinations.length === 0) return null
  return (
    <section className="card nearby-card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">근교 당일치기</p>
          <h2>{guide.hub} 근교 가볼 만한 곳</h2>
        </div>
      </div>

      <p className="visa-summary">{guide.summary}</p>

      <ul className="nearby-list">
        {guide.destinations.map((dest) => (
          <li key={dest.name} className="nearby-item">
            <div className="nearby-item__head">
              <strong>{dest.name}</strong>
              <span className="nearby-time">🚆 {dest.travel_time}</span>
            </div>
            <div className="nearby-item__meta">
              <span className="nearby-transport">{dest.transport}</span>
              {dest.best_for && <span className="nearby-chip">{dest.best_for}</span>}
            </div>
            {dest.highlights.length > 0 && (
              <div className="nearby-highlights">
                {dest.highlights.map((h) => (
                  <span key={h} className="nearby-tag">
                    {h}
                  </span>
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>

      <p className="visa-disclaimer">
        ⓘ 이동시간·운행은 변동될 수 있어요. 방문 전{' '}
        {guide.source_url ? (
          <a href={guide.source_url} target="_blank" rel="noreferrer">
            현지 관광 공식 정보
          </a>
        ) : (
          '공식 정보'
        )}
        를 확인하세요.
      </p>
    </section>
  )
}
