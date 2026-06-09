import type { LocalTransportItem, LocalTransportPlan } from '../types/trip'

function TransportRow({ item }: { item: LocalTransportItem }) {
  return (
    <li className="transit-row">
      <div className="transit-row__main">
        <strong>{item.name}</strong>
        {item.detail && <span className="transit-row__detail">{item.detail}</span>}
      </div>
      <div className="transit-row__meta">
        {item.duration && <span className="transit-chip">{item.duration}</span>}
        {item.price && <span className="transit-chip transit-chip--price">{item.price}</span>}
      </div>
    </li>
  )
}

/** 현지 이동 카드: 공항↔시내 교통 + 교통패스 추천. */
export function LocalTransportCard({ plan }: { plan?: LocalTransportPlan | null }) {
  if (!plan) return null
  return (
    <section className="card local-transport-card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">현지 이동</p>
          <h2>교통 — {plan.city}</h2>
        </div>
      </div>

      <p className="visa-summary">{plan.summary}</p>

      {plan.airport_transfers.length > 0 && (
        <>
          <p className="transit-group-label">공항 ↔ 시내</p>
          <ul className="transit-list">
            {plan.airport_transfers.map((item) => (
              <TransportRow key={item.name} item={item} />
            ))}
          </ul>
        </>
      )}

      {plan.transit_passes.length > 0 && (
        <>
          <p className="transit-group-label">교통패스 · 카드</p>
          <ul className="transit-list">
            {plan.transit_passes.map((item) => (
              <TransportRow key={item.name} item={item} />
            ))}
          </ul>
        </>
      )}

      {plan.tips.length > 0 && (
        <ul className="text-list">
          {plan.tips.map((tip) => (
            <li key={tip}>{tip}</li>
          ))}
        </ul>
      )}

      <p className="visa-disclaimer">
        ⓘ 요금·소요시간은 대략치입니다. 탑승 전{' '}
        {plan.source_url ? (
          <a href={plan.source_url} target="_blank" rel="noreferrer">
            현지 교통 공식 정보
          </a>
        ) : (
          '공식 정보'
        )}
        를 확인하세요.
      </p>
    </section>
  )
}
