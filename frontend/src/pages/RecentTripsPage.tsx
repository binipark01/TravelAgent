import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { listAgentRuns } from '../api/agent'
import { EmptyState } from '../components/EmptyState'
import { ErrorState } from '../components/ErrorState'
import { errorMessage } from '../utils/errors'
import { formatDateTime } from '../utils/format'

export function RecentTripsPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['agent-runs'],
    queryFn: () => listAgentRuns(40),
  })

  return (
    <section className="card">
      <h1>내 여행</h1>
      <p className="fine-print">눌러서 이어서 대화하기 — 그 여행 계획을 불러와 에이전트와 계속 진행해요.</p>
      {isLoading && <p className="empty-panel-text">불러오는 중…</p>}
      {error && <ErrorState message={errorMessage(error)} />}
      {data && data.length === 0 && <EmptyState message="저장된 여행이 없습니다." />}
      {data && data.length > 0 && (
        <div className="option-list">
          {data.map((run) => (
            <Link className="recent-trip-row" to={`/?run=${run.run_id}`} key={run.run_id}>
              <div>
                <strong>
                  {run.destination ?? '여행'}
                  {run.date_range ? ` · ${run.date_range}` : ''}
                </strong>
                <p className="recent-request-text">{run.message}</p>
              </div>
              <span>{formatDateTime(run.created_at)}</span>
            </Link>
          ))}
        </div>
      )}
    </section>
  )
}
