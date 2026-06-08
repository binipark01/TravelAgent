import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { getAgentRun } from '../api/agent'
import { ErrorState } from '../components/ErrorState'
import { PlanCards } from '../components/PlanCards'
import { errorMessage } from '../utils/errors'

export function SavedTripPage() {
  const { runId = '' } = useParams()
  const { data, isLoading, error } = useQuery({
    queryKey: ['run', runId],
    queryFn: () => getAgentRun(runId),
    enabled: Boolean(runId),
  })

  function copyShareLink() {
    void navigator.clipboard?.writeText(window.location.href)
  }

  const summary = data?.state_summary
  return (
    <section className="card wide-card saved-trip">
      <div className="saved-trip-header">
        <Link to="/trips" className="back-link">
          ← 내 여행
        </Link>
        <div className="saved-trip-actions">
          <button className="ghost-button" type="button" onClick={() => window.print()}>
            PDF로 저장
          </button>
          <button className="primary-button" type="button" onClick={copyShareLink}>
            공유 링크 복사
          </button>
        </div>
      </div>
      {isLoading && <p className="empty-panel-text">불러오는 중…</p>}
      {error && <ErrorState message={errorMessage(error)} />}
      {data && (
        <div className="saved-trip-body">
          <h1>{summary?.destination ?? '여행 계획'}</h1>
          <p className="section-summary">
            {[summary?.origin, summary?.destination].filter(Boolean).join(' → ') || '여행'}
            {summary?.date_range ? ` · ${summary.date_range}` : ''}
            {summary?.travelers ? ` · ${summary.travelers}명` : ''}
          </p>
          <PlanCards plan={data.state} />
        </div>
      )}
    </section>
  )
}
