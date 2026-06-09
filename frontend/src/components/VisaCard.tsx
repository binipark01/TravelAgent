import type { VisaCheckResult } from '../types/trip'

/** 입국/비자 요건 카드. 무비자 기간·전자여행허가·여권 유효기간을 한눈에 보여준다. */
export function VisaCard({ visa }: { visa?: VisaCheckResult | null }) {
  if (!visa) return null
  const needsVisa = visa.visa_required === true
  return (
    <section className="card visa-card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">입국 준비</p>
          <h2>비자 · 입국 요건 — {visa.destination_country}</h2>
        </div>
        <span className={`visa-badge ${needsVisa ? 'visa-badge--warn' : 'visa-badge--ok'}`}>
          {needsVisa ? '비자/도착비자 필요' : visa.visa_free_days ? `무비자 ${visa.visa_free_days}일` : '확인 필요'}
        </span>
      </div>

      <p className="visa-summary">{visa.summary}</p>

      <dl className="visa-facts">
        {visa.entry_authorization && (
          <div>
            <dt>전자여행허가</dt>
            <dd>{visa.entry_authorization}</dd>
          </div>
        )}
        {visa.passport_validity_rule && (
          <div>
            <dt>여권 유효기간</dt>
            <dd>{visa.passport_validity_rule}</dd>
          </div>
        )}
        {visa.passport_country && (
          <div>
            <dt>기준 여권</dt>
            <dd>{visa.passport_country}</dd>
          </div>
        )}
      </dl>

      {visa.details.length > 0 && (
        <ul className="text-list">
          {visa.details.map((d) => (
            <li key={d}>{d}</li>
          ))}
        </ul>
      )}

      <p className="visa-disclaimer">
        ⓘ 입국 정책은 수시로 바뀝니다. 출국 전{' '}
        {visa.source_url ? (
          <a href={visa.source_url} target="_blank" rel="noreferrer">
            외교부 해외안전여행
          </a>
        ) : (
          '외교부 해외안전여행'
        )}
        에서 반드시 재확인하세요.
      </p>
    </section>
  )
}
