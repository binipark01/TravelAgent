import type { AgentEvent } from '../types/agent'
import { cleanDisplayText, formatDateTime } from '../utils/format'
import { EmptyState } from './EmptyState'

export function AgentEventLog({ events }: { events: AgentEvent[] }) {
  const visibleEvents = events.filter((event) =>
    [
      'user_message',
      'missing_info_detected',
      'critic_blocker_found',
      'plan_ready',
      'run_waiting_for_user',
      'run_completed',
      'error',
    ].includes(event.type),
  )

  return (
    <section className="card">
      <h2>대화와 주요 이벤트</h2>
      {visibleEvents.length === 0 ? (
        <EmptyState message="아직 표시할 이벤트가 없습니다." />
      ) : (
        <ol className="event-log">
          {visibleEvents.map((event) => (
            <li key={event.event_id}>
              <span>{formatDateTime(event.created_at)}</span>
              <strong>{cleanDisplayText(event.message)}</strong>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
