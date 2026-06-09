import type { FxInfo } from '../types/trip'

/** 환율/돈 카드: 실시간 환율, 샘플 환산, 예산 현지통화 환산, 환전 팁. */
export function FxCard({ fx }: { fx?: FxInfo | null }) {
  if (!fx) return null
  return (
    <section className="card fx-card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">환율 · 돈</p>
          <h2>
            {fx.base_currency} → {fx.target_currency}
          </h2>
        </div>
        <span className="fx-rate-badge">
          1 {fx.target_currency} ≈ {fx.base_per_target.toFixed(fx.base_per_target < 10 ? 2 : 1)}{' '}
          {fx.base_currency}
        </span>
      </div>

      {fx.budget_total_target_label && (
        <p className="fx-budget">
          예상 예산이 현지 통화로 <strong>약 {fx.budget_total_target_label}</strong>
        </p>
      )}

      {fx.samples.length > 0 && (
        <ul className="fx-samples">
          {fx.samples.map((s) => (
            <li key={s.local_label}>
              <span className="fx-samples__local">{s.local_label}</span>
              <span className="fx-samples__arrow">≈</span>
              <span className="fx-samples__krw">{s.krw_label}</span>
            </li>
          ))}
        </ul>
      )}

      {fx.tips.length > 0 && (
        <ul className="text-list">
          {fx.tips.map((tip) => (
            <li key={tip}>{tip}</li>
          ))}
        </ul>
      )}

      <p className="visa-disclaimer">
        ⓘ 실시간 참고 환율입니다. 실제 환전·카드 결제 환율과는 차이가 있습니다.
      </p>
    </section>
  )
}
