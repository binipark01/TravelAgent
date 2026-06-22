import type { NearbyGuide } from '../types/trip'
import { cleanDisplayText } from '../utils/format'
import { placeTriggerProps, useMapFocus } from './MapFocusContext'

/** 근교 당일치기 카드: 허브에서 닿는 근교 명소를 이동시간·교통·하이라이트로 정리. */
export function NearbyCard({ guide }: { guide?: NearbyGuide | null }) {
  const focus = useMapFocus()
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
        {guide.destinations.map((dest) => {
          // 근교는 허브 도시 밖이라, 허브를 지역 맥락으로 줘서 지도에 그 명소를 띄운다.
          const trig = placeTriggerProps(focus, { label: dest.name, area: guide.hub })
          return (
          <li key={dest.name} className="nearby-item">
            <div className="nearby-item__head">
              <strong className={trig.className} {...trig.interactive}>
                {cleanDisplayText(dest.name)}
              </strong>
              {dest.best_for && <span className="nearby-chip">{dest.best_for}</span>}
            </div>
            <div className="nearby-item__meta">
              <span className="nearby-time">🚆 {cleanDisplayText(dest.travel_time)}</span>
              {dest.transport && (
                <span className="nearby-transport">· {cleanDisplayText(dest.transport)}</span>
              )}
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
          )
        })}
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
