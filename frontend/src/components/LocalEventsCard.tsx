import type { LocalEventsGuide } from '../types/trip'
import { cleanDisplayText } from '../utils/format'
import { placeTriggerProps, useMapFocus } from './MapFocusContext'

/** 현지 축제·이벤트 카드: 여행 날짜에 목적지에서 열리는 행사를 기간·장소·하이라이트로 정리. */
export function LocalEventsCard({ guide }: { guide?: LocalEventsGuide | null }) {
  const focus = useMapFocus()
  if (!guide || guide.events.length === 0) return null
  return (
    <section className="card events-card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">현지 축제·이벤트</p>
          <h2>{guide.destination} 여행 중 열리는 행사</h2>
        </div>
        {guide.date_range && <span className="events-range">{guide.date_range}</span>}
      </div>

      <p className="visa-summary">{guide.summary}</p>

      <ul className="events-list">
        {guide.events.map((event) => {
          // 행사장이 있으면 도시를 지역 맥락으로 줘서 지도에 그 장소를 띄운다.
          const trig = event.venue
            ? placeTriggerProps(focus, { label: event.venue, area: guide.destination })
            : null
          return (
            <li key={`${event.name}-${event.period}`} className="events-item">
              <div className="events-item__head">
                <strong>{cleanDisplayText(event.name)}</strong>
                <span className="events-chip">{cleanDisplayText(event.category)}</span>
                {event.period && (
                  <span className="events-period">📅 {cleanDisplayText(event.period)}</span>
                )}
              </div>
              {event.highlight && (
                <p className="events-highlight">{cleanDisplayText(event.highlight)}</p>
              )}
              <div className="events-item__meta">
                {event.venue &&
                  (trig ? (
                    <span className={`events-venue ${trig.className}`.trim()} {...trig.interactive}>
                      📍 {cleanDisplayText(event.venue)}
                    </span>
                  ) : (
                    <span className="events-venue">📍 {cleanDisplayText(event.venue)}</span>
                  ))}
                {event.source_url && (
                  <a
                    className="events-source"
                    href={event.source_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    출처
                  </a>
                )}
              </div>
            </li>
          )
        })}
      </ul>

      <p className="visa-disclaimer">
        ⓘ 일정·장소는 변동될 수 있어요. 방문 전 공식 안내를 확인하세요.
      </p>
    </section>
  )
}
