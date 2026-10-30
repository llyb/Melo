import { describe, expect, it, vi } from 'vitest'
import { useChat } from '../src/renderer/src/composables/useChat'
import { validMessages } from '../src/shared/chat'

describe('chat state', () => {
  it('validates roles, unicode and boundaries', () => {
    expect(validMessages([{ role: 'user', content: '😀'.repeat(8000) }])).toBe(true)
    expect(validMessages([{ role: 'user', content: 'x'.repeat(8001) }])).toBe(false)
    expect(validMessages([{ role: 'system', content: 'x' }])).toBe(false)
    expect(validMessages([{ role: 'user', content: ' ' }])).toBe(false)
    expect(validMessages([{ role: 'user', content: 'a', secret: true }])).toBe(false)
    expect(validMessages([{ role: 'user', content: 'a' }, { role: 'assistant', content: 'x'.repeat(9000) }, { role: 'user', content: 'continue' }])).toBe(true)
  })

  it('keeps failed input and retries without duplicating history', async () => {
    const api = { health: vi.fn(), chat: vi.fn()
      .mockResolvedValueOnce({ ok: false, request_id: '1', error: { code: 'UPSTREAM_ERROR', message: '失败', retryable: true } })
      .mockResolvedValue({ ok: true, data: { request_id: '2', message: { role: 'assistant', content: '你好' } } }) }
    const state = useChat(api)
    state.input.value = '你好'
    await state.send()
    expect(state.input.value).toBe('你好')
    expect(state.messages.value).toHaveLength(0)
    await state.send()
    expect(state.messages.value.map(m => m.role)).toEqual(['user', 'assistant'])
    state.input.value = '继续'
    await state.send()
    expect(api.chat.mock.calls[2][0]).toHaveLength(3)
    state.reset()
    expect(state.messages.value).toHaveLength(0)
  })

  it('rejects duplicate sends and reset while pending', async () => {
    let finish!: (result: unknown) => void
    const api = { health: vi.fn(), chat: vi.fn(() => new Promise(resolve => { finish = resolve })) }
    const state = useChat(api as Parameters<typeof useChat>[0])
    await state.send()
    expect(api.chat).not.toHaveBeenCalled()
    state.input.value = 'hello'
    const pending = state.send()
    await state.send()
    state.reset()
    expect(state.input.value).toBe('hello')
    expect(api.chat).toHaveBeenCalledTimes(1)
    finish({ ok: true, data: { request_id: '1', message: { role: 'assistant', content: 'ok' } } })
    await pending
    expect(state.messages.value).toHaveLength(2)
  })
})
