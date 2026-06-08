import { ClipboardCheck, WandSparkles } from 'lucide-react'

interface PlanActionsProps {
  isPlanning: boolean
  isValidating: boolean
  onPlan: () => void
  onValidate: () => void
}

export function PlanActions({ isPlanning, isValidating, onPlan, onValidate }: PlanActionsProps) {
  return (
    <section className="card action-card">
      <div>
        <p className="eyebrow">작업</p>
        <h2>계획 작업</h2>
      </div>
      <button type="button" className="primary-button" onClick={onPlan} disabled={isPlanning}>
        <WandSparkles aria-hidden="true" />
        {isPlanning ? '일정 생성 중...' : '일정 생성'}
      </button>
      <button
        type="button"
        className="secondary-button"
        onClick={onValidate}
        disabled={isValidating}
      >
        <ClipboardCheck aria-hidden="true" />
        {isValidating ? '일정 검증 중...' : '일정 검증'}
      </button>
    </section>
  )
}
