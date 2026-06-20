import type { MultiCityPlan } from '../types/trip'
import { cleanDisplayText } from '../utils/format'

/** 멀티시티 동선: 도시별 숙박일수 + 도시간 이동(수단·소요·예매처) 오버뷰. */
export function MultiCityCard({ plan }: { plan?: MultiCityPlan | null }) {
  if (!plan || plan.segments.length === 0) return null
  return (
    <section className="card multicity-card wide-card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">멀티시티 동선</p>
          <h2>{plan.destinations.map(cleanDisplayText).join(' → ')}</h2>
        </div>
      </div>

      <p className="visa-summary">{cleanDisplayText(plan.summary)}</p>

      <ol className="multicity-flow">
        {plan.segments.map((seg, index) => (
          <li key={`${seg.city}-${index}`} className="multicity-seg">
            <div className="multicity-seg__head">
              <strong>{cleanDisplayText(seg.city)}</strong>
              <span className="multicity-nights">{seg.nights}박</span>
            </div>
            {seg.highlights.length > 0 && (
              <div className="multicity-tags">
                {seg.highlights.map((h) => (
                  <span key={h} className="nearby-tag">
                    {cleanDisplayText(h)}
                  </span>
                ))}
              </div>
            )}
            {plan.legs[index] && (
              <div className="multicity-leg">
                ↓ {cleanDisplayText(plan.legs[index].mode)} ·{' '}
                {cleanDisplayText(plan.legs[index].duration)}
                {plan.legs[index].booking_hint && (
                  <span className="multicity-book">
                    {' '}
                    · {cleanDisplayText(plan.legs[index].booking_hint as string)}
                  </span>
                )}
              </div>
            )}
          </li>
        ))}
      </ol>

      {plan.tips.length > 0 && (
        <ul className="text-list">
          {plan.tips.map((tip) => (
            <li key={tip}>{cleanDisplayText(tip)}</li>
          ))}
        </ul>
      )}
      <p className="card-footnote">
        LLM 웹검색 종합 · 각 도시 항공·숙소는 도시별로 따로 검색하세요
      </p>
    </section>
  )
}
