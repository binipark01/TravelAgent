import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { BookingSimulationPanel } from './BookingSimulationPanel'

describe('BookingSimulationPanel', () => {
  it('disables booking simulation without approved approval', () => {
    render(
      <BookingSimulationPanel
        approvals={[]}
        booking={null}
        isSimulating={false}
        onSimulate={vi.fn()}
      />,
    )

    expect(screen.getByRole('button', { name: '예약 가능 여부 확인' })).toBeDisabled()
  })
})
