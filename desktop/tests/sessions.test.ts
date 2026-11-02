import { expect, it, vi } from 'vitest'
import { useChat } from '../src/renderer/src/composables/useChat'
import type { MeloApi, SessionSummary } from '../src/shared/chat'

it('creates independent sessions and reuses a failed turn id on retry', async () => {
  const session: SessionSummary = { id: crypto.randomUUID(), title: '新会话', revision: 0, created_at: '', updated_at: '' }
  const sendTurn = vi.fn().mockResolvedValueOnce({ ok: false, request_id: 'x', error: { code: 'UPSTREAM_ERROR', message: '失败', retryable: true } }).mockResolvedValue({ ok: true, data: { session: { ...session, revision: 1 }, messages: [{ id: 'u', role: 'user', content: 'hi' }, { id: 'a', role: 'assistant', content: 'ok' }] } })
  const api = { health: vi.fn(), listSessions: vi.fn().mockResolvedValue({ ok: true, data: { items: [], has_more: false } }), createSession: vi.fn().mockResolvedValue({ ok: true, data: session }), sendTurn } as unknown as MeloApi
  const state = useChat(api)
  state.input.value = 'hi'
  await state.send()
  expect(state.input.value).toBe('hi')
  await state.send()
  expect(sendTurn.mock.calls[0][1].turn_id).toBe(sendTurn.mock.calls[1][1].turn_id)
  expect(state.messages.value).toHaveLength(2)
  await state.reset()
  expect(state.messages.value).toHaveLength(0)
})

it('locks send and create while a selection response is pending', async () => {
  let finish!: (value: unknown) => void
  const api = { getSession: vi.fn(() => new Promise(resolve => { finish = resolve })), sendTurn: vi.fn(), createSession: vi.fn() } as unknown as MeloApi
  const state = useChat(api)
  state.input.value = 'draft'
  const selecting = state.selectSession(crypto.randomUUID())
  await state.send()
  await state.reset()
  expect(api.sendTurn).not.toHaveBeenCalled()
  expect(api.createSession).not.toHaveBeenCalled()
  finish({ ok: false, request_id: 'r', error: { code: 'OFFLINE', message: 'offline', retryable: true } })
  await selecting
  expect(state.input.value).toBe('draft')
})

it('preserves per-session drafts and switches away after deleting the selected session', async () => {
  const a = { id: crypto.randomUUID(), title: 'A', revision: 0, created_at: '', updated_at: '' }
  const b = { ...a, id: crypto.randomUUID(), title: 'B' }
  let rows = [a, b]
  const api = {
    getSession: vi.fn(async (id: string) => ({ ok: true, data: { session: rows.find(s => s.id === id), messages: [], next_before_seq: null, pending_turn: null } })),
    listSessions: vi.fn(async () => ({ ok: true, data: { items: rows, has_more: false } })),
    deleteSession: vi.fn(async (id: string) => { rows = rows.filter(s => s.id !== id); return { ok: true, data: { deleted_id: id } } })
  } as unknown as MeloApi
  const state = useChat(api)
  await state.selectSession(a.id)
  state.input.value = 'A draft'
  await state.selectSession(b.id)
  state.input.value = 'B draft'
  await state.selectSession(a.id)
  expect(state.input.value).toBe('A draft')
  await state.deleteSession(a.id)
  expect(state.selected.value?.id).toBe(b.id)
  expect(state.input.value).toBe('B draft')
})
