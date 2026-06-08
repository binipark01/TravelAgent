import { Send } from 'lucide-react'
import { type FormEvent, useMemo, useState } from 'react'
import type { TripPlanState } from '../types/trip'
import { fieldLabel } from '../utils/format'

type MissingInfoFormProps = {
  fields: string[]
  state: TripPlanState
  isSubmitting: boolean
  onSubmit: (message: string) => void
}

const questionMap: Record<string, string> = {
  origin: '출발지는 어디인가요?',
  destinations: '어디로 가고 싶으신가요?',
  start_date: '출발일 또는 가능한 기간은 언제인가요?',
  end_date: '언제 돌아오시나요?',
  travelers: '몇 명이 여행하시나요?',
  passport_country: '여권 국적은 어디인가요?',
}

export function MissingInfoForm({ fields, state, isSubmitting, onSubmit }: MissingInfoFormProps) {
  const [message, setMessage] = useState('')
  const questions = useMemo(() => fields.map((field) => questionMap[field] ?? fieldLabel(field)), [fields])
  const needsAnswer = fields.length > 0

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!message.trim()) return
    onSubmit(message.trim())
    setMessage('')
  }

  return (
    <section className="card info-edit-card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">에이전트 질문</p>
          <h2>{needsAnswer ? '한 번에 답변하기' : '에이전트에게 추가 지시'}</h2>
        </div>
      </div>
      {needsAnswer ? (
        <div className="agent-question-summary">
          <p>계획을 더 정확히 만들기 위해 아래 정보가 있으면 좋습니다. 한 문장으로 편하게 답하세요.</p>
          <ul>
            {questions.map((question) => (
              <li key={question}>{question}</li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="fine-print">
          이미 충분한 정보로 계획을 만들고 있습니다. 조건을 바꾸고 싶으면 자연어로 추가 지시를 보내세요.
        </p>
      )}
      <form className="missing-info-form" onSubmit={handleSubmit}>
        <label>
          답변 또는 추가 요청
          <textarea
            rows={4}
            value={message}
            onChange={(event) => setMessage(event.target.value)}
          />
        </label>
        <button className="primary-button" disabled={isSubmitting || !message.trim()} type="submit">
          <Send aria-hidden="true" />
          {isSubmitting ? '반영 중' : needsAnswer ? '답변 보내기' : '추가 지시 보내기'}
        </button>
      </form>
      {state.assumptions.length > 0 && (
        <p className="fine-print">에이전트가 부족한 값은 임시 가정으로 표시하고 계속 진행합니다.</p>
      )}
    </section>
  )
}
