import type { TripStateSummary } from '../types/agent'
import { formatNumber, fieldLabel } from '../utils/format'

export function TripStateSummaryPanel({ summary }: { summary: TripStateSummary }) {
  return (
    <section className="card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">여행 상태</p>
          <h2>현재 여행 상태</h2>
        </div>
      </div>
      <dl className="summary-list">
        <div>
          <dt>목적지</dt>
          <dd>{summary.destination ?? '미정'}</dd>
        </div>
        <div>
          <dt>출발지</dt>
          <dd>{summary.origin ?? '미정'}</dd>
        </div>
        <div>
          <dt>기간</dt>
          <dd>{summary.date_range ?? '미정'}</dd>
        </div>
        <div>
          <dt>인원</dt>
          <dd>{summary.travelers ? `${summary.travelers}명` : '미정'}</dd>
        </div>
        <div>
          <dt>예산</dt>
          <dd>
            {summary.budget_per_person
              ? `1인 ${formatNumber(summary.budget_per_person)}`
              : summary.budget_total
                ? `총 ${formatNumber(summary.budget_total)}`
                : '미정'}
          </dd>
        </div>
      </dl>
      {summary.missing_fields.length > 0 && (
        <ul className="pill-list compact">
          {summary.missing_fields.map((field) => (
            <li key={field}>{fieldLabel(field)}</li>
          ))}
        </ul>
      )}
    </section>
  )
}
