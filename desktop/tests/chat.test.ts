import { expect, it } from 'vitest'
import { validText } from '../src/shared/chat'
it('validates Unicode input boundaries without UTF-16 truncation', () => {
  expect(validText('😀'.repeat(8000), 8000)).toBe(true)
  expect(validText('😀'.repeat(8001), 8000)).toBe(false)
  expect(validText(' ', 8000)).toBe(false)
})
