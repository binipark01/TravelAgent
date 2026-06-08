import type { LLMAnswerResponse } from '../types/llm'

export function LLMAnswerCard({ response }: { response: LLMAnswerResponse }) {
  const isBlocked = response.answer_kind === 'blocked'
  return (
    <section className="assistant-answer-message" aria-label="agent 답변">
      {isBlocked && (
        <span
          style={{
            display: 'inline-block',
            marginBottom: 8,
            padding: '2px 10px',
            borderRadius: 999,
            fontSize: 12,
            fontWeight: 600,
            background: 'rgba(217, 119, 6, 0.12)',
            color: '#b45309',
          }}
        >
          실시간 가격 미확정 · 참고용
        </span>
      )}
      <div className="llm-answer-text">{response.answer}</div>
    </section>
  )
}
