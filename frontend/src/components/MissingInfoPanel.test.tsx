import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { MissingInfoPanel } from './MissingInfoPanel'

describe('MissingInfoPanel', () => {
  it('renders required missing questions with reasons', () => {
    render(<MissingInfoPanel fields={['origin', 'start_date', 'passport_country']} />)

    expect(screen.getByText('출발지')).toBeInTheDocument()
    expect(screen.getByText('출발일')).toBeInTheDocument()
    expect(screen.getByText('여권 국적')).toBeInTheDocument()
  })
})
