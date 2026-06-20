import type { StayAreaGuide } from '../types/trip'
import { cleanDisplayText } from '../utils/format'

/** 숙박 구역 카드: '어느 동네에 묵을지'를 분위기·적합 여행·팁으로 정리(호텔 후보 보완). */
export function StayAreaCard({ guide }: { guide?: StayAreaGuide | null }) {
  if (!guide || guide.areas.length === 0) return null
  return (
    <section className="card stay-area-card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">어디에 묵을까</p>
          <h2>{cleanDisplayText(guide.destination)} 추천 숙박 구역</h2>
        </div>
      </div>

      <p className="visa-summary">{cleanDisplayText(guide.summary)}</p>

      <ul className="stay-area-list">
        {guide.areas.map((area) => (
          <li key={area.name} className="stay-area-item">
            <div className="stay-area-item__head">
              <strong>{cleanDisplayText(area.name)}</strong>
              {area.source_url && (
                <a href={area.source_url} target="_blank" rel="noreferrer">
                  출처 ↗
                </a>
              )}
            </div>
            {area.vibe && <p className="stay-area-vibe">{cleanDisplayText(area.vibe)}</p>}
            {area.good_for.length > 0 && (
              <div className="stay-area-tags">
                {area.good_for.map((g) => (
                  <span key={g} className="nearby-tag">
                    {cleanDisplayText(g)}
                  </span>
                ))}
              </div>
            )}
            {area.note && <p className="stay-area-note">ⓘ {cleanDisplayText(area.note)}</p>}
          </li>
        ))}
      </ul>

      <p className="card-footnote">LLM 웹검색 종합 · 호텔 후보의 위치 선택에 참고</p>
    </section>
  )
}
