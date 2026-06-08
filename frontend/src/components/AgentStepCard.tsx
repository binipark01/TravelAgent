import type { AgentStep } from '../types/agent'
import { agentDisplayLabel, toolCallDisplayLabel } from '../utils/agentDisplay'
import { cleanDisplayText } from '../utils/format'

const stepStatusLabels: Record<AgentStep['status'], string> = {
  pending: '대기',
  running: '실행 중',
  completed: '완료',
  failed: '실패',
  skipped: '대기 중',
}

export function AgentStepCard({ step }: { step: AgentStep }) {
  const agentLabel = agentDisplayLabel(step.agent_name)

  return (
    <article className={`agent-step-card step-${step.status}`}>
      <header>
        <div>
          <strong>{agentLabel}</strong>
          {step.input_summary !== agentLabel && <p>{cleanDisplayText(step.input_summary)}</p>}
        </div>
        <span className="small-badge">{stepStatusLabels[step.status]}</span>
      </header>
      {step.output_summary && <p>{cleanDisplayText(step.output_summary)}</p>}
      {step.tool_calls.length > 0 && (
        <ul className="tool-call-list">
          {step.tool_calls.map((call, index) => (
            <li key={`${step.step_id}-${index}`}>{toolCallDisplayLabel(call)}</li>
          ))}
        </ul>
      )}
    </article>
  )
}
