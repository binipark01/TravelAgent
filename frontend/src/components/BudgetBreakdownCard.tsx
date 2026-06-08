import type { BudgetEstimate } from '../types/budget'
import { cleanDisplayText, formatNumber } from '../utils/format'
import { EmptyState } from './EmptyState'

const labels: Record<keyof BudgetEstimate['breakdown'], string> = {
  flights: '항공',
  accommodation: '숙박',
  food: '식비',
  local_transport: '현지 이동',
  activities: '입장/체험',
  buffer: '예비비',
}

export function BudgetBreakdownCard({ budget }: { budget?: BudgetEstimate | null }) {
  return (
    <section className="card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">비용</p>
          <h2>예산</h2>
        </div>
      </div>
      {!budget ? (
        <EmptyState message="아직 예산이 계산되지 않았습니다." />
      ) : (
        <>
          <div className="metric-row">
            <div>
              <span>총 예상 비용</span>
              <strong>{formatNumber(budget.total_estimated_cost, budget.currency)}</strong>
            </div>
            <div>
              <span>1인 예상 비용</span>
              <strong>{formatNumber(budget.per_person_estimated_cost, budget.currency)}</strong>
            </div>
          </div>
          <dl className="breakdown-list">
            {Object.entries(budget.breakdown).map(([key, value]) => (
              <div key={key}>
                <dt>{labels[key as keyof BudgetEstimate['breakdown']]}</dt>
                <dd>{formatNumber(value, budget.currency)}</dd>
              </div>
            ))}
          </dl>
          {budget.budget_warnings.length > 0 && (
            <ul className="text-list warning-list">
              {budget.budget_warnings.map((warning) => (
                <li key={warning}>{cleanDisplayText(warning) || '모든 가격은 추정치입니다.'}</li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  )
}
