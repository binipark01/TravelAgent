import type { TripPlanState } from '../types/trip'
import { cleanDisplayText, formatDateTime } from '../utils/format'
import { EmptyState } from './EmptyState'

export function EvidencePanel({ state }: { state: TripPlanState }) {
  const sourceCount = state.source_refs.length
  const evidenceCount = state.evidence_refs.length
  const liveCount = state.source_refs.filter((ref) => ref.is_live).length
  const reviewCount = Math.max(sourceCount - liveCount, 0)

  return (
    <section className="card evidence-panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">근거</p>
          <h2>수집 근거</h2>
        </div>
      </div>
      {evidenceCount === 0 && sourceCount === 0 ? (
        <EmptyState message="아직 수집된 근거가 없습니다." />
      ) : (
        <>
          <div className="metric-row">
            <div>
              <span>수집 근거</span>
              <strong>{evidenceCount}개</strong>
            </div>
            <div>
              <span>확인 출처</span>
              <strong>{sourceCount}개</strong>
            </div>
          </div>
          <p className="fine-print">
            실시간 확인 {liveCount}개 · 예약 전 재확인 {reviewCount}개
          </p>
          <ul className="source-mini-list">
            {state.source_refs.slice(0, 5).map((ref) => (
              <li key={ref.source_id}>
                <strong>{cleanDisplayText(ref.title) || '확인 출처'}</strong>
                <span>{ref.is_live ? '실시간 확인' : '예약 전 확인 필요'}</span>
                <small>{formatDateTime(ref.retrieved_at)}</small>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
