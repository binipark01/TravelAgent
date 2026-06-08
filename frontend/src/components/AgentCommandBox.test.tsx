import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { AgentCommandBox } from './AgentCommandBox'

describe('AgentCommandBox', () => {
  it('renders one command textarea without structured travel form fields', async () => {
    const onSubmit = vi.fn()
    render(<AgentCommandBox isSubmitting={false} onSubmit={onSubmit} />)

    expect(screen.getByLabelText('여행 요청')).toBeInTheDocument()
    expect(screen.queryByLabelText('출발지')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('목적지')).not.toBeInTheDocument()
    expect(screen.queryByText('맛집')).not.toBeInTheDocument()
    expect(screen.getByPlaceholderText('여행 요청을 입력하세요')).toBeInTheDocument()

    await userEvent.type(screen.getByLabelText('여행 요청'), '10월 초 일본 4박 5일')
    await userEvent.click(screen.getByRole('button', { name: '보내기' }))

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        message: '10월 초 일본 4박 5일',
        locale: 'ko-KR',
      }),
    )
  })

  it('submits immediately when Enter is pressed in the command box', async () => {
    const onSubmit = vi.fn()
    render(<AgentCommandBox isSubmitting={false} onSubmit={onSubmit} />)

    const commandBox = screen.getByLabelText('여행 요청')
    await userEvent.type(commandBox, '삿포로 항공권 찾아줘{Enter}')

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        message: '삿포로 항공권 찾아줘',
      }),
    )
    expect(commandBox).toHaveValue('')
  })

  it('keeps Shift Enter available for multiline requests', async () => {
    const onSubmit = vi.fn()
    render(<AgentCommandBox isSubmitting={false} onSubmit={onSubmit} />)

    const commandBox = screen.getByLabelText('여행 요청')
    await userEvent.type(commandBox, '삿포로')
    await userEvent.keyboard('{Shift>}{Enter}{/Shift}')
    await userEvent.type(commandBox, '오전 출발')

    expect(onSubmit).not.toHaveBeenCalled()
    expect(commandBox).toHaveValue('삿포로\n오전 출발')
  })
})
