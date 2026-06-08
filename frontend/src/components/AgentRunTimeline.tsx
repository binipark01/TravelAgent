import { AgentStepCard } from './AgentStepCard'
import type { AgentStep } from '../types/agent'
import { EmptyState } from './EmptyState'

export function AgentRunTimeline({ steps }: { steps: AgentStep[] }) {
  return (
    <section className="card agent-timeline-card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">실행 흐름</p>
          <h2>계획 처리 단계</h2>
        </div>
      </div>
      {steps.length === 0 ? (
        <EmptyState message="아직 실행된 단계가 없습니다." />
      ) : (
        <div className="agent-step-list">
          {steps.map((step) => (
            <AgentStepCard step={step} key={step.step_id} />
          ))}
        </div>
      )}
    </section>
  )
}
