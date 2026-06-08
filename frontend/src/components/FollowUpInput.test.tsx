import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { FollowUpInput } from './FollowUpInput'

describe('FollowUpInput', () => {
  it('submits a follow-up message', async () => {
    const onSubmit = vi.fn()
    render(<FollowUpInput isSubmitting={false} onSubmit={onSubmit} />)

    await userEvent.type(
      screen.getByLabelText('에이전트가 요청한 정보에 답변하기'),
      '출발지는 서울입니다.',
    )
    await userEvent.click(screen.getByRole('button', { name: '답변 보내기' }))

    expect(onSubmit).toHaveBeenCalledWith('출발지는 서울입니다.')
  })
})
