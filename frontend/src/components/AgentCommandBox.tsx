import { Send } from 'lucide-react'
import { useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import type { LLMAnswerRequest } from '../types/llm'

interface AgentCommandBoxProps {
  isSubmitting: boolean
  onSubmit: (payload: LLMAnswerRequest) => void
}

export function AgentCommandBox({ isSubmitting, onSubmit }: AgentCommandBoxProps) {
  const [message, setMessage] = useState('')

  function submitMessage() {
    const trimmedMessage = message.trim()
    if (!trimmedMessage || isSubmitting) return

    onSubmit({
      message: trimmedMessage,
      locale: 'ko-KR',
      currency: 'KRW',
      timezone: 'Asia/Seoul',
    })
    setMessage('')
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    submitMessage()
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return

    event.preventDefault()
    submitMessage()
  }

  return (
    <form className="agent-command-box" onSubmit={handleSubmit}>
      <label htmlFor="agent-request" className="composer-label">
        여행 요청
      </label>
      <div className="composer-row">
        <textarea
          id="agent-request"
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="여행 요청을 입력하세요"
          rows={3}
          required
        />
        <button
          className="primary-button composer-submit"
          type="submit"
          disabled={isSubmitting || !message.trim()}
        >
          <Send aria-hidden="true" />
          {isSubmitting ? '작성 중' : '보내기'}
        </button>
      </div>
    </form>
  )
}
