import { describe, expect, it } from 'vitest'
import { buildApiUrl } from './client'

describe('buildApiUrl', () => {
  it('builds URLs from the configured API base URL', () => {
    expect(buildApiUrl('/trips')).toBe('http://127.0.0.1:8000/trips')
    expect(buildApiUrl('health')).toBe('http://127.0.0.1:8000/health')
  })
})
