import { Send } from 'lucide-react'
import { useState } from 'react'
import type { FormEvent } from 'react'

interface FollowUpInputProps {
  isSubmitting: boolean
  onSubmit: (message: string) => void
}

export function FollowUpInput({ isSubmitting, onSubmit }: FollowUpInputProps) {
  const [message, setMessage] = useState('')

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!message.trim()) return
    onSubmit(message.trim())
    setMessage('')
  }

  return (
    <section className="card">
      <h2>추가 답변</h2>
      <form className="stack" onSubmit={handleSubmit}>
        <label htmlFor="agent-follow-up">에이전트가 요청한 정보에 답변하기</label>
        <textarea
          id="agent-follow-up"
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          rows={4}
        />
        <button type="submit" className="secondary-button" disabled={isSubmitting || !message.trim()}>
          <Send aria-hidden="true" />
          {isSubmitting ? '반영 중...' : '답변 보내기'}
        </button>
      </form>
    </section>
  )
}
