import type { SafetyInfo } from '../types/trip'

/** 안전·만일 카드: 긴급연락처, 영사콜센터, 여행경보, 보험/주의사항. */
export function SafetyCard({ safety }: { safety?: SafetyInfo | null }) {
  if (!safety) return null
  return (
    <section className="card safety-card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">안전 · 만일</p>
          <h2>현지 안전 — {safety.destination_country}</h2>
        </div>
      </div>

      <p className="visa-summary">{safety.summary}</p>

      {safety.emergency_contacts.length > 0 && (
        <ul className="safety-contacts">
          {safety.emergency_contacts.map((c) => (
            <li key={`${c.label}-${c.number}`}>
              <span className="safety-contacts__label">{c.label}</span>
              <a className="safety-contacts__number" href={`tel:${c.number.replace(/\s/g, '')}`}>
                {c.number}
              </a>
            </li>
          ))}
        </ul>
      )}

      <dl className="visa-facts">
        <div>
          <dt>영사콜센터(24h)</dt>
          <dd>{safety.consular_call_center}</dd>
        </div>
        {safety.embassy_note && (
          <div>
            <dt>대사관·영사관</dt>
            <dd>{safety.embassy_note}</dd>
          </div>
        )}
      </dl>

      {safety.travel_advisory && (
        <p className="safety-advisory">🚩 {safety.travel_advisory}</p>
      )}

      {safety.local_cautions.length > 0 && (
        <>
          <p className="transit-group-label">현지 주의사항</p>
          <ul className="text-list">
            {safety.local_cautions.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </>
      )}

      {safety.insurance_tips.length > 0 && (
        <>
          <p className="transit-group-label">여행자보험</p>
          <ul className="text-list">
            {safety.insurance_tips.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        </>
      )}

      <p className="visa-disclaimer">
        ⓘ 여행경보는 수시로 바뀝니다. 출국 전{' '}
        {safety.source_url ? (
          <a href={safety.source_url} target="_blank" rel="noreferrer">
            외교부 해외안전여행
          </a>
        ) : (
          '외교부 해외안전여행'
        )}
        에서 확인하세요.
      </p>
    </section>
  )
}
