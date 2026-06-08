import { Send } from 'lucide-react'
import { useState } from 'react'
import type { FormEvent } from 'react'

interface MessageBoxProps {
  isSubmitting: boolean
  onSubmit: (message: string) => void
}

export function MessageBox({ isSubmitting, onSubmit }: MessageBoxProps) {
  const [message, setMessage] = useState('')

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!message.trim()) return
    onSubmit(message.trim())
    setMessage('')
  }

  return (
    <section className="card">
      <h2>입력 정보 수정/추가</h2>
      <form className="stack" onSubmit={handleSubmit}>
        <label htmlFor="follow-up-message">수정하거나 보완할 여행 정보</label>
        <textarea
          id="follow-up-message"
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          rows={5}
        />
        <button type="submit" className="secondary-button" disabled={isSubmitting || !message.trim()}>
          <Send aria-hidden="true" />
          {isSubmitting ? '반영 중...' : '입력 정보 반영'}
        </button>
      </form>
    </section>
  )
}
